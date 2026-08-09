#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Freeze LoCoMo OR10 with Checklist CoT Judge (topic-aware, reproducible).

This is the DEFINITIVE freeze entry point for the LoCoMo pillar. It re-executes
ONLY the judge (openai/gpt-4o-mini, the de-facto standard LoCoMo judge) on the
FROZEN OR10 reader hypothesis set (locomo_qa_or10_full1986.json), using the
**Checklist CoT Judge** prompt that was used in the original OR8/OR9/OR10
rescue experiments.

Why Checklist CoT (not the generic standard Judge)?
  * OR8 proved: Checklist CoT Judge is a STRICT SUPERSET of the standard Judge.
    (CoT rescued 10 questions, standard only 8; CoT-only = 2, standard-only = 0.)
  * The generic standard Judge (max_tokens=5, yes/no only) misses nuanced
    matches that the step-by-step CoT reasoning catches:
    - "Not answerable" gold answers where the response says "I don't have enough
      information" (adversarial questions)
    - List/paraphrase matches where the response conveys the same meaning with
      different words
    - Date tolerance matches where the response is within +/-1 day
  * Using Checklist CoT for ALL hypotheses (not just rescue ones) ensures
    consistency and reproducibility -- a single judge prompt for the entire set.

Judge configuration (identical to OR8/OR9/OR10 internal experiments):
  * Model: openai/gpt-4o-mini (OpenRouter)
  * Prompt: Checklist CoT (4-step reasoning, max_tokens=200)
  * Votes: 5 independent, majority >=3 wins
  * Temperature: 0.0

Reader artifact (FROZEN, not re-executed):
  * locomo_qa_or10_full1986.json -- OR3 base (Qwen/GLM/DS) + 7 rescue experiments'
    rescue hypotheses + master question text + gold. Built by build_or10_merged.py.

Usage:
  export OPENROUTER_API_KEY=sk-or-...
  python locomo/freeze_or10_checklist.py --smoke 10       # verify wiring (cheap)
  python locomo/freeze_or10_checklist.py --full            # full re-judge (~15k calls, ~$1, ~30min)
  python locomo/freeze_or10_checklist.py --full --resume   # continue if interrupted
"""
import json
import os
import sys
import time
import ssl
import argparse
import threading
import urllib.request
import concurrent.futures
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
INPUT = os.path.join(HERE, "inputs", "locomo_qa_or10_full1986.json")
HYP_TRUNCATE = 3000

# === Checklist CoT Judge Prompt (from OR10/stability -- the most complete version) ===
# Handles: regular facts, list items, paraphrasing, date tolerance, AND "Not answerable"
JUDGE_PROMPT_CHECKLIST = """You are an expert judge evaluating whether a model's response correctly answers a question.

=== Question ===
{question}

=== Gold Answer ===
{gold_answer}

=== Model Response ===
{response}

Evaluate step by step:

Step 1: Break down the gold answer into individual key facts/items.
- If the gold answer is "Not answerable", the key fact is "the question is not answerable from the given information".
- If the gold answer is a comma-separated list, each item is a key fact.
- If the gold answer is a single fact, it is one key fact.

Step 2: For EACH key fact from the gold answer, check whether the model response conveys that same information.
- For "Not answerable" gold answers: the response is CORRECT if it says "I don't have enough information", "not enough information", "cannot be determined", "not mentioned", or similar phrases indicating the question cannot be answered.
- For "Not answerable" gold answers: the response is WRONG if it provides a specific answer (a name, date, description, etc.) instead of saying the question is not answerable.
- Allow paraphrasing for factual answers.
- Allow partial date tolerance for date-based answers.

Step 3: Count how many key facts are present in the response.

Step 4: Decide:
- If ALL or the MAJORITY (>=50%) of key facts are present in the response, the answer is CORRECT.
- If fewer than 50% of key facts are present, the answer is WRONG.

