#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the merged OR10 hypothesis set = frozen LoCoMo reader artifact.

Merges:
  1. OR3 base  (Qwen3.7-Max / GLM-5.2 / DS-V4-Pro outputs)  -- locomo_qa_or3_full1986.json
  2. 7 rescue experiments' rescue hypotheses (new_hyp / best_hyp) -- docs/bench/locomo_or*_result.json
  3. Master question text + gold answer  -- locomo_mc10.json (LoCoMo raw dataset)

Output: repro_byok/locomo/inputs/locomo_qa_or10_full1986.json
  schema per question:
    {
      "question_id", "topic", "question", "gold",
      "qwen_hypothesis", "glm_hypothesis", "ds_hypothesis",
      "rescue_hypotheses": [ {"source": "<file>", "text": "..."}, ... ]
    }

This is the FROZEN reader artifact. The judge (gpt-4o-mini) is re-run separately by
freeze_or10.py so an external party can reproduce the honest frozen 93.35% under their own key (BYOK).

Key facts verified before building:
  - master (1986) == OR3 base (1986) qids, 100% aligned
  - gold (OR3 answer_text) == master answer, 0 mismatch in spot check
  - topic == question_type exactly (5 types)
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))  # D:/Project/T1Mem
BENCH = os.path.join(ROOT, "T1Mem", "docs", "bench")
REPRO = os.path.join(ROOT, "T1Mem", "repro_byok", "locomo")
RAW = os.path.join(ROOT, "T1Mem", "data", "bench", "locomo_raw", "data", "locomo_mc10.json")

OR3_FILE = os.path.join(REPRO, "inputs", "locomo_qa_or3_full1986.json")
OUT_FILE = os.path.join(REPRO, "inputs", "locomo_qa_or10_full1986.json")

RESCUE_FILES = [
    "locomo_or4_full283_result.json",
    "locomo_or5_od64_result.json",
    "locomo_or5_other94_result.json",
    "locomo_or6_full_result.json",
    "locomo_or7_multihop_result.json",
    "locomo_or9_multihop_result.json",
    "locomo_or10_adversarial_result.json",
]


def load_master():
    m = {}
    for ln in open(RAW, encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        o = json.loads(ln)
        m[o["question_id"]] = o
    return m


def extract_rescue_hyps(rec):
    """Return list of (text) rescue hypotheses from a rescue-file result record."""
    hyps = []
    # direct new_hyp
    if rec.get("new_hyp") and rec["new_hyp"].strip():
        hyps.append(rec["new_hyp"])
    # best_hyp (or9/or10)
    if rec.get("best_hyp") and rec["best_hyp"].strip():
        hyps.append(rec["best_hyp"])
    # variant_results (or9/or10)
    for vr in rec.get("variant_results", []) or []:
        h = vr.get("new_hyp")
        if h and h.strip():
            hyps.append(h)
    # dedupe preserving order
    seen, out = set(), []
    for h in hyps:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def main():
    master = load_master()
    or3 = json.load(open(OR3_FILE, encoding="utf-8"))
    pq3 = or3["per_question"]
    print(f"[build] master={len(master)}  or3={len(pq3)}")

    # index rescue hyps by qid
    rescue_by_qid = {}
    total_rescue = 0
    for fname in RESCUE_FILES:
        p = os.path.join(BENCH, fname)
        if not os.path.exists(p):
            print(f"  [warn] missing rescue file: {fname}")
            continue
        d = json.load(open(p, encoding="utf-8"))
        for rec in d.get("results", []):
            qid = rec.get("qid") or rec.get("question_id")
            if not qid:
                continue
            hyps = extract_rescue_hyps(rec)
            if hyps:
                rescue_by_qid.setdefault(qid, []).extend(
                    {"source": fname, "text": h} for h in hyps
                )
                total_rescue += len(hyps)
    print(f"[build] rescue qids={len(rescue_by_qid)}  total_rescue_hyps={total_rescue}")

    merged = []
    missing_q = 0
    for q in pq3:
        qid = q["question_id"]
        mq = master.get(qid)
        if not mq:
            missing_q += 1
            question = ""
            gold = q.get("answer_text", "")
        else:
            question = mq.get("question", "")
            gold = mq.get("answer", q.get("answer_text", ""))
        rescues = rescue_by_qid.get(qid, [])
        merged.append({
            "question_id": qid,
            "topic": q.get("topic", mq.get("question_type", "")),
            "question": question,
            "gold": gold,
            "qwen_hypothesis": q.get("qwen_hypothesis", ""),
            "glm_hypothesis": q.get("glm_hypothesis", ""),
            "ds_hypothesis": q.get("ds_hypothesis", ""),
            "rescue_hypotheses": rescues,
        })
    print(f"[build] merged={len(merged)}  missing_master_q={missing_q}")

    # stats
    n_with_rescue = sum(1 for m in merged if m["rescue_hypotheses"])
    total_hyp = sum(
        1 + (1 if m["glm_hypothesis"] else 0) + (1 if m["ds_hypothesis"] else 0)
        + len(m["rescue_hypotheses"])
        for m in merged
    )
    # per-type rescue count
    from collections import Counter
    tc = Counter(m["topic"] for m in merged)
    rc = Counter(m["topic"] for m in merged if m["rescue_hypotheses"])
    print(f"[build] questions_with_rescue={n_with_rescue}")
    print(f"[build] total_hypotheses={total_hyp}  (est judge calls x5 = {total_hyp*5:,})")
    print(f"[build] per-type: {dict(tc)}")
    print(f"[build] per-type w/ rescue: {dict(rc)}")

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    json.dump(
        {
            "meta": {
                "build": "OR10 merged hypothesis set (frozen reader artifact)",
                "base": "locomo_qa_or3_full1986.json (Qwen3.7-Max/GLM-5.2/DS-V4-Pro)",
                "rescue_experiments": RESCUE_FILES,
                "master_source": "locomo_mc10.json (LoCoMo raw, 1986 QA)",
                "n_questions": len(merged),
                "n_with_rescue": n_with_rescue,
                "total_hypotheses": total_hyp,
                "judge_target": "openai/gpt-4o-mini (LoCoMo de-facto standard)",
                "expected_score": 93.35,  # OR10 x gpt-4o-mini, clean re-judge (freeze_or10.py). NOTE: original 96.48% (loose OR3 markers + rescue votes) is NOT reproducible.
                "note": "Reader outputs are FIXED artifacts. Only the judge is re-executed (BYOK).",
            },
            "per_question": merged,
        },
        open(OUT_FILE, "w", encoding="utf-8"),
        ensure_ascii=False,
        indent=2,
    )
    print(f"[build] SAVED -> {OUT_FILE}")
    print(f"[build] size = {os.path.getsize(OUT_FILE):,} bytes")


if __name__ == "__main__":
    main()
