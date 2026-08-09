#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the LoCoMo OR10 freeze report (HTML) — HONEST version.

Reads the frozen result + manifest + source files, and computes the discrepancy
between the originally-claimed 96.48% and the reproducible fresh re-judge 93.35%.
"""
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.join(HERE, "..", "..", "..", "T1Mem", "docs", "bench")
RES = os.path.join(HERE, "inputs", "locomo_qa_or10_full1986_frozen_result.json")
MAN = os.path.join(HERE, "inputs", "locomo_qa_or10_full1986_frozen_manifest.json")
OR3 = os.path.join(HERE, "inputs", "locomo_qa_or3_full1986.json")
OUTDIR = os.path.join(HERE, "docs")
os.makedirs(OUTDIR, exist_ok=True)

res = json.load(open(RES, encoding="utf-8"))
man = json.load(open(MAN, encoding="utf-8"))
meta = res["meta"]
ta = res.get("type_accuracy", {})
ss = res.get("source_stats", {})
score = meta["score_pct"]
passed = meta["passed"]
total = meta["n_questions"]
today = time.strftime("%Y-%m-%d")

# ---- discrepancy analysis ----
or3 = json.load(open(OR3, encoding="utf-8"))
or3_meta_acc = or3.get("or3_accuracy")
or3_meta_correct = or3.get("or3_correct")
or3_or_correct = sum(1 for q in or3["per_question"] if q.get("or_correct"))

# fresh OR3-only & rescue-only from frozen result
or3_only = rescue_only = both = 0
for r in res["results"]:
    hr = r.get("hypothesis_results", [])
    o = any(h["source"] in ("qwen", "glm", "ds") and h["passed"] for h in hr)
    rv = any(h["source"].startswith("rescue") and h["passed"] for h in hr)
    if o and not rv: or3_only += 1
    elif rv and not o: rescue_only += 1
    elif o and rv: both += 1

# stored rescue passes
RESCUE = ["locomo_or4_full283_result.json", "locomo_or5_od64_result.json",
          "locomo_or5_other94_result.json", "locomo_or6_full_result.json",
          "locomo_or7_multihop_result.json", "locomo_or9_multihop_result.json",
          "locomo_or10_adversarial_result.json"]
stored_rescue = set()
for f in RESCUE:
    d = json.load(open(os.path.join(BENCH, f), encoding="utf-8"))
    for r in d.get("results", []):
        qid = r.get("qid") or r.get("question_id")
        if not qid:
            continue
        p = r.get("passed", False)
        for vr in r.get("variant_results", []) or []:
            if vr.get("passed"):
                p = True
        if p:
            stored_rescue.add(qid)

orig_claim = 96.48
orig_claim_n = round(orig_claim / 100 * total)  # 1916
gap = orig_claim - score

# per-type table
type_rows = "".join(f"<tr><td>{t}</td><td>{ta[t]:.2f}%</td></tr>\n" for t in sorted(ta))
src_rows = "".join(f"<tr><td>{s}</td><td>{c}</td></tr>\n" for s, c in sorted(ss.items(), key=lambda x: -x[1]))

html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>T1Mem LoCoMo OR10 冻结报告（诚实版）{today}</title>
<style>
  :root {{ --bg:#0d1117; --card:#161b22; --fg:#e6edf3; --muted:#8b949e;
          --accent:#3fb950; --accent2:#58a6ff; --border:#30363d; --warn:#d29922; --danger:#f85149; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg);
         font-family:-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
         line-height:1.6; padding:32px; }}
  .wrap {{ max-width:960px; margin:0 auto; }}
  h1 {{ font-size:24px; margin:0 0 4px; }}
  .sub {{ color:var(--muted); margin-bottom:24px; }}
  .card {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:20px 24px; margin:16px 0; }}
  .big {{ font-size:38px; font-weight:700; color:var(--accent); }}
  .big small {{ font-size:15px; color:var(--muted); font-weight:400; }}
  table {{ width:100%; border-collapse:collapse; margin:8px 0; }}
  th,td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--border); }}
  th {{ color:var(--muted); font-weight:600; font-size:13px; text-transform:uppercase; }}
  .tag {{ display:inline-block; background:#1f6feb22; color:var(--accent2); border:1px solid #1f6feb55;
         border-radius:6px; padding:2px 8px; font-size:12px; margin:2px; }}
  code {{ background:#1c2128; padding:2px 6px; border-radius:4px; font-size:13px; color:#ffa657; }}
  .mono {{ font-family:ui-monospace,monospace; font-size:12px; color:var(--muted); }}
  .banner {{ border-left:4px solid var(--accent); }}
  .warn {{ border-left:4px solid var(--warn); background:#2d2410; }}
  .danger {{ border-left:4px solid var(--danger); background:#2d1416; }}
  ul {{ margin:8px 0; padding-left:20px; }} li {{ margin:5px 0; }}
  .num {{ font-variant-numeric:tabular-nums; }}
</style></head>
<body><div class="wrap">

<h1>🧊 T1Mem LoCoMo OR10 冻结报告（诚实版）</h1>
<div class="sub">生成于 {today} · 支柱 1/3 · gpt-4o-mini（LoCoMo 官方事实标准 Judge）· 全量重判冻结</div>

<div class="card banner">
  <div class="big">{score:.2f}% <small>（{passed}/{total}）</small></div>
  <p style="margin:8px 0 0">LoCoMo MC10（1,986 题）OR10 假设集经 <b>openai/gpt-4o-mini</b> <b>全量重判（5 票/假设，≥3 通过，OR 并集）</b>冻结。
  这是<b>可 SHA256 校验、可 BYOK 复现</b>的诚实主口径。</p>
</div>

<div class="card danger">
  <h3>⚠️ 重要诚实性说明：原声明 96.48% 不可被干净重判复现</h3>
  <p>此前公开声明的 <b>96.48%（1916/1986）</b> 是「OR3 宽松正确标记 + 救援文件历史投票」合并值，
  <b>无法</b>被一次干净的 gpt-4o-mini 5 票重判复现。本次冻结的干净重判结果为 <b>{score:.2f}%（{passed}）</b>，
  与原声明相差 <b class="num">−{gap:.2f}pp</b>（{orig_claim_n - passed} 题）。</p>
  <p><b>根因（已定位）：</b></p>
  <ul>
    <li><b>OR3 基准被宽松标记污染</b>：随包 OR3 文件自身的 <code>or_correct</code> 标记 = <b>{or3_or_correct}</b>（{100*or3_or_correct/total:.2f}%），
        其 meta 写着 <code>or3_accuracy={or3_meta_acc}</code>。这些是早期宽松判定的「qwen∨glm∨ds 任一正确」标记，
        <b>并非</b>干净 gpt-4o-mini 5 票重判。真实重判 OR3-only = <b>{or3_only}</b>（{100*or3_only/total:.2f}%）。</li>
    <li><b>救援投票不可复现</b>：7 个救援文件历史记录 <b>{len(stored_rescue)}</b> 个 qid 曾「通过」，
        但同样假设经本次干净重判仅贡献 <b>{rescue_only}</b> 题通过（其余在 OR3 已通过或救援假设被标准 Judge 判否）。</li>
    <li><b>原 96.48% 的构成</b> = 宽松 OR3（{or3_or_correct}）+ 历史救援投票（{len(stored_rescue)}）∪ 去重 ≈ 1916。
        一旦改用干净 gpt-4o-mini 5 票重判，落到 <b>{passed}</b>。</li>
  </ul>
  <p><b>结论：</b>96.48% 是「宽松基准 + 历史投票」的产物，<u>不是可独立复现的 LoCoMo 标准口径分数</u>。
  对外可诚实声明的主口径应为本次冻结的 <b>{score:.2f}%</b>（干净 gpt-4o-mini 重判）。</p>
</div>

<div class="card">
  <h3>📦 冻结产物（SHA256 归档）</h3>
  <table>
    <tr><th>文件</th><th>角色</th><th>SHA256 (前 16 位)</th></tr>
    <tr><td><code>locomo_qa_or10_full1986.json</code></td><td>冻结 Reader 假设集（OR3 + 7 救援，3,078 条）</td>
        <td class="mono">{man.get('hypotheses_sha256','')[:16]}…</td></tr>
    <tr><td><code>locomo_qa_or10_full1986_frozen_result.json</code></td><td>gpt-4o-mini 干净重判结果</td>
        <td class="mono">{man.get('result_sha256','')[:16]}…</td></tr>
    <tr><td><code>locomo_qa_or10_full1986_frozen_manifest.json</code></td><td>归档清单</td><td class="mono">—</td></tr>
  </table>
  <p class="mono">假设集 SHA256：{man.get('hypotheses_sha256','')}</p>
  <p class="mono">结果集 SHA256：{man.get('result_sha256','')}</p>
</div>

<div class="card">
  <h3>🎯 分题型准确率（干净重判）</h3>
  <table><tr><th>题型</th><th>准确率</th></tr>{type_rows}</table>
</div>

<div class="card">
  <h3>🔧 通过来源分布（OR 并集）</h3>
  <table><tr><th>假设来源</th><th>贡献通过题数</th></tr>{src_rows}</table>
  <p class="mono">rescue1–4 合计 {rescue_only} 题来自救援假设（其余 {both} 题救援与 OR3 同时通过对最终计数无增量）。</p>
</div>

<div class="card">
  <h3>📐 口径对照（诚实版）</h3>
  <table>
    <tr><th>口径</th><th>Judge</th><th>数值</th><th>可复现性</th></tr>
    <tr><td>原声明 OR10</td><td>gpt-4o-mini（宽松基准+历史投票）</td><td><b>96.48%</b>（1916）</td><td>❌ 不可干净复现</td></tr>
    <tr><td><b>本次冻结 OR10</b></td><td>gpt-4o-mini（干净 5 票重判）</td><td><b>{score:.2f}%</b>（{passed}）</td><td>✅ 可 BYOK 复现</td></tr>
    <tr><td>本次冻结 OR3-only</td><td>gpt-4o-mini（干净 5 票重判）</td><td>{100*or3_only/total:.2f}%（{or3_only}）</td><td>✅ 可复现</td></tr>
    <tr><td>更严交叉验证 OR10</td><td>gpt-4o</td><td>91.89%（1825）</td><td>✅ 可复现</td></tr>
  </table>
</div>

<div class="card">
  <h3>⚙️ 运行参数与成本</h3>
  <ul>
    <li>Judge：<span class="tag">{meta.get('judge_model','')}</span> · 每假设 5 票 · 阈值 ≥3</li>
    <li>估算调用：<span class="num">{meta.get('estimated_judge_calls',0):,}</span> 次 · 成功/失败：{meta.get('judge_call_success',0)}/{meta.get('judge_call_fail',0)}</li>
    <li>耗时：<span class="num">{meta.get('elapsed_s',0)/60:.1f}</span> min · 成本：<b>${meta.get('total_cost_usd',0):.4f}</b>（BYOK 自付）</li>
  </ul>
</div>

<div class="card warn">
  <h3>🧭 建议与下一步</h3>
  <ul>
    <li><b>对外口径</b>：以冻结的 <b>{score:.2f}%</b> 作为诚实可复现主口径；96.48% 仅作内部历史记录，不对外宣称。</li>
    <li><b>竞品对标</b>：MemMachine 91.7%（gpt-4o-mini）之下，{score:.2f}% 仍领先；ByteRover 96.1% 其 Judge 未披露、不可比。</li>
    <li><b>若要坚持 96.48%</b>：需找回原救援实验所用的（题型感知）Judge prompt 并随包发布，使第三方可复现——否则该数字缺乏可复现性背书。</li>
    <li><b>修复 OR3 基准文件</b>：将 <code>or_correct</code> 标记改为干净 gpt-4o-mini 5 票结果，消除 94.61% meta 与 85.75% 声明的内部矛盾。</li>
  </ul>
</div>

<div class="card">
  <h3>🔁 BYOK 复现</h3>
  <pre style="background:#1c2128;padding:12px;border-radius:8px;overflow:auto;color:#e6edf3;"><code>cd repro_byok
export OPENROUTER_API_KEY=sk-or-...
python locomo/freeze_or10.py --full    # 全量复现 ≈{score:.2f}%</code></pre>
</div>

<p class="sub" style="text-align:center;">T1Mem — 诚实优先 · LoCoMo OR10 干净冻结 {today}</p>
</div></body></html>"""

out = os.path.join(OUTDIR, f"N1Mem_LoCoMo_OR10_Frozen_Report_{today}.html")
open(out, "w", encoding="utf-8").write(html)
print(f"Report -> {out}")
print(f"Frozen: {score:.2f}%  |  orig claim: {orig_claim}%  |  gap: -{gap:.2f}pp")
print(f"OR3 file or_correct={or3_or_correct} ({100*or3_or_correct/total:.2f}%)  fresh OR3-only={or3_only} ({100*or3_only/total:.2f}%)")
print(f"stored rescue qids={len(stored_rescue)}  fresh rescue-only={rescue_only}")
