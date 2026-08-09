#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LoCoMo QA — BYOK Judge (Mode A: judge-only on frozen reader hypotheses).

This is the reproduction entry point for an external party who wants to verify
T1Mem's LoCoMo score WITHOUT trusting our API keys.

What it does:
  1. Loads the FROZEN reader hypotheses we ship in inputs/locomo_qa_or3_full1986.json
     (model outputs from Qwen 3.7 Max / GLM 5.2 / DS V4-Pro — fixed, reproducible artifacts).
  2. Re-runs ONLY the judge with YOUR OWN OpenRouter key (openai/gpt-4o-mini by default,
     the de-facto standard LoCoMo judge; use --judge-model openai/gpt-4o for a stricter
     cross-check), using the EXACT same LoCoMo judge prompt T1Mem used internally.
  3. Aggregates 5 votes per hypothesis; a question passes if ANY hypothesis reaches
     >=3/5 "yes" (OR3 union). This is identical to T1Mem's internal scoring.
  4. Emits a result JSON with the same schema as our published frozen result, so the
     reproduced score is directly comparable.

Why this isolates the judge variable: the reader outputs are frozen artifacts, so the
only thing you re-execute is the judge — under your own key. If your score matches ours
(within GPT-judge variance), our claimed number is independently corroborated.

Usage:
  export OPENROUTER_API_KEY=sk-or-...        # YOUR key (BYOK)
  python locomo/run_judge_byok.py --full
  python locomo/run_judge_byok.py --smoke 10
  python locomo/run_judge_byok.py --full --resume
  python locomo/run_judge_byok.py --full --judge-model openai/gpt-4o   # 可选：更严交叉验证
"""
import json
import os
import sys
import time
import argparse
import threading
import concurrent.futures

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "common"))
from openrouter_judge import OpenRouterJudge  # noqa: E402

INPUT_DEFAULT = os.path.join(HERE, "inputs", "locomo_qa_or3_full1986.json")
HYP_TRUNCATE = 3000

# ---- LoCoMo judge prompt (IDENTICAL to T1Mem's internal domestic judge) ----
JUDGE_PROMPT_TEMPLATE = """You are an expert judge evaluating whether a model's response is correct.

=== Question ===
{question}

=== Gold Answer ===
{gold_answer}

=== Model Response ===
{response}

Evaluation criteria:
- The response is correct if it conveys the same meaning as the gold answer, even if worded differently.
- For factual questions, the response must contain the key factual information.
- For temporal questions, allow ±1 day tolerance for date-based answers.
- For adversarial questions, "I don't have enough information" is correct only if the gold answer indicates the question is unanswerable.
- Minor wording differences are acceptable as long as the core answer matches.
- For LIST questions (gold answer contains multiple comma-separated items):
  * The response is correct if it contains the MAJORITY of the gold answer's key items.
  * Extra items in the response that are not in the gold answer are ACCEPTABLE — do NOT mark wrong just because the response includes additional related items.
  * Missing 1-2 items from a list of 4+ is acceptable if the response captures the main items.
  * Paraphrased items count as matches (e.g., "dairy-free cake" matches "dairy free vanilla cake").
  * The response does NOT need to list items in the same order as the gold answer.