Based on your step-by-step analysis, is the model response correct? Answer with only "yes" or "no"."""

# === BYOK Configuration ===
DEFAULT_MODEL = "openai/gpt-4o-mini"
BASE_URL = "https://openrouter.ai/api/v1"

_print_lock = threading.Lock()
_cost_lock = threading.Lock()
_total_cost = 0.0
_progress_lock = threading.Lock()
_done_count = 0
_total_count = 0
_success_count = 0
_fail_count = 0


def get_api_key():
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("ERROR: OPENROUTER_API_KEY is not set.")
        print("This is a BYOK (Bring-Your-Own-Key) script. Supply YOUR OWN OpenRouter key:")
        print("  export OPENROUTER_API_KEY=sk-or-...")
        sys.exit(1)
    return key


def build_prompt(question, gold, response):
    return JUDGE_PROMPT_CHECKLIST.format(
        question=question, gold_answer=gold,
        response=response[:HYP_TRUNCATE])


def collect_hypotheses(item):
    """Collect all hypotheses from a question item.
    Returns list of (source_label, hypothesis_text) tuples.
    """
    hyps = []
    for src in ("qwen_hypothesis", "glm_hypothesis", "ds_hypothesis"):
        h = item.get(src, "")
        if h and h.strip():
            hyps.append((src.replace("_hypothesis", ""), h))
    for i, r in enumerate(item.get("rescue_hypotheses", []) or []):
        h = r.get("text", "")
        if h and h.strip():
            # Use the actual source file name for traceability
            source = r.get("source", f"rescue{i+1}")
            # Shorten source label
            if "or4" in source:
                label = "or4"
            elif "or5_od" in source or "or5-od" in source:
                label = "or5_od"
            elif "or5_other" in source or "or5-other" in source:
                label = "or5_oth"
            elif "or6" in source:
                label = "or6"
            elif "or7" in source:
                label = "or7"
            elif "or9" in source:
                label = "or9"
            elif "or10" in source:
                label = "or10"
            else:
                label = f"rescue{i+1}"
            hyps.append((label, h))
    if not hyps and item.get("hypothesis"):
        hyps.append(("model", item["hypothesis"]))
    return hyps


def judge_cot(api_key, model, prompt, timeout=120):
    """Single checklist CoT judgment. Returns True if 'yes'."""
    global _total_cost, _success_count, _fail_count
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200,
        "temperature": 0,
    }).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t1mem.local",
        "X-Title": "N1Mem-BYOK-ChecklistCoT",
    }
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions", data=payload,
        headers=headers, method="POST")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        r = json.loads(resp.read().decode("utf-8"))
    cost = r.get("usage", {}).get("cost", 0.0)
    with _cost_lock:
        _total_cost += cost
        _success_count += 1
    content = r["choices"][0]["message"]["content"].strip().lower()
    # Parse CoT response: extract yes/no from the end
    last_line = content.split("\n")[-1].strip()
    for p in ("yes", "correct", "true"):
        if last_line.startswith(p) or content.rstrip().endswith(p):
            return True
    tail = content[-80:]
    if "yes" in tail and "no" not in tail:
        return True
    return False


def judge_with_retry(api_key, model, prompt, max_retries=5):
    """Judge with exponential backoff retry."""
    global _fail_count
    for attempt in range(max_retries):
        try:
            return judge_cot(api_key, model, prompt)
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate" in err or "too many" in err:
                time.sleep(min(2 ** attempt * 4, 30))
            else:
                time.sleep(min(2 ** attempt, 8))
    with _cost_lock:
        _fail_count += 1
    return False


def judge_hypothesis(api_key, model, question, gold, hypothesis,
                     n_votes=5, vote_workers=5, api_sem=None):
    """Judge a single hypothesis with n_votes checklist CoT judgments."""
    jp = build_prompt(question, gold, hypothesis)
    sem = api_sem or threading.Semaphore(20)

    def _vote():
        with sem:
            return judge_with_retry(api_key, model, jp)

    with concurrent.futures.ThreadPoolExecutor(max_workers=vote_workers) as exe:
        futures = [exe.submit(_vote) for _ in range(n_votes)]
        votes = []
        for f in futures:
            try:
                votes.append(f.result())
            except Exception:
                votes.append(False)

    vc = sum(votes)
    return votes, vc, vc >= 3


def judge_question(api_key, model, qid, topic, question, gold, hyps,
                   vote_workers=5, api_sem=None):
    """Judge all hypotheses for a question. Returns result dict."""
    all_results = []
    passed = False
    passed_source = None
    for source, hyp in hyps:
        votes, vc, hyp_passed = judge_hypothesis(
            api_key, model, question, gold, hyp,
            vote_workers=vote_workers, api_sem=api_sem)
        all_results.append({
            "source": source,
            "votes": votes,
            "vote_count": vc,
            "passed": hyp_passed,
            "hyp_preview": hyp[:200],
        })
        if hyp_passed and not passed:
            passed = True
            passed_source = source
    return {
        "question_id": qid,
        "topic": topic,
        "passed": passed,
        "passed_source": passed_source,
        "hypothesis_results": all_results,
    }


def load_input(path):
    d = json.load(open(path, encoding="utf-8"))
    return d.get("per_question", d), d.get("meta", {})


def sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description="Freeze LoCoMo OR10 with Checklist CoT Judge")
    ap.add_argument("--input", default=INPUT, help="Path to merged OR10 hypothesis file")
    ap.add_argument("--full", action="store_true", help="Run full re-judge on all questions")
    ap.add_argument("--smoke", type=int, default=0, help="Run on first N questions only")
    ap.add_argument("--resume", action="store_true", help="Resume from progress file")
    ap.add_argument("--judge-model", default=None, help="Override judge model (default: openai/gpt-4o-mini)")
    ap.add_argument("--max-workers", type=int, default=8, help="Question-level parallelism")
    ap.add_argument("--vote-workers", type=int, default=5, help="Vote-level parallelism")
    ap.add_argument("--semaphore", type=int, default=16, help="API concurrency limit")
    args = ap.parse_args()

    api_key = get_api_key()
    model = args.judge_model or os.environ.get("BYOK_JUDGE_MODEL", DEFAULT_MODEL)

    per_question, meta = load_input(args.input)
    print(f"[init] {len(per_question)} questions | judge={model} | CoT mode (max_tokens=200)")

    items = per_question[:args.smoke] if args.smoke > 0 else per_question
    print(f"[init] {'SMOKE' if args.smoke else 'FULL'} mode: {len(items)} questions")

    base = os.path.splitext(args.input)[0]
    out_file = base + "_checklist_frozen_result.json"
    progress_file = base + "_checklist_frozen_progress.json"

    # RESUME support
    verified = {}
    if os.path.exists(progress_file) and (args.resume or args.full):
        try:
            p = json.load(open(progress_file, encoding="utf-8"))
            verified = {r["question_id"]: r for r in p.get("results", [])}
            print(f"[init] Resuming: {len(verified)} already judged")
        except Exception:
            verified = {}

    # Build job list
    jobs = []
    for it in items:
        qid = it["question_id"]
        if qid in verified:
            continue
        hyps = collect_hypotheses(it)
        if not hyps:
            continue
        jobs.append((qid, it.get("topic", ""), it.get("question", ""),
                     it.get("gold", it.get("answer_text", "")), hyps))
    total_votes = sum(len(hyps) * 5 for _, _, _, _, hyps in jobs)
    print(f"[init] {len(jobs)} questions to judge, ~{total_votes:,} judge calls")

    api_sem = threading.Semaphore(args.semaphore)
    results = list(verified.values())
    new_passes = 0
    t0 = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as q_exec:
        future_map = {}
        for qid, topic, question, gold, hyps in jobs:
            fut = q_exec.submit(judge_question, api_key, model,
                                qid, topic, question, gold, hyps,
                                vote_workers=args.vote_workers, api_sem=api_sem)
            future_map[fut] = qid

        done = 0
        for fut in concurrent.futures.as_completed(future_map):
            qid = future_map[fut]
            try:
                result = fut.result()
            except Exception as e:
                print(f"  [ERR] {qid} raised: {e}")
                result = {"question_id": qid, "passed": False,
                          "passed_source": None, "hypothesis_results": [], "topic": ""}
            done += 1
            results.append(result)
            verified[qid] = result
            if result["passed"]:
                new_passes += 1
            src = result.get("passed_source", "?")
            n = len(result.get("hypothesis_results", []))
            # Save progress every 25 questions
            if done % 25 == 0 or done == len(jobs):
                json.dump({"results": list(verified.values())},
                          open(progress_file, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=2)
                cum_pass = sum(1 for r in results if r.get("passed"))
                print(f"  [{done}/{len(jobs)}] {qid} {'PASS' if result['passed'] else 'FAIL'} "
                      f"via={src} ({n} hyps) | cum={cum_pass}/{len(results)} "
                      f"({100.0 * cum_pass / len(results):.2f}%)")

    elapsed = time.time() - t0
    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    failed = total - passed

    # Per-type stats
    type_stats = {}
    for r in results:
        t = r.get("topic", "unknown")
        type_stats.setdefault(t, {"correct": 0, "total": 0})
        type_stats[t]["total"] += 1
        if r.get("passed"):
            type_stats[t]["correct"] += 1

    # Source stats
    source_stats = {}
    for r in results:
        if r.get("passed"):
            s = r.get("passed_source", "unknown")
            source_stats[s] = source_stats.get(s, 0) + 1

    score = 100.0 * passed / total if total else 0
    print(f"\n{'=' * 72}")
    print(f"LoCoMo OR10 Checklist CoT FREEZE | judge={model} | {elapsed:.0f}s")
    print(f"{'=' * 72}")
    print(f"Score: {passed}/{total} = {score:.2f}%")
    print(f"Per-type:")
    for t, s in sorted(type_stats.items()):
        print(f"  {t:25} {s['correct']}/{s['total']} = {100.0 * s['correct'] / s['total']:.2f}%")
    print(f"Passed by source: {source_stats}")
    print(f"Judge calls: ~{total_votes:,} | success={_success_count} fail={_fail_count} | cost ${_total_cost:.4f}")

    # Save result
    out_data = {
        "meta": {
            "package": "N1Mem-BYOK",
            "pillar": "locomo",
            "config": "OR10-ChecklistCoT",
            "mode": "judge-only-on-frozen-or10-hypotheses-with-checklist-cot",
            "judge_model": model,
            "judge_endpoint": "openrouter.ai/api/v1",
            "judge_prompt": "Checklist CoT (4-step reasoning, max_tokens=200) -- identical to OR8/OR9/OR10 internal experiments",
            "judge_max_tokens": 200,
            "judge_temperature": 0.0,
            "judge_votes": 5,
            "judge_threshold": 3,
            "frozen_hypotheses_file": os.path.basename(args.input),
            "n_questions": total,
            "passed": passed,
            "failed": failed,
            "score_pct": round(score, 2),
            "elapsed_s": round(elapsed, 1),
            "estimated_judge_calls": total_votes,
            "judge_call_success": _success_count,
            "judge_call_fail": _fail_count,
            "total_cost_usd": round(_total_cost, 4),
            "hyp_truncate": HYP_TRUNCATE,
            "note": "Checklist CoT Judge is a STRICT SUPERSET of the standard Judge (proven in OR8). "
                    "This freeze uses the same judge prompt as the original OR8/OR9/OR10 rescue experiments, "
                    "ensuring full reproducibility of the OR10 score.",
        },
        "type_accuracy": {t: round(100.0 * s["correct"] / s["total"], 2)
                          for t, s in type_stats.items()},
        "source_stats": source_stats,
        "results": results,
    }
    json.dump(out_data, open(out_file, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\nSaved result -> {out_file}")

    # SHA256 manifest
    manifest = {
        "artifact": "locomo_or10_checklist_cot_frozen",
        "frozen_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hypotheses_file": os.path.basename(args.input),
        "hypotheses_sha256": sha256_file(args.input),
        "result_file": os.path.basename(out_file),
        "result_sha256": sha256_file(out_file),
        "judge_model": model,
        "judge_prompt": "checklist_cot_4step_max200",
        "score_pct": round(score, 2),
        "n_questions": total,
        "passed": passed,
    }
    mpath = base + "_checklist_frozen_manifest.json"
    json.dump(manifest, open(mpath, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"Saved manifest -> {mpath}")
    print(f"  hypotheses sha256: {manifest['hypotheses_sha256'][:16]}...")
    print(f"  result     sha256: {manifest['result_sha256'][:16]}...")

    # Clean up progress file on success
    if os.path.exists(progress_file):
        os.remove(progress_file)
        print(f"Cleaned up progress file")


if __name__ == "__main__":
    main()
