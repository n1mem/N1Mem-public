#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B7 — per-dim best 自动化流水线 (P2-3)
=====================================
把 MAB 四维各自最优组合 (per-dimension best) 的手工估算流程固化为可重跑脚本：

  ① 配置发现   (config discovery) : 读取 composite_spec.json 四维 best 配置 + 已验证成绩
  ② 组合 manifest (composite)     : simple_average 计算组合成绩, 写 mab_composite_manifest.json
  ③ SHA 冻结   (SHA freeze)       : 对 manifest 文件计算 SHA256, 作为对外可验证指纹
  ④ claim_card 同步 (claim sync)   : 把组合成绩/维度分/SHA 同步进 claim_card.json 的 MAB 行

零 API 调用、零新授权，全部基于在案已验证成绩 (符合 C2 成本铁律)。
claim_card 同步默认 dry-run 打印 diff；加 --apply-claim 才真写 (对外口径铁律: 先披露再执行)。

用法:
  python build_mab_composite.py            # 写 manifest + 算 SHA + 打印 claim diff (不写 claim)
  python build_mab_composite.py --apply-claim   # 上述 + 实际写回 claim_card.json
"""
import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC_PATH = os.path.join(HERE, "composite_spec.json")
MANIFEST_PATH = os.path.join(HERE, "mab_composite_manifest.json")
CLAIM_PATH = os.path.join(HERE, "..", "..", "claim_card.json")


def load_spec():
    with open(SPEC_PATH, encoding="utf-8") as f:
        return json.load(f)


def discover_configs(spec):
    """① 配置发现: 列出 spec 引用的四维 best 配置, 校验存在性。"""
    found = []
    for dim, d in spec["dimensions"].items():
        cfg = d.get("config")
        cfg_path = os.path.join(HERE, cfg) if cfg else None
        exists = os.path.exists(cfg_path) if cfg_path else False
        found.append((dim, cfg, exists))
    return found


def build_manifest(spec):
    """② 组合 manifest: 算 simple_average, 拼装与历史结构对齐的 manifest dict。"""
    dims = spec["dimensions"]
    scores = {k: float(v["score"]) for k, v in dims.items()}
    simple_avg = round(sum(scores.values()) / len(scores), 2)
    manifest = {
        "title": "T1Mem MemoryAgentBench (MAB) Composite Best-per-Dimension Results",
        "composite_at": spec["composite_at"],
        "benchmark": spec["benchmark"],
        "config_strategy": spec["config_strategy"],
        "stack_note": spec["stack_note"],
        "judge": spec["judge"],
        "total_questions": spec["total_questions"],
        "scores": {**scores, "simple_average": simple_avg},
        "dimension_source": dims,
        "vs_frozen": {
            "frozen_simple_average": spec["frozen_simple_average"],
            "composite_simple_average": simple_avg,
            "delta_pp": round(simple_avg - spec["frozen_simple_average"], 2),
        },
        "baseline_comparison": spec["baseline_comparison"],
        "frozen_manifest_sha256": spec["frozen_manifest_sha256"],
    }
    return manifest, simple_avg


def sha256_of_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_manifest(manifest):
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    return text, sha256_of_text(text)


def sync_claim(manifest, simple_avg, sha, apply=False):
    """④ claim_card 同步: 更新 MAB 行的组合成绩/维度分/manifest SHA。"""
    with open(CLAIM_PATH, encoding="utf-8") as f:
        claim = json.load(f)

    target = None
    for b in claim["benchmarks"]:
        if b.get("id") == "memoryagentbench":
            target = b
            break
    if target is None:
        print("[claim] ERROR: claim_card.json 中找不到 memoryagentbench 行", file=sys.stderr)
        return False

    dims = manifest["scores"]
    new_dim_scores = {k: dims[k] for k in ("AR", "CR", "TTL", "LRU")}
    new_headline = simple_avg
    new_sha = sha

    # 找到 frozen_artifacts 中 role==manifest_composite 的条目
    comp_artifact = None
    for a in target.get("frozen_artifacts", []):
        if a.get("role") == "manifest_composite":
            comp_artifact = a
            break

    old_headline = target.get("headline_score_pct")
    old_dim = target.get("dimension_scores")
    old_sha = comp_artifact.get("sha256") if comp_artifact else None

    diffs = []
    if old_headline != new_headline:
        diffs.append(f"  headline_score_pct: {old_headline} -> {new_headline}")
    if old_dim != new_dim_scores:
        diffs.append(f"  dimension_scores: {old_dim} -> {new_dim_scores}")
    if old_sha != new_sha:
        diffs.append(f"  frozen_artifacts[manifest_composite].sha256:\n    {old_sha}\n    -> {new_sha}")

    if not diffs:
        print("[claim] 已是最新, 无需变更 (dry-run 无 diff)")
        return True

    print("[claim] 待同步变更 (dry-run):")
    for d in diffs:
        print(d)

    if not apply:
        print("[claim] (dry-run 模式, 未写入。加 --apply-claim 执行实际写入)")
        return True

    # apply: 备份 + 写入
    bak = CLAIM_PATH + ".bak"
    with open(bak, "w", encoding="utf-8") as f:
        with open(CLAIM_PATH, encoding="utf-8") as src:
            f.write(src.read())
    target["headline_score_pct"] = new_headline
    target["headline_detail"] = "四维 simple average（组合口径：per-dimension best 双栈）"
    target["dimension_scores"] = new_dim_scores
    if comp_artifact is not None:
        comp_artifact["sha256"] = new_sha
    with open(CLAIM_PATH, "w", encoding="utf-8") as f:
        json.dump(claim, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[claim] 已写入 claim_card.json (备份: {os.path.basename(bak)})")
    return True


def main():
    ap = argparse.ArgumentParser(description="B7 per-dim best 自动化流水线")
    ap.add_argument("--apply-claim", action="store_true",
                    help="实际写回 claim_card.json (默认仅 dry-run 打印 diff)")
    args = ap.parse_args()

    print("=" * 60)
    print("B7 per-dim best 自动化流水线")
    print("=" * 60)

    # ① 配置发现
    spec = load_spec()
    print("\n[① 配置发现] 四维 best 配置:")
    for dim, cfg, exists in discover_configs(spec):
        mark = "OK" if exists else "MISSING"
        print(f"  {dim:4s} {spec['dimensions'][dim]['score']:6.2f}  [{mark}] {cfg or '(无)'}")

    # ② 组合 manifest
    manifest, simple_avg = build_manifest(spec)
    print(f"\n[② 组合 manifest] 四维 simple_average = {simple_avg}%  (vs 冻结 {spec['frozen_simple_average']}%, delta {manifest['vs_frozen']['delta_pp']:+.2f}pp)")

    # ③ SHA 冻结
    text, sha = write_manifest(manifest)
    print(f"[③ SHA 冻结] 写入 {os.path.relpath(MANIFEST_PATH, HERE)}")
    print(f"         manifest sha256 = {sha}")

    # ④ claim_card 同步
    print()
    sync_claim(manifest, simple_avg, sha, apply=args.apply_claim)

    print("\n完成。")


if __name__ == "__main__":
    main()