Is the model response correct? Answer yes or no only."""


def build_judge_prompt(question, gold, response):
    return JUDGE_PROMPT_TEMPLATE.format(
        question=question, gold_answer=gold, response=response[:HYP_TRUNCATE])


def collect_hypotheses(item):
    hyps = []
    for src in ("qwen_hypothesis", "glm_hypothesis", "ds_hypothesis"):
        h = item.get(src, "")
        if h and h.strip():
            hyps.append((src.replace("_hypothesis", ""), h))
    if not hyps and item.get("hypothesis"):
        hyps.append(("model", item["hypothesis"]))
    return hyps


def load_input(path):
    d = json.load(open(path, encoding="utf-8"))
    if isinstance(d, dict):
        if "per_question" in d:
            return d["per_question"], d
        for k, v in d.items():
            if isinstance(v, list) and v and isinstance(v[0], dict) and "question_id" in v[0]:
                return v, d
    if isinstance(d, list):
        return d, None
    raise ValueError(f"Cannot find per_question list in {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=INPUT_DEFAULT)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--smoke", type=int, default=0)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--output", default=None)
    ap.add_argument("--judge-model", default=None, help="Override BYOK_JUDGE_MODEL")
    args = ap.parse_args()

    if args.judge_model:
        os.environ["BYOK_JUDGE_MODEL"] = args.judge_model

    judge = OpenRouterJudge()

    per_question, meta = load_input(args.input)
    print(f"[init] Loaded {len(per_question)} questions from {os.path.basename(args.input)}")

    items = per_question[:args.smoke] if args.smoke > 0 else per_question
    print(f"[init] {'SMOKE' if args.smoke else 'FULL'} mode: {len(items)} questions | judge={judge.model}")

    out_file = args.output or os.path.join(
        HERE, "..", "docs" if os.path.isdir(os.path.join(HERE, "..", "docs")) else ".",
        "locomo_byok_result.json")
    # simpler default: put result next to this script
    out_file = args.output or os.path.join(HERE, "locomo_byok_result.json")
    progress_file = out_file[:-len("_result.json")] + "_progress.json" if out_file.endswith("_result.json") else out_file + ".progress"

    verified = {}
    if os.path.exists(progress_file) and (args.resume or args.full):
        try:
            p = json.load(open(progress_file, encoding="utf-8"))
            verified = {r["question_id"]: r for r in p.get("results", [])}
            print(f"[init] Resuming: {len(verified)} already judged")
        except Exception:
            verified = {}

    jobs = []
    for it in items:
        qid = it["question_id"]
        if qid in verified:
            continue
        hyps = collect_hypotheses(it)
        if not hyps:
            continue
        jobs.append((qid, it.get("topic", ""), it.get("query", it.get("question", "")),
                     it.get("answer_text", ""), hyps))
    print(f"[init] {len(jobs)} questions to judge")

    results = list(verified.values())
    new_passes = 0
    total_votes = 0
    t0 = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=judge.max_workers) as q_exec, \
         concurrent.futures.ThreadPoolExecutor(max_workers=judge.vote_workers) as v_exec:
        future_map = {}
        for qid, topic, question, gold, hyps in jobs:
            total_votes += len(hyps) * 5
            fut = q_exec.submit(_judge_question, judge, v_exec, qid, topic, question, gold, hyps)
            future_map[fut] = qid
        done = 0
        for fut in concurrent.futures.as_completed(future_map):
            qid = future_map[fut]
            try:
                result = fut.result()
            except Exception as e:  # noqa: BLE001
                print(f"  [ERR] {qid} raised: {e}")
                result = {"question_id": qid, "passed": False, "passed_source": None,
                          "hypothesis_results": [], "topic": ""}
            done += 1
            results.append(result)
            verified[qid] = result
            if result["passed"]:
                new_passes += 1
            src = result.get("passed_source", "?")
            n = len(result.get("hypothesis_results", []))
            print(f"  [{done}/{len(jobs)}] {qid} {'PASS' if result['passed'] else 'FAIL'} via={src} ({n} hyps)")
            if done % 5 == 0 or done == len(jobs):
                json.dump({"results": list(verified.values())}, open(progress_file, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=2)

    elapsed = time.time() - t0
    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    type_stats = {}
    for r in results:
        t = r.get("topic", "unknown")
        type_stats.setdefault(t, {"correct": 0, "total": 0})
        type_stats[t]["total"] += 1
        if r.get("passed"):
            type_stats[t]["correct"] += 1
    source_stats = {}
    for r in results:
        if r.get("passed"):
            s = r.get("passed_source", "unknown")
            source_stats[s] = source_stats.get(s, 0) + 1

    print(f"\n{'=' * 60}")
    print(f"BYOK LoCoMo Judge Complete (elapsed {elapsed:.0f}s) | judge={judge.model}")
    print(f"{'=' * 60}")
    print(f"Score: {passed}/{total} = {100.0 * passed / total:.2f}%")
    print("Per-type:")
    for t, s in sorted(type_stats.items()):
        acc = 100.0 * s["correct"] / s["total"] if s["total"] else 0
        print(f"  {t:20} {s['correct']}/{s['total']} = {acc:.2f}%")
    print(f"Passed by source: {source_stats}")
    print(f"Judge calls: ~{total_votes:,} | success/fail: {judge.success}/{judge.fail} | cost ${judge.cost:.4f}")

    json.dump({
        "meta": {
            "package": "N1Mem-BYOK",
            "pillar": "locomo",
            "mode": "judge-only-on-frozen-hypotheses",
            "judge_model": judge.model,
            "judge_endpoint": "openrouter.ai/api/v1",
            "judge_prompt": "identical to T1Mem domestic LoCoMo judge (see run_judge_byok.py)",
            "frozen_hypotheses_file": os.path.basename(args.input),
            "total_judged": total, "passed": passed, "failed": total - passed,
            "score_pct": round(100.0 * passed / total, 2),
            "elapsed_s": round(elapsed, 1), "estimated_judge_calls": total_votes,
            "judge_call_success": judge.success, "judge_call_fail": judge.fail,
            "total_cost_usd": round(judge.cost, 4), "hyp_truncate": HYP_TRUNCATE,
            "note": "Reader outputs are frozen artifacts (qwen/glm/ds). Only the judge was re-executed under BYOK.",
        },
        "type_accuracy": {t: round(100.0 * s["correct"] / s["total"], 2) for t, s in type_stats.items()},
        "source_stats": source_stats,
        "results": results,
    }, open(out_file, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nSaved to {out_file}")


def _judge_question(judge, v_exec, qid, topic, question, gold, hyps):
    all_results = []
    passed = False
    passed_source = None
    for source, hyp in hyps:
        jp = build_judge_prompt(question, gold, hyp)
        futures = [v_exec.submit(judge.judge_one, jp) for _ in range(5)]
        votes = [f.result() for f in futures]
        hyp_passed = sum(votes) >= 3
        all_results.append({"source": source, "votes": votes, "vote_count": sum(votes),
                            "passed": hyp_passed, "hyp_preview": hyp[:200]})
        if hyp_passed and not passed:
            passed = True
            passed_source = source
    return {"question_id": qid, "topic": topic, "passed": passed,
            "passed_source": passed_source, "hypothesis_results": all_results}


if __name__ == "__main__":
    main()
