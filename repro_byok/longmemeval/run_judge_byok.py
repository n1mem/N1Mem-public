#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LongMemEval QA — BYOK Judge (Mode A: judge frozen hypotheses with your own key).

Reproduces T1Mem's LongMemEval score WITHOUT trusting our API keys.

What it does:
  1. Loads FROZEN reader hypotheses we ship in inputs/t1mem_hypotheses_500.jsonl
     (T1Mem's best hypothesis per question — a fixed, reproducible artifact).
  2. Loads GOLD answers/type from the OFFICIAL LongMemEval dataset via --gold
     (build it once with build_gold.py; the official data is public).
  3. Re-runs ONLY the judge with YOUR OWN OpenRouter key (openai/gpt-4o default), using
     the EXACT same task-specific anscheck prompt T1Mem used internally.
  4. 5 independent votes per hypothesis, majority (>=3) wins; a question passes if ANY
     hypothesis reaches majority. Mirrors T1Mem's OR aggregation.

Faithfulness note:
  * This Mode A artifact ships T1Mem's SINGLE best hypothesis per question. T1Mem's
    published 99.2% is an OR aggregate over MULTIPLE model hypotheses
    (Qwen / GLM / V4Pro / SFE / flip strategies). To reproduce the full OR number,
    supply a multi-hypothesis input (see README "Mode B") — the same script ORs across
    all hypotheses per question, so no code change is needed.
  * Either way, only the judge is re-executed under your key; reader outputs are frozen.

Usage:
  export OPENROUTER_API_KEY=sk-or-...     # YOUR key (BYOK)
  python longmemeval/build_gold.py --data <official_longmemeval_dir> --out longmemeval/inputs/lme_gold.json
  python longmemeval/run_judge_byok.py --gold longmemeval/inputs/lme_gold.json --full
  python longmemeval/run_judge_byok.py --gold longmemeval/inputs/lme_gold.json --smoke 10
"""
import json
import os
import sys
import time
import argparse
import concurrent.futures

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "common"))
from openrouter_judge import OpenRouterJudge  # noqa: E402

INPUT_DEFAULT = os.path.join(HERE, "inputs", "t1mem_hypotheses_500.jsonl")
HYP_TRUNCATE = 3000

# ============ anscheck prompt — IDENTICAL to T1Mem's internal LME judge ============
def get_anscheck_prompt(task, question, answer, response, abstention=False):
    if not abstention:
        if task in ["single-session-user", "single-session-assistant", "multi-session"]:
            template = (
                "I will give you a question, a correct answer, and a response from a model. "
                "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
                "If the response is equivalent to the correct answer or contains all the intermediate steps "
                "to get the correct answer, you should also answer yes. If the response only contains a subset "
                "of the information required by the answer, answer no. \n\n"
                "Question: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\n"
                "Is the model response correct? Answer yes or no only."
            )
            prompt = template.format(question, answer, response)
        elif task == "temporal-reasoning":
            template = (
                "I will give you a question, a correct answer, and a response from a model. "
                "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
                "If the response is equivalent to the correct answer or contains all the intermediate steps "
                "to get the correct answer, you should also answer yes. If the response only contains a subset "
                "of the information required by the answer, answer no. In addition, do not penalize off-by-one "
                "errors for the number of days. If the question asks for the number of days/weeks/months, etc., "
                "and the model makes off-by-one errors (e.g., predicting 19 days when the answer is 18), the "
                "model's response is still correct. \n\n"
                "Question: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\n"
                "Is the model response correct? Answer yes or no only."
            )
            prompt = template.format(question, answer, response)
        elif task == "knowledge-update":
            template = (
                "I will give you a question, a correct answer, and a response from a model. "
                "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
                "If the response contains some previous information along with an updated answer, the response "
                "should be considered as correct as long as the updated answer is the required answer.\n\n"
                "Question: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\n"
                "Is the model response correct? Answer yes or no only."
            )
            prompt = template.format(question, answer, response)
        elif task == "single-session-preference":
            template = (
                "I will give you a question, a rubric for desired personalized response, and a response from a model. "
                "Please answer yes if the response satisfies the desired response. Otherwise, answer no. "
                "The model does not need to reflect all the points in the rubric. The response is correct as long "
                "as it recalls and utilizes the user's personal information correctly.\n\n"
                "Question: {}\n\nRubric: {}\n\nModel Response: {}\n\n"
                "Is the model response correct? Answer yes or no only."
            )
            prompt = template.format(question, answer, response)
        else:
            template = (
                "I will give you a question, a correct answer, and a response from a model. "
                "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
                "Answer yes or no only.\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\n"
                "Is the model response correct? Answer yes or no only."
            )
            prompt = template.format(question, answer, response)
    else:
        template = (
            "I will give you an unanswerable question, an explanation, and a response from a model. "
            "Please answer yes if the model correctly identifies the question as unanswerable. The model could "
            "say that the information is incomplete, or some other information is given but the asked information "
            "is not.\n\nQuestion: {}\n\nExplanation: {}\n\nModel Response: {}\n\n"
            "Does the model correctly identify the question as unanswerable? Answer yes or no only."
        )
        prompt = template.format(question, answer, response)
    return prompt


def load_hypotheses(path):
    """Return {question_id: [(source, hypothesis_text), ...]}.

    Accepts two input shapes:
      * jsonl of {"question_id","hypothesis"}  -> single source "best"
      * json of {question_id: {"hypotheses":[{"source","hypothesis"}]}} -> multi-source
    """
    grouped = {}
    if path.endswith(".jsonl"):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            qid = d["question_id"]
            grouped.setdefault(qid, []).append(("best", d.get("hypothesis", "")))
    else:
        d = json.load(open(path, encoding="utf-8"))
        for qid, v in d.items():
            hyps = v.get("hypotheses", []) if isinstance(v, dict) else []
            grouped.setdefault(qid, []).extend([(h.get("source", "best"), h.get("hypothesis", "")) for h in hyps])
    return grouped


def load_gold(path):
    """Return {question_id: {"question","answer","type"}}."""
    g = json.load(open(path, encoding="utf-8"))
    out = {}
    if isinstance(g, list):
        for r in g:
            out[r["question_id"]] = {"question": r.get("question", ""),
                                     "answer": r.get("answer", ""),
                                     "type": r.get("type", r.get("question_type", "multi-session"))}
    else:
        for qid, v in g.items():
            out[qid] = {"question": v.get("question", ""), "answer": v.get("answer", ""),
                        "type": v.get("type", v.get("question_type", "multi-session"))}
    return out


ABSTENTION_QIDS = set()  # T1Mem used should_use_abstention(); reproduced by gold "unanswerable" flag if present.


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=INPUT_DEFAULT)
    ap.add_argument("--gold", required=True, help="Gold mapping from build_gold.py (official LME data)")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--smoke", type=int, default=0)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--output", default=None)
    ap.add_argument("--judge-model", default=None)
    args = ap.parse_args()
    if args.judge_model:
        os.environ["BYOK_JUDGE_MODEL"] = args.judge_model

    judge = OpenRouterJudge()

    hyp = load_hypotheses(args.input)
    gold = load_gold(args.gold)
    qids = list(hyp.keys())
    if args.smoke > 0:
        qids = qids[:args.smoke]
    print(f"[init] {len(qids)} questions | judge={judge.model} | hyps={sum(len(v) for v in hyp.values())}")

    out_file = args.output or os.path.join(HERE, "longmemeval_byok_result.json")
    progress_file = out_file + ".progress"

    verified = {}
    if os.path.exists(progress_file) and (args.resume or args.full):
        try:
            p = json.load(open(progress_file, encoding="utf-8"))
            verified = {r["question_id"]: r for r in p.get("results", [])}
            print(f"[init] Resuming: {len(verified)} already judged")
        except Exception:
            verified = {}

    jobs = [(qid, gold.get(qid, {})) for qid in qids if qid not in verified]
    print(f"[init] {len(jobs)} questions to judge")

    results = list(verified.values())
    t0 = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=judge.max_workers) as q_exec, \
         concurrent.futures.ThreadPoolExecutor(max_workers=judge.vote_workers) as v_exec:
        future_map = {}
        for qid, g in jobs:
            fut = q_exec.submit(_judge_question, judge, v_exec, qid, g, hyp.get(qid, []))
            future_map[fut] = qid
        done = 0
        for fut in concurrent.futures.as_completed(future_map):
            qid = future_map[fut]
            try:
                result = fut.result()
            except Exception as e:  # noqa: BLE001
                print(f"  [ERR] {qid} raised: {e}")
                result = {"question_id": qid, "passed": False, "passed_source": None,
                          "hypothesis_results": [], "question_type": ""}
            done += 1
            results.append(result)
            verified[qid] = result
            src = result.get("passed_source", "?")
            print(f"  [{done}/{len(jobs)}] {qid} {'PASS' if result['passed'] else 'FAIL'} via={src}")
            if done % 10 == 0 or done == len(jobs):
                json.dump({"results": list(verified.values())}, open(progress_file, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=2)

    elapsed = time.time() - t0
    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    type_stats = {}
    for r in results:
        t = r.get("question_type", "unknown")
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
    print(f"BYOK LongMemEval Judge Complete (elapsed {elapsed:.0f}s) | judge={judge.model}")
    print(f"{'=' * 60}")
    print(f"Score: {passed}/{total} = {100.0 * passed / total:.2f}%")
    print("Per-type:")
    for t, s in sorted(type_stats.items()):
        acc = 100.0 * s["correct"] / s["total"] if s["total"] else 0
        print(f"  {t:24} {s['correct']}/{s['total']} = {acc:.2f}%")
    print(f"Passed by source: {source_stats}")
    print(f"Judge calls success/fail: {judge.success}/{judge.fail} | cost ${judge.cost:.4f}")

    json.dump({
        "meta": {
            "package": "N1Mem-BYOK", "pillar": "longmemeval",
            "mode": "judge-only-on-frozen-hypotheses",
            "judge_model": judge.model, "judge_endpoint": "openrouter.ai/api/v1",
            "judge_prompt": "identical to T1Mem internal LME anscheck (task-specific)",
            "frozen_hypotheses_file": os.path.basename(args.input),
            "gold_file": os.path.basename(args.gold),
            "total_judged": total, "passed": passed, "failed": total - passed,
            "score_pct": round(100.0 * passed / total, 2),
            "elapsed_s": round(elapsed, 1), "judge_call_success": judge.success,
            "judge_call_fail": judge.fail, "total_cost_usd": round(judge.cost, 4),
            "note": "Single-best frozen hypothesis per question. OR across multi-model hypotheses reproduces the higher published OR number.",
        },
        "type_accuracy": {t: round(100.0 * s["correct"] / s["total"], 2) for t, s in type_stats.items()},
        "source_stats": source_stats, "results": results,
    }, open(out_file, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nSaved to {out_file}")


def _judge_question(judge, v_exec, qid, g, hyps):
    question = g.get("question", "")
    answer = g.get("answer", "")
    qtype = g.get("type", "multi-session")
    abstain = ("unanswerable" in str(answer).lower()) or (g.get("abstention"))
    all_results = []
    passed = False
    passed_source = None
    for source, hyp in hyps:
        jp = get_anscheck_prompt(qtype, question, answer, hyp[:HYP_TRUNCATE], abstention=abstain)
        futures = [v_exec.submit(judge.judge_one, jp) for _ in range(5)]
        votes = [f.result() for f in futures]
        hyp_passed = sum(votes) >= 3
        all_results.append({"source": source, "votes": votes, "vote_count": sum(votes),
                            "passed": hyp_passed, "hyp_preview": hyp[:200]})
        if hyp_passed and not passed:
            passed = True
            passed_source = source
    return {"question_id": qid, "question_type": qtype, "passed": passed,
            "passed_source": passed_source, "hypothesis_results": all_results}


if __name__ == "__main__":
    main()
