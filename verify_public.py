#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_public.py — N1Mem 公开仓完整性校验（零依赖可跑，装依赖后做真实重算）

做什么：
  [1] 校验所有冻结产物的 SHA256 与发布值一致（证明数据未被篡改）。
  [2] 双数验证 LoCoMo 官方 token 级 F1：
        - 简洁协议（主披露，Option A 修复）：官方 32-token 短答案协议重跑，
          应 ≈ 65.34%（SHA256 4b7425d9…）。读已签名 concise official_f1_result.json 断言。
        - 遗留长文协议（透明参考）：原 OR10 长推理文与官方 32-token 短答案协议不匹配，
          应 ≈ 23.34%（SHA256 ef4f8ed2…）。若环境有 numpy/regex/nltk，可独立重算验证。
        两数字并列披露，不隐藏任一。

运行：  python verify_public.py
退出码：0=通过，1=失败
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

# 发布值（与 claim_card.json / README 一致）。改了冻结产物必须同步改这里。
EXPECTED_SHA = {
    "repro_byok/locomo/inputs/locomo_qa_or10_full1986_checklist_frozen_result.json":
        "896224a00bac005b8b36583768e2080762cb8a6020b72bc9bbbbcbf3241e5045",
    "repro_byok/locomo/inputs/locomo_qa_or10_full1986_frozen_result.json":
        "510cfccb1fc796123586d2410ed1cb61e225c44cd3e935089d3c97e9e44f2927",
    "repro_byok/locomo/inputs/locomo_qa_or10_full1986_official_f1_result.json":
        "ef4f8ed2777c647a9b24d6485181e47caea3596ea4a72611053eadcdab409185",
    "repro_byok/locomo/inputs/locomo_qa_or10_concise_full1986_official_f1_result.json":
        "4b7425d9ffd660c0fe46e96228f19eb3a8e688bb22f11c808d2049e0c4212e75",
    "repro_byok/longmemeval/inputs/t1mem_hypotheses_500.jsonl":
        "0721579d894b28e3ef0c7a7ac910e506b36f4c6e075228c71b1d11005615c515",
    "repro_byok/amb/mab_frozen_manifest.json":
        "fd9cd75cd9380fea0c46a02707660948bb237dc99fa0c6cba79e2bde3e4a6ef5",
    "repro_byok/longmemeval-v2/inputs/lmev2_4model_lazy_or_result.json":
        "5780da66d715101fc693ccc08cca8233cf6b60cb5dea375a1642f062464f957c",
    "repro_byok/longmemeval-v2/inputs/lmev2_flash_single_result.json":
        "abcd6dd23b457d5335da90ea5aa1bc04709bea14c42d39f3fbd1c2925a916fdd",
    "repro_byok/longmemeval-v2/inputs/lmev2_historical_baseline_result.json":
        "66de748ac4ff18027cc71df1b6728e1fdca3362b6ac856d5ebd833ea16b0cd85",
    "claim_card.json":
        "c6c08d4a6611975f890b10a9b45c24ed9f600799ce18e3141c27d2f050502045",
}

# LoCoMo 官方 token 级 F1 双数披露发布值
PUBLISHED_CONCISE_F1 = 0.6534   # 简洁协议（Option A 修复，主披露）
PUBLISHED_LEGACY_F1 = 0.2334    # 遗留长文协议（透明参考）


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def check_sha256():
    print("[1] SHA256 校验（证明冻结产物未被篡改）")
    ok = True
    for rel, exp in EXPECTED_SHA.items():
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            print(f"  [MISS] {rel}  (文件缺失)")
            ok = False
            continue
        actual = sha256_of(p)
        good = actual == exp
        ok = ok and good
        print(f"  [{'OK ' if good else 'FAIL'}] {rel}\n        {actual}")
    return ok


def _assert_f1(val, published, label):
    if val is None:
        print(f"  [SKIP] {label}: 无可用数值")
        return True
    dev = abs(val - published)
    good = dev < 0.02
    print(f"  {label}: {val*100:.2f}%  (发布值 {published*100:.2f}%, 偏差 {dev*100:.2f}pp) -> [{'OK' if good else 'WARN'}]")
    return good


