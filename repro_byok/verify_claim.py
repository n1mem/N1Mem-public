#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate a BYOK reproduction result and emit a comparable claim summary.

This is the neutral, third-party-friendly checker. A reproducer runs a pillar
script, then runs THIS to (a) confirm the result matches the expected schema,
(b) print the reproduced score, and (c) compute a deterministic CLAIM HASH over
the verdicts (excluding volatile fields like cost/elapsed), so the result can be
independently compared to T1Mem's published number.

Usage:
  python verify_claim.py --pillar locomo      --result locomo/locomo_byok_result.json
  python verify_claim.py --pillar longmemeval --result longmemeval/longmemeval_byok_result.json
  python verify_claim.py --pillar amb         --result amb/amb_byok_result.json
"""
import os
import sys
import json
import argparse
import hashlib

HERE = os.path.dirname(os.path.abspath(__file__))


def load_schema(pillar):
    path = os.path.join(HERE, pillar, "result_schema.json")
    return json.load(open(path, encoding="utf-8"))


def validate(result, schema):
    """Lightweight structural validation (no jsonschema dependency)."""
    errors = []
    required_top = schema.get("required", [])
    for k in required_top:
        if k not in result:
            errors.append(f"missing top-level key: {k}")
    # results array shape (locomo/longmemeval)
    if "results" in result:
        if not isinstance(result["results"], list):
            errors.append("'results' must be a list")
        else:
            item_req = (schema.get("properties", {})
                        .get("results", {}).get("items", {}).get("required", []))
            for i, it in enumerate(result["results"][:5]):
                for rk in item_req:
                    if rk not in it:
                        errors.append(f"results[{i}] missing '{rk}'")
    # amb dimensions
    if "dimensions" in result:
        for d in ("AR", "CR", "TTL", "LRU"):
            if d not in result["dimensions"]:
                errors.append(f"dimensions missing '{d}'")
    return errors


def claim_hash(result, pillar):
    """Deterministic SHA256 over the verdicts (volatile meta excluded)."""
    if pillar in ("locomo", "longmemeval"):
        verdicts = sorted(
            {r["question_id"]: bool(r.get("passed")) for r in result.get("results", [])}.items()
        )
        blob = json.dumps({"pillar": pillar, "verdicts": verdicts},
                          sort_keys=True, ensure_ascii=False)
    else:  # amb
        dims = {k: result.get("dimensions", {}).get(k, {}).get("score")
                for k in ("AR", "CR", "TTL", "LRU")}
        blob = json.dumps({"pillar": pillar, "dimensions": dims},
                          sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pillar", required=True, choices=["locomo", "longmemeval", "amb"])
    ap.add_argument("--result", required=True)
    args = ap.parse_args()

    if not os.path.exists(args.result):
        print(f"[ERROR] result file not found: {args.result}")
        sys.exit(2)

    schema = load_schema(args.pillar)
    result = json.load(open(args.result, encoding="utf-8"))

    errors = validate(result, schema)
    if errors:
        print("[VALIDATION] FAILED:")
        for e in errors:
            print(f"   - {e}")
        sys.exit(3)
    print("[VALIDATION] OK — result matches the pillar schema.")

    print(f"\n=== T1Mem BYOK Claim — {args.pillar} ===")
    if args.pillar in ("locomo", "longmemeval"):
        meta = result.get("meta", {})
        total = meta.get("total_judged") or len(result.get("results", []))
        passed = meta.get("passed")
        if passed is None:
            passed = sum(1 for r in result.get("results", []) if r.get("passed"))
        score = 100.0 * passed / total if total else 0
        print(f"  Judge model : {meta.get('judge_model')}")
        print(f"  Score       : {passed}/{total} = {score:.2f}%")
        print(f"  Per-type    : {result.get('type_accuracy', {})}")
    else:  # amb
        dims = result.get("dimensions", {})
        scores = [d.get("score") for d in dims.values() if isinstance(d, dict) and d.get("score") is not None]
        print(f"  Dimensions  : {dims}")
        if scores:
            print(f"  Simple mean : {sum(scores)/len(scores):.2f}%")

    h = claim_hash(result, args.pillar)
    print(f"\n  Claim hash  : {h}")
    print("  (T1Mem publishes the expected score range; compare your Score above to it.)")


if __name__ == "__main__":
    main()
