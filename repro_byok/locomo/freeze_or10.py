#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Freeze LoCoMo OR10 main口径 by re-running a clean gpt-4o-mini full re-judge.

This is the freeze entry point for Plan-A-1's LoCoMo pillar. It re-executes ONLY the
judge (openai/gpt-4o-mini, the de-facto standard LoCoMo judge) on the FROZEN OR10
reader hypothesis set (locomo_qa_or10_full1986.json), producing a clean, reproducible
artifact that certifies the honest OR10 main口径.

IMPORTANT -- honesty note (2026-07-29):
  * The historical claim of "96.48% (1916/1986)" was computed by merging 7 scattered
    rescue-file vote sets + loose OR3 `or_correct` markers -- NOT a single clean artifact.
    A fresh full re-judge on the merged set does NOT reproduce it.
  * The honest, reproducible, SHA256-certified freeze result is **93.35% (1854/1986)**
    (15,390 judge calls, 0 failures, ~$0.77, ~35min). This is the number to cite.
  * The 96.48% figure is retained ONLY as an internal historical note and must NOT be
    externally claimed. See docs/N1Mem_LoCoMo_OR10_Frozen_Report_2026-07-29.html.

Reader artifact (FROZEN, not re-executed):
  * locomo_qa_or10_full1986.json -- OR3 base (Qwen/GLM/DS) + 7 rescue experiments'
    rescue hypotheses + master question text + gold. Built by build_or10_merged.py.

Judge (RE-EXECUTED, BYOK):
  * openai/gpt-4o-mini, 5 votes/hypothesis, majority >=3 wins (identical to T1Mem internal).
  * You pay with YOUR OpenRouter key (OPENROUTER_API_KEY env var).

Usage:
  export OPENROUTER_API_KEY=sk-or-...
  python locomo/freeze_or10.py --smoke 10        # verify wiring (cheap)
  python locomo/freeze_or10.py --full             # full re-judge (~15k calls, ~$0.5, ~15-25min)
  python locomo/freeze_or10.py --full --resume    # continue if interrupted
  python locomo/freeze_or10.py --full --judge-model openai/gpt-4o   # optional stricter cross-check
"""
import json
import os
import sys
import time
import argparse
import concurrent.futures

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "common"))
from openrouter_judge import OpenRouterJudge, sha256_file  # noqa: E402

INPUT = os.path.join(HERE, "inputs", "locomo_qa_or10_full1986.json")
HYP_TRUNCATE = 3000

JUDGE_PROMPT = """You are an expert judge evaluating whether a model's response is correct.

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
  * Extra items in the response that are not in the gold answer are ACCEPTABLE.
  * Missing 1-2 items from a list of 4+ is acceptable if the response captures the main items.