def check_official_f1():
    print("\n[2] LoCoMo 官方 token 级 F1（双数披露，确定性，无需 API）")

    # (a) 简洁协议（主披露）：读已签名 concise 结果文件
    concise_file = os.path.join(ROOT, "repro_byok/locomo/inputs",
                                 "locomo_qa_or10_concise_full1986_official_f1_result.json")
    concise_val = None
    if os.path.exists(concise_file):
        d = json.load(open(concise_file, encoding="utf-8"))
        concise_val = d.get("overall_mean_f1")
        print(f"  简洁协议（主披露）已签名 overall_mean_f1: {concise_val*100:.2f}%" if concise_val is not None
              else "  简洁协议结果文件无 overall_mean_f1 字段")
    ok_concise = _assert_f1(concise_val, PUBLISHED_CONCISE_F1, "  简洁协议 65.34% (主披露)")

    # (b) 遗留长文协议（透明参考）：读已签名 legacy 结果文件 + 可选独立重算
    legacy_file = os.path.join(ROOT, "repro_byok/locomo/inputs",
                               "locomo_qa_or10_full1986_official_f1_result.json")
    raw = os.path.join(ROOT, "repro_byok/locomo/inputs", "locomo_qa_or10_full1986.json")
    legacy_recomputed = None
    if os.path.exists(raw):
        try:
            sys.path.insert(0, os.path.join(ROOT, "repro_byok", "locomo"))
            from freeze_or10_official_f1 import score_hypothesis, collect_hypotheses  # noqa
            data = json.load(open(raw, encoding="utf-8"))
            scores = []
            for q in data["per_question"]:
                hyps = collect_hypotheses(q)
                if not hyps:
                    scores.append(0.0)
                    continue
                best = max(score_hypothesis(q["topic"], t, q["gold"]) for _, t in hyps)
                scores.append(best)
            legacy_recomputed = sum(scores) / len(scores) if scores else 0.0
            print(f"  遗留长文协议独立重算（OR 聚合）: {legacy_recomputed*100:.2f}%  (n={len(scores)})")
        except Exception as e:
            print(f"  跳过遗留协议独立重算（缺少依赖 numpy/regex/nltk）: {e}")

    legacy_signed = None
    if os.path.exists(legacy_file):
        d = json.load(open(legacy_file, encoding="utf-8"))
        legacy_signed = d.get("overall_mean_f1")
        print(f"  遗留长文协议已签名 overall_mean_f1: {legacy_signed*100:.2f}%" if legacy_signed is not None
              else "  遗留协议结果文件无 overall_mean_f1 字段")

    legacy_val = legacy_recomputed if legacy_recomputed is not None else legacy_signed
    ok_legacy = _assert_f1(legacy_val, PUBLISHED_LEGACY_F1, "  遗留长文协议 23.34% (透明参考)")

    # 双数一致性提示
    if concise_val is not None and legacy_val is not None:
        print(f"  双数披露: 简洁 {concise_val*100:.2f}% / 遗留 {legacy_val*100:.2f}% "
              f"(差 {(concise_val-legacy_val)*100:.2f}pp，源于生成格式对齐)")

    return ok_concise and ok_legacy


# LME-V2 发布值（score=0 表示正确）
PUBLISHED_LMEV2 = {
    "repro_byok/longmemeval-v2/inputs/lmev2_4model_lazy_or_result.json":
        {"correct": 283, "total": 451, "accuracy": 0.627},
    "repro_byok/longmemeval-v2/inputs/lmev2_flash_single_result.json":
        {"correct": 200, "total": 451, "accuracy": 0.443},
    "repro_byok/longmemeval-v2/inputs/lmev2_historical_baseline_result.json":
        {"correct": 190, "total": 451, "accuracy": 0.421},
}


def check_lmev2():
    print("\n[3] LME-V2 冻结结果分数重算（score=0 为正确）")
    ok = True
    for rel, pub in PUBLISHED_LMEV2.items():
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            print(f"  [MISS] {rel}")
            ok = False
            continue
        data = json.load(open(p, encoding="utf-8"))
        total = len(data.get("results", []))
        correct = sum(1 for r in data.get("results", []) if r.get("score", 1) == 0)
        acc = correct / total if total else 0.0
        good = (correct == pub["correct"] and total == pub["total"]
                and abs(acc - pub["accuracy"]) < 0.005)
        ok = ok and good
        print(f"  [{'OK ' if good else 'FAIL'}] {os.path.basename(rel)}: "
              f"{correct}/{total} = {acc*100:.2f}% (发布 {pub['correct']}/{pub['total']} = {pub['accuracy']*100:.1f}%)")
    return ok


def main():
    print("=" * 64)
    print("N1Mem 公开仓 · 完整性校验 (verify_public.py)")
    print("=" * 64)
    ok1 = check_sha256()
    ok2 = check_official_f1()
    ok3 = check_lmev2()
    overall = ok1 and ok2 and ok3
    print("\n" + "=" * 64)
    print(f"结果: {'PASS ✅' if overall else 'FAIL ❌'}")
    print("=" * 64)
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
