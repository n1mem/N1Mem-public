#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the gold-answer mapping for LongMemEval from the OFFICIAL dataset.

T1Mem does not redistribute the LongMemEval test set. The official data is public
(Microsoft LongMemEval, HuggingFace/GitHub). You download it yourself and run this
once to extract {question_id: {question, answer, type}} — the only gold fields the
BYOK judge needs. This keeps the package BYOK-clean (no bundled proprietary data).

Usage:
  python longmemeval/build_gold.py --data path/to/longmemeval.json --out longmemeval/inputs/lme_gold.json
  python longmemeval/build_gold.py --data path/to/longmemeval_dir/ --out longmemeval/inputs/lme_gold.json

The official sample schema uses keys: question_id, question, answer, type
(falls back to question_type). Unknown extra fields are ignored.
"""
import json
import os
import argparse
import glob


def load_official(path):
    """Load official samples from a json file or a directory of json/jsonl."""
    samples = []
    if os.path.isdir(path):
        files = sorted(glob.glob(os.path.join(path, "*.json")) +
                       glob.glob(os.path.join(path, "*.jsonl")))
    else:
        files = [path]
    for f in files:
        if f.endswith(".jsonl"):
            for line in open(f, encoding="utf-8"):
                line = line.strip()
                if line:
                    samples.append(json.loads(line))
        else:
            d = json.load(open(f, encoding="utf-8"))
            if isinstance(d, dict):
                # some releases nest under a key
                for v in d.values():
                    if isinstance(v, list):
                        samples.extend(v)
                        break
                else:
                    samples.append(d)
            else:
                samples.extend(d)
    return samples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="Official LongMemEval json file or directory")
    ap.add_argument("--out", required=True, help="Output gold mapping json")
    args = ap.parse_args()

    samples = load_official(args.data)
    gold = {}
    skipped = 0
    for s in samples:
        qid = s.get("question_id")
        if not qid:
            skipped += 1
            continue
        gold[qid] = {
            "question": s.get("question", ""),
            "answer": s.get("answer", ""),
            "type": s.get("type", s.get("question_type", "multi-session")),
        }
    print(f"[build_gold] Loaded {len(samples)} samples, built gold for {len(gold)} "
          f"questions ({skipped} skipped: no question_id)")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    json.dump(gold, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[build_gold] Wrote {args.out}")


if __name__ == "__main__":
    main()
