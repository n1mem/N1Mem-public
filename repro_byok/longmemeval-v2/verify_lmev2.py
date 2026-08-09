#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_lmev2.py — N1Mem LME-V2 冻结结果零依赖校验

做什么：
  [1] 校验 LME-V2 三个冻结结果文件的 SHA256。
  [2] 从文件中重算 correct / total / accuracy，验证与 claim_card.json 一致：
        - 4-model lazy OR: 283/451 = 62.7%
        - DS-V4-Flash 单模型: 200/451 = 44.3%
        - 历史基线: 190/451 = 42.1%

注意：LME-V2 是完整端到端基准（检索 + Reader + Judge），第三方独立重跑需要
      N1Mem 引擎（暂未开源）。本脚本提供的是「冻结结果完整性 + 分数可重算」验证。

运行：  python verify_lmev2.py
退出码：0=通过，1=失败
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
INPUTS = os.path.join(ROOT, "inputs")

# 发布值（与 claim_card.json 一致）
EXPECTED = {
    "lmev2_4model_lazy_or_result.json": {
        "sha256": "5780da66d715101fc693ccc08cca8233cf6b60cb5dea375a1642f062464f957c",
        "expected_correct": 283,
        "expected_total": 451,
        "expected_accuracy": 0.627,
    },
    "lmev2_flash_single_result.json": {
        "sha256": "abcd6dd23b457d5335da90ea5aa1bc04709bea14c42d39f3fbd1c2925a916fdd",
        "expected_correct": 200,
        "expected_total": 451,
        "expected_accuracy": 0.443,
    },
    "lmev2_historical_baseline_result.json": {
        "sha256": "66de748ac4ff18027cc71df1b6728e1fdca3362b6ac856d5ebd833ea16b0cd85",
        "expected_correct": 190,
        "expected_total": 451,
        "expected_accuracy": 0.421,
    },
}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def count_correct(data):
    """LME-V2 里 score=0 表示正确。"""
    total = len(data.get("results", []))
    correct = sum(1 for r in data.get("results", []) if r.get("score", 1) == 0)
    return correct, total


def check():
    print("=" * 64)
    print("N1Mem LME-V2 · 冻结结果校验 (verify_lmev2.py)")
    print("=" * 64)
    ok = True
    for fname, meta in EXPECTED.items():
        p = os.path.join(INPUTS, fname)
        print(f"\n[校验] {fname}")
        if not os.path.exists(p):
            print(f"  [FAIL] 文件缺失: {fname}")
            ok = False
            continue

        actual_sha = sha256_of(p)
        sha_good = actual_sha == meta["sha256"]
        print(f"  SHA256: {'OK ' if sha_good else 'FAIL'} ({actual_sha})")
        ok = ok and sha_good

        data = json.load(open(p, encoding="utf-8"))
        correct, total = count_correct(data)
        acc = correct / total if total else 0.0
        acc_good = abs(acc - meta["expected_accuracy"]) < 0.005
        correct_good = correct == meta["expected_correct"] and total == meta["expected_total"]
        print(f"  重算分数: {correct}/{total} = {acc*100:.2f}%")
        print(f"  发布值:   {meta['expected_correct']}/{meta['expected_total']} = {meta['expected_accuracy']*100:.1f}%")
        print(f"  分数校验: {'OK' if (acc_good and correct_good) else 'WARN'}")
        ok = ok and acc_good and correct_good

    print("\n" + "=" * 64)
    print(f"结果: {'PASS ✅' if ok else 'FAIL ❌'}")
    print("=" * 64)
    return ok


if __name__ == "__main__":
    ok = check()
    sys.exit(0 if ok else 1)
