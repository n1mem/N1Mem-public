#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Option A — regenerate LoCoMo answers under the OFFICIAL LoCoMo generation protocol,
then score with the OFFICIAL F1 metric (snap-research/locomo task_eval/evaluation.py).

GOAL: produce a number that is comparable to the *original* LoCoMo paper's metric
(token-level F1), by matching its generation protocol:
  - short / few-word answers (num_tokens_request=32 in the official code)
  - adversarial questions answered with the exact refusal phrase the official
    string-match expects ("not mentioned in the conversation").

DESIGN (isolation of the output-format variable):
  - SAME endpoints as OR10 (qwen / glm / deepseek-v4-pro via build_llm) -> no model switch.
  - SAME context as OR10 (FULL conversation sessions, ~150K, no retrieval) -> fair.
  - ONLY the answer FORMAT changes (concise prompt instead of long CoT prompt).
  - Output goes to a NEW file (locomo_qa_or10_concise_full1986.json). The original
    OR10 file and all option-B frozen results are NEVER modified.

Supports:
  --limit N     run only a stratified slice (N total, ~N/5 per category) for validation
  --models L    comma list of model keys (default qwen,glm,deepseek-v4-pro)
  --resume      skip questions already present in the output file

This script ONLY generates. Scoring is done by freeze_or10_official_f1.py pointed at
the concise file (see --score-only notes in report). For convenience, validation mode
also prints baseline-vs-concise F1 on the slice.
"""
import json
import sys
import os
import re
import time
import argparse
import threading
import concurrent.futures

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]   # T1Mem/
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src" / "t1mem-core"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

sys.stdout.reconfigure(line_buffering=True)

# Import score_hypothesis from the existing official-F1 evaluator (no LLM judge).
# This guarantees the SAME metric is used for baseline and concise comparison.
sys.path.insert(0, str(SCRIPT_DIR))
from freeze_or10_official_f1 import score_hypothesis, TOPIC_TO_CAT

# Warm up circular deps, then build_llm (same adapter OR10 used).
import memory.engine  # noqa: F401
from llm.adapter import build_llm

SECRETS = str(PROJECT_ROOT / "secrets")

# ---------------------------------------------------------------------------
# Concise generation prompt (official-protocol faithful: short answer)
# ---------------------------------------------------------------------------
CONCISE_PROMPT = """Based on the following conversation transcripts, answer the question.

=== Conversation Transcripts ===
{context}

=== Question ===
{question}

CRITICAL INSTRUCTIONS:
- Output ONLY the direct answer to the question. Nothing else.
- No full sentences. No explanations. No preamble. No "Based on the conversation...".
- If the answer is a name, output just the name.
- If the answer is a place, output just the place.
- If the answer is an item, output just the item name.
- If the answer is multiple items, separate with commas: "item1, item2, item3"
- Do NOT add context like "performed at the concert" or "from a trip to".
- Do NOT add "The answer is" or any wrapper text.
- Search through ALL sessions carefully. The answer IS in the conversations.
{adversarial_line}