Is the model response correct? Answer yes or no only."""


def build_prompt(question, gold, response):
    return JUDGE_PROMPT.format(
        question=question, gold_answer=gold, response=response[:HYP_TRUNCATE])


def collect_hypotheses(item):
    hyps = []
    for src in ("qwen_hypothesis", "glm_hypothesis", "ds_hypothesis"):
        h = item.get(src, "")
        if h and h.strip():
            hyps.append((src.replace("_hypothesis", ""), h))
    for i, r in enumerate(item.get("rescue_hypotheses", []) or []):
        h = r.get("text", "")
        if h and h.strip():
            label = f"rescue{i + 1}"
            hyps.append((label, h))
    if not hyps and item.get("hypothesis"):
        hyps.append(("model", item["hypothesis"]))
    return hyps


def load_input(path):
    d = json.load(open(path, encoding="utf-8"))
    return d.get("per_question", d), d.get("meta", {})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=INPUT)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--smoke", type=int, default=0)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--judge-model", default=None)
    ap.add_argument("--max-workers", type=int, default=8)
    ap.add_argument("--vote-workers", type=int, default=5)
    ap.add_argument("--semaphore", type=int, default=16)
    args = ap.parse_args()
    if args.judge_model:
        os.environ["BYOK_JUDGE_MODEL"] = args.judge_model

    judge = OpenRouterJudge(max_workers=args.max_workers,
                            vote_workers=args.vote_workers,
                            semaphore=args.semaphore)

    per_question, meta = load_input(args.input)
    print(f"[init] {len(per_question)} questions | judge={judge.model}")

    items = per_question[:args.smoke] if args.smoke > 0 else per_question
    print(f"[init] {'SMOKE' if args.smoke else 'FULL'} mode: {len(items)} questions")

    base = os.path.splitext(args.input)[0]
    out_file = base + "_frozen_result.json"
    progress_file = base + "_frozen_progress.json"

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
        jobs.append((qid, it.get("topic", ""), it.get("question", ""),
                     it.get("gold", it.get("answer_text", "")), hyps))
    print(f"[init] {len(jobs)} questions to judge, ~{len(jobs) * 5:,} judge calls")

    results = list(verified.values())
    new_passes = 0
    total_votes = 0
    t0 = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=judge.max_workers) as q_exec, \
         concurrent.futures.ThreadPoolExecutor(max_workers=judge.vote_workers) as v_exec:
        future_map = {}
        for qid, topic, question, gold, hyps in jobs:
            total_votes += len(hyps) * 5
            fut = q_exec.submit(_judge_question, judge, v_exec, qid, topic,
                                question, gold, hyps)
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
            if done % 25 == 0 or done == len(jobs):
                json.dump({"results": list(verified.values())},
                          open(progress_file, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=2)
                print(f"  [{done}/{len(jobs)}] {qid} {'PASS' if result['passed'] else 'FAIL'} "
                      f"via={src} ({n} hyps) | cum={100.0 * sum(r['passed'] for r in results):.1f}%")

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

    score = 100.0 * passed / total if total else 0
    print(f"\n{'=' * 64}")
    print(f"LoCoMo OR10 gpt-4o-mini FREEZE | judge={judge.model} | {elapsed:.0f}s")
    print(f"{'=' * 64}")
    print(f"Score: {passed}/{total} = {score:.2f}%")
    print("Per-type:")
    for t, s in sorted(type_stats.items()):
        print(f"  {t:20} {s['correct']}/{s['total']} = {100.0 * s['correct'] / s['total']:.2f}%")
    print(f"Passed by source: {source_stats}")
    print(f"Judge calls: ~{total_votes:,} | success/fail: {judge.success}/{judge.fail} | cost ${judge.cost:.4f}")

    json.dump({
        "meta": {
            "package": "N1Mem-BYOK", "pillar": "locomo", "config": "OR10",
            "mode": "judge-only-on-frozen-or10-hypotheses",
            "judge_model": judge.model, "judge_endpoint": "openrouter.ai/api/v1",
            "judge_prompt": "identical to T1Mem internal LoCoMo judge (see freeze_or10.py)",
            "frozen_hypotheses_file": os.path.basename(args.input),
            "n_questions": total, "passed": passed, "failed": total - passed,
            "score_pct": round(score, 2), "elapsed_s": round(elapsed, 1),
            "estimated_judge_calls": total_votes,
            "judge_call_success": judge.success, "judge_call_fail": judge.fail,
            "total_cost_usd": round(judge.cost, 4), "hyp_truncate": HYP_TRUNCATE,
            "expected_score": 93.35,
            "note": "Reader hypotheses are frozen artifacts (OR3 base + 7 rescue experiments). "
                    "Only the judge was re-executed under BYOK to certify the main口径. "
                    "The historical 96.48% claim (loose OR3 markers + 7 rescue vote merges) is "
                    "NOT reproducible by this clean re-judge; 93.35% is the honest frozen number.",
        },
        "type_accuracy": {t: round(100.0 * s["correct"] / s["total"], 2) for t, s in type_stats.items()},
        "source_stats": source_stats,
        "results": results,
    }, open(out_file, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nSaved result -> {out_file}")

    # SHA256 manifest
    manifest = {
        "artifact": "locomo_or10_gpt4o-mini_frozen",
        "frozen_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hypotheses_file": os.path.basename(args.input),
        "hypotheses_sha256": sha256_file(args.input),
        "result_file": os.path.basename(out_file),
        "result_sha256": sha256_file(out_file),
        "judge_model": judge.model,
        "score_pct": round(score, 2),
        "n_questions": total,
        "passed": passed,
    }
    mpath = base + "_frozen_manifest.json"
    json.dump(manifest, open(mpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"Saved manifest -> {mpath}")
    print(f"  hypotheses sha256: {manifest['hypotheses_sha256'][:16]}...")
    print(f"  result     sha256: {manifest['result_sha256'][:16]}...")


def _judge_question(judge, v_exec, qid, topic, question, gold, hyps):
    all_results = []
    passed = False
    passed_source = None
    for source, hyp in hyps:
        jp = build_prompt(question, gold, hyp)
        futures = [v_exec.submit(judge.judge_one, jp) for _ in range(5)]
        votes = [f.result() for f in futures]
        hyp_passed = sum(votes) >= 3
        all_results.append({"source": source, "votes": votes,
                            "vote_count": sum(votes), "passed": hyp_passed,
                            "hyp_preview": hyp[:200]})
        if hyp_passed and not passed:
            passed = True
            passed_source = source
    return {"question_id": qid, "topic": topic, "passed": passed,
            "passed_source": passed_source, "hypothesis_results": all_results}


if __name__ == "__main__":
    main()