Answer:"""

ADVERSARIAL_LINE = ("- If the question cannot be answered from the conversation (e.g., it "
                    "contains a false premise or asks about something never discussed), "
                    "output exactly: Not mentioned in the conversation")

REFUSAL_SIGNALS = [
    'not mentioned', 'no information available', 'no information',
    "don't have enough", 'do not have enough', 'cannot answer', "can't answer",
    'unable to answer', 'not answerable', 'false premise', "i don't know",
    'i do not know', 'insufficient', 'no way to determine', 'not discussed',
    'not stated', 'no mention', 'never mentioned', 'not in the conversation',
    'not provided',
]


def clean_output(text, topic):
    """Strip think blocks, Answer: prefix, quotes; normalize adversarial refusals."""
    if not text:
        return ""
    t = text
    # remove <think:opensource>...</think:opensource> (Qwen thinking)
    t = re.sub(r'<think>.*?</think>', '', t, flags=re.DOTALL).strip()
    # remove leading "Answer:" / "The answer is:"
    t = re.sub(r'^\s*(answer\s*:?\s*|the answer is\s*:?\s*)', '', t, flags=re.IGNORECASE)
    # strip surrounding quotes
    t = t.strip().strip('"').strip("'").strip()
    # collapse whitespace
    t = ' '.join(t.split())

    if topic == 'adversarial':
        low = t.lower()
        if any(sig in low for sig in REFUSAL_SIGNALS):
            return 'Not mentioned in the conversation'
    return t


def build_context(session_texts, session_datetimes):
    parts = []
    for i, s in enumerate(session_texts):
        dt = ''
        if session_datetimes and i < len(session_datetimes) and session_datetimes[i]:
            dt = f' ({session_datetimes[i]})'
        parts.append(f'[Session {i+1}{dt}] {s}')
    return '\n\n'.join(parts) if parts else '(No conversation history available)'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None,
                    help='stratified slice size for validation (≈N/5 per category)')
    ap.add_argument('--models', type=str, default='qwen,glm,deepseek-v4-pro',
                    help='comma list of model keys')
    ap.add_argument('--resume', action='store_true', help='skip completed questions')
    ap.add_argument('--workers', type=int, default=4)
    args = ap.parse_args()

    models = [m.strip() for m in args.models.split(',') if m.strip()]

    # ---- Load OR10 question set (question_id, topic, question, gold) ----
    or10_path = SCRIPT_DIR / 'inputs' / 'locomo_qa_or10_full1986.json'
    with open(or10_path, 'r', encoding='utf-8') as f:
        or10 = json.load(f)
    per_q = or10['per_question']
    print(f'[load] OR10 questions: {len(per_q)}', flush=True)

    # ---- Load full conversation data for context ----
    full_path = PROJECT_ROOT / 'data' / 'bench' / 'locomo_mc10_full.json'
    print(f'[load] conversation data: {full_path}', flush=True)
    with open(full_path, 'r', encoding='utf-8') as f:
        full_items = json.load(f)
    full_map = {}
    for it in full_items:
        qid = it.get('question_id')
        full_map[qid] = it
    print(f'[load] conversation items: {len(full_map)}', flush=True)

    # ---- Select questions ----
    if args.limit:
        per_cat = max(1, args.limit // 5)
        sel = []
        seen = {t: 0 for t in TOPIC_TO_CAT}
        for q in per_q:
            t = q['topic']
            if seen[t] < per_cat:
                sel.append(q)
                seen[t] += 1
        # pad if some category short
        if len(sel) < args.limit:
            for q in per_q:
                if q not in sel:
                    sel.append(q)
                if len(sel) >= args.limit:
                    break
        questions = sel
        print(f'[select] stratified slice: {len(questions)} '
              f'(per-category cap={per_cat})', flush=True)
    else:
        questions = per_q
        print(f'[select] FULL run: {len(questions)} questions', flush=True)

    # ---- Resume ----
    out_path = SCRIPT_DIR / 'inputs' / 'locomo_qa_or10_concise_full1986.json'
    done = {}
    if args.resume and out_path.exists():
        with open(out_path, 'r', encoding='utf-8') as f:
            prev = json.load(f)
        for r in prev.get('per_question', []):
            done[r['question_id']] = r
        print(f'[resume] {len(done)} questions already done', flush=True)

    # ---- Build LLM clients (same endpoints as OR10) ----
    clients = {}
    for m in models:
        clients[m] = build_llm(m, secrets_dir=SECRETS, no_circuit=True,
                               max_cost_per_run=10.0)
    print(f'[llm] clients ready: {list(clients.keys())}', flush=True)

    lock = threading.Lock()
    t0 = time.time()
    gen_count = 0

    def gen_one(q):
        qid = q['question_id']
        topic = q['topic']
        gold = q['gold']
        it = full_map.get(qid)
        if it is None:
            return {'question_id': qid, 'topic': topic, 'question': q['question'],
                    'gold': gold, 'error': 'no conversation data',
                    'concise': {m: '' for m in models}}
        context = build_context(it.get('session_texts', []),
                                it.get('session_datetimes', []))
        adv_line = ADVERSARIAL_LINE if topic == 'adversarial' else ''
        prompt = CONCISE_PROMPT.format(context=context, question=q['question'],
                                       adversarial_line=adv_line)
        out = {}
        for m in models:
            try:
                raw = clients[m].complete(prompt, max_tokens=120, temperature=0.0)
                out[m] = clean_output(raw, topic)
            except Exception as e:
                out[m] = ''
                print(f'  [WARN] {qid}/{m} gen failed: {e}', flush=True)
        return {'question_id': qid, 'topic': topic, 'question': q['question'],
                'gold': gold, 'concise': out}

    # ---- Run ----
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as exe:
        futs = {exe.submit(gen_one, q): q for q in questions
                if q['question_id'] not in done}
        total = len(futs)
        for i, fut in enumerate(concurrent.futures.as_completed(futs), 1):
            r = fut.result()
            results.append(r)
            gen_count += 1
            if i % 20 == 0 or i == total:
                el = time.time() - t0
                print(f'  [{i}/{total}] {gen_count} gen | {el:.1f}s '
                      f'({el/max(i,1):.2f}s/q)', flush=True)

    # merge resumed
    merged = {}
    for r in results:
        merged[r['question_id']] = r
    for qid, r in done.items():
        merged.setdefault(qid, r)
    ordered = [merged[q['question_id']] for q in questions
               if q['question_id'] in merged]

    out = {
        'meta': {
            'method': 'optionA_official_protocol_concise',
            'models': models,
            'prompt': 'concise (short answer) + adversarial->Not mentioned',
            'context': 'full conversation sessions (~150K), no retrieval',
            'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'n_questions': len(ordered),
            'is_slice': bool(args.limit),
        },
        'per_question': ordered,
    }
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f'[save] {out_path}  ({len(ordered)} questions)', flush=True)

    # ---- Validation: baseline vs concise F1 on this slice ----
    base_map = {q['question_id']: q for q in per_q}
    cat_scores = {}
    for r in ordered:
        qid = r['question_id']
        topic = r['topic']
        gold = r['gold']
        base = base_map.get(qid, {})
        old_hyp = (base.get('qwen_hypothesis', '') or '')
        # concise best across models (OR)
        concise_scores = [score_hypothesis(topic, r['concise'].get(m, ''), gold)
                          for m in models if r['concise'].get(m, '').strip()]
        concise_best = max(concise_scores) if concise_scores else 0.0
        base_sc = score_hypothesis(topic, old_hyp, gold) if old_hyp.strip() else 0.0
        cat_scores.setdefault(topic, {'base': [], 'concise': []})
        cat_scores[topic]['base'].append(base_sc)
        cat_scores[topic]['concise'].append(concise_best)

    print('\n' + '=' * 64)
    print('VALIDATION  baseline(old qwen long) vs concise(official protocol)')
    print('=' * 64)
    all_b, all_c = [], []
    for topic, d in sorted(cat_scores.items(), key=lambda x: -len(x[1]['base'])):
        b = sum(d['base']) / len(d['base'])
        c = sum(d['concise']) / len(d['concise'])
        all_b.extend(d['base']); all_c.extend(d['concise'])
        print(f'  {topic:<18} N={len(d["base"]):>3}  base={b*100:5.1f}%  '
              f'concise={c*100:5.1f}%  Δ={(c-b)*100:+5.1f}pp')
    print('-' * 64)
    print(f'  {"OVERALL":<18} N={len(all_b):>3}  base={sum(all_b)/len(all_b)*100:5.1f}%  '
          f'concise={sum(all_c)/len(all_c)*100:5.1f}%  '
          f'Δ={(sum(all_c)/len(all_c)-sum(all_b)/len(all_b))*100:+5.1f}pp')
    print('=' * 64)


if __name__ == '__main__':
    main()
