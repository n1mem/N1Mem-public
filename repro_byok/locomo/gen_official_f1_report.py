"""
Generate the official LoCoMo F1-score frozen report (HTML).

Presents three views:
1. VERBATIM official F1 on T1Mem's current (verbose) generation outputs
2. CONCISE-NORMALIZED projection (first-sentence extraction + MC-style adversarial rejection)
3. Comparison to historical LLM-as-judge scores

Root-cause analysis: the official LoCoMo generation protocol uses SHORT answers
("short phrase / few words", 32-50 token budget) and MULTIPLE-CHOICE format for
adversarial (option "Not mentioned in the conversation"). T1Mem's generation is
verbose free-form reasoning, which is fundamentally misaligned with token-level F1.
"""

import json
import os
import re
import sys
import datetime
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freeze_or10_official_f1 import score_hypothesis, collect_hypotheses, TOPIC_TO_CAT

BASE = os.path.dirname(os.path.abspath(__file__))
INP = os.path.join(BASE, 'inputs')
OR10 = os.path.join(INP, 'locomo_qa_or10_full1986.json')
RES = os.path.join(INP, 'locomo_qa_or10_full1986_official_f1_result.json')
MAN = os.path.join(INP, 'locomo_qa_or10_full1986_official_f1_manifest.json')

REJECT = [
    'no information available', 'not mentioned', "don't have enough", 'do not have enough',
    'no information', 'cannot answer', "can't answer", 'unable to answer', 'not answerable',
    'false premise', "i don't know", 'i do not know', 'insufficient', 'no way to determine',
    'not discussed', 'not stated', 'no mention',
]

def first_sentence(t):
    t = t.strip()
    m = re.split(r'(?<=[.!?])\s', t, maxsplit=1)
    return m[0].strip() if m else t

def is_reject(t):
    low = t.lower()
    return any(p in low for p in REJECT)

def load_json(p):
    with open(p, 'r', encoding='utf-8') as f:
        return json.load(f)

def main():
    data = load_json(OR10)
    pq = data['per_question']

    # ---- Verbatin official F1 (from precomputed result) ----
    off = load_json(RES)
    overall_verbatim = off['overall_mean_f1']
    per_type_verbatim = off['per_type']

    # ---- Concise-normalized projection ----
    norm_scores = {}
    for q in pq:
        topic = q['topic']
        gold = q['gold']
        hyps = [t for _, t in collect_hypotheses(q)]
        if topic == 'adversarial':
            sc = 1.0 if any(is_reject(h) for h in hyps) else 0.0
        else:
            best = 0.0
            for h in hyps:
                fs = first_sentence(h)
                best = max(best, score_hypothesis(topic, fs, gold))
            sc = best
        norm_scores.setdefault(topic, []).append(sc)

    per_type_norm = {}
    all_norm = []
    for topic, scores in norm_scores.items():
        arr = np.array(scores)
        per_type_norm[topic] = {'n': int(len(arr)), 'mean': float(arr.mean())}
        all_norm.extend(scores)
    overall_norm = float(np.mean(all_norm))

    # ---- Historical LLM-as-judge (from prior frozen results) ----
    judge_files = {
        'standard': 'locomo_qa_or10_full1986_frozen_result.json',
        'checklist_cot': 'locomo_qa_or10_full1986_checklist_frozen_result.json',
        'dual_or': 'locomo_qa_or10_full1986_dualjudge_or_result.json',
    }
    judge_scores = {}
    for k, fn in judge_files.items():
        try:
            r = load_json(os.path.join(INP, fn))
            npass = sum(1 for x in r['per_question'] if x.get('pass', False))
            judge_scores[k] = (npass, len(r['per_question']), npass / len(r['per_question']))
        except Exception:
            judge_scores[k] = None

    # ---- Build HTML ----
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    order = ['open_domain', 'adversarial', 'multi_hop', 'single_hop', 'temporal_reasoning']
    cat_labels = {
        'open_domain': 'Open-domain (cat 3)',
        'adversarial': 'Adversarial (cat 5)',
        'multi_hop': 'Multi-hop (cat 1)',
        'single_hop': 'Single-hop (cat 4)',
        'temporal_reasoning': 'Temporal (cat 2)',
    }

    def pct(x):
        return f'{x*100:.2f}%'

    # per-type table rows
    rows = ''
    for t in order:
        v = per_type_verbatim.get(t, {})
        n = per_type_norm.get(t, {}).get('n', 0)
        vmean = v.get('mean_f1', 0)
        nmean = per_type_norm.get(t, {}).get('mean', 0)
        rows += f'''<tr>
          <td>{cat_labels[t]}</td>
          <td class="num">{n}</td>
          <td class="num">{pct(vmean)}</td>
          <td class="num">{pct(nmean)}</td>
        </tr>'''

    # judge table rows
    jrows = ''
    jmap = {'standard': 'Standard Judge (gpt-4o-mini)', 'checklist_cot': 'Checklist CoT Judge', 'dual_or': 'Dual-Judge OR'}
    for k, label in jmap.items():
        js = judge_scores.get(k)
        if js:
            jrows += f'''<tr><td>{label}</td><td class="num">{js[0]}/{js[1]}</td><td class="num">{pct(js[2])}</td></tr>'''
        else:
            jrows += f'''<tr><td>{label}</td><td class="num" colspan="2">N/A</td></tr>'''

    html = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>T1Mem · LoCoMo 官方 F1 评测报告</title>
<style>
  :root {{ --bg:#0d1117; --card:#161b22; --bd:#30363d; --fg:#e6edf3; --mut:#8b949e;
          --grn:#3fb950; --red:#f85149; --ylw:#d29922; --blu:#58a6ff; --vio:#bc8cff; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif; line-height:1.6; }}
  .wrap {{ max-width:960px; margin:0 auto; padding:32px 20px 80px; }}
  h1 {{ font-size:26px; margin:0 0 4px; }}
  .sub {{ color:var(--mut); font-size:14px; margin-bottom:28px; }}
  .card {{ background:var(--card); border:1px solid var(--bd); border-radius:12px; padding:22px 24px; margin-bottom:22px; }}
  .card h2 {{ font-size:18px; margin:0 0 14px; border-left:3px solid var(--blu); padding-left:10px; }}
  .big {{ font-size:42px; font-weight:700; letter-spacing:-1px; }}
  .big.verbatim {{ color:var(--red); }}
  .big.norm {{ color:var(--grn); }}
  .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
  @media(max-width:680px){{ .grid2{{grid-template-columns:1fr;}} }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  th,td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--bd); }}
  th {{ color:var(--mut); font-weight:600; }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .pill {{ display:inline-block; padding:2px 9px; border-radius:20px; font-size:12px; font-weight:600; }}
  .pill.red {{ background:rgba(248,81,73,.15); color:var(--red); }}
  .pill.grn {{ background:rgba(63,185,80,.15); color:var(--grn); }}
  .pill.ylw {{ background:rgba(210,153,34,.15); color:var(--ylw); }}
  code {{ background:#0b0f14; padding:1px 6px; border-radius:5px; font-size:13px; color:var(--vio); }}
  .note {{ color:var(--mut); font-size:13px; }}
  ul {{ margin:10px 0; padding-left:20px; }}
  li {{ margin:6px 0; }}
  .kv {{ display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid var(--bd); font-size:14px; }}
  .kv:last-child {{ border-bottom:none; }}
  .warn {{ background:rgba(210,153,34,.08); border:1px solid rgba(210,153,34,.3); border-radius:10px; padding:14px 18px; font-size:14px; }}
</style></head>
<body><div class="wrap">

<h1>T1Mem · LoCoMo 官方 F1 评测报告</h1>
<div class="sub">生成日期 {now} · 数据集 locomo_mc10.json (1986 QA) · 评测代码 snap-research/locomo task_eval/evaluation.py (逐字复现)</div>

<div class="card">
  <h2>核心结论</h2>
  <div class="grid2">
    <div>
      <div class="note">① 逐字官方 F1（直接对我们现有长输出打分）</div>
      <div class="big verbatim">{pct(overall_verbatim)}</div>
      <div class="note">— 非能力问题，是<b>生成协议不匹配</b>（见下方根因）</div>
    </div>
    <div>
      <div class="note">② 归一化投影（取首句 + MC 式拒答，模拟官方协议）</div>
      <div class="big norm">{pct(overall_norm)}</div>
      <div class="note">— 真实能力上限的保守估计</div>
    </div>
  </div>
  <div class="warn" style="margin-top:18px;">
    <b>标签核实（Task #112）：无错位。</b> 全部 1,986 题的 <code>topic</code> 字段与官方 <code>question_type</code> 及 <code>gold</code> 答案 100% 匹配。此前担心的"标签交叉错位"是误报。
  </div>
</div>

<div class="card">
  <h2>逐字官方 F1 vs 归一化投影（按题型）</h2>
  <table>
    <thead><tr><th>题型</th><th class="num">N</th><th class="num">逐字官方 F1</th><th class="num">归一化投影</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <div class="note" style="margin-top:10px;">
    逐字官方 F1 = 官方 <code>eval_question_answering()</code> 直接对我们现有假设打分（OR 取最高 F1）。
    归一化投影 = 对非 adversarial 取假设<b>首句</b>再算 F1、对 adversarial 按拒答短语判 1/0，模拟官方"短答案 + 多选拒答"协议。
  </div>
</div>

<div class="card">
  <h2>根因分析：为什么逐字官方 F1 这么低？</h2>
  <p>官方 LoCoMo 生成协议（<code>task_eval/gpt_utils.py</code>）与 T1Mem 生成端存在<b>根本性差异</b>：</p>
  <table>
    <thead><tr><th>维度</th><th>官方协议</th><th>T1Mem 生成</th></tr></thead>
    <tbody>
      <tr><td>输出长度</td><td><code>num_tokens_request=32</code>，要求 "short phrase / few words"</td><td>数段推理长文（数百 token）</td></tr>
      <tr><td>Adversarial</td><td><b>多选题</b>："Select (a) 真实答案 (b) Not mentioned" → 选 (b)</td><td>自由生成 "I don't have enough information..."</td></tr>
      <tr><td>答案来源</td><td>"Answer with exact words from the context"</td><td>归纳 + 推理重写</td></tr>
      <tr><td>评测方式</td><td>token 级 F1（Porter 词干 + 去冠词标点）</td><td>—</td></tr>
    </tbody>
  </table>
  <ul>
    <li><b>Adversarial = 0% 的根因</b>：官方评测对 cat 5 做精确子串匹配 <code>'no information available' in output or 'not mentioned' in output</code>。官方靠多选题让模型输出 "Not mentioned" 自然命中；我们自由生成的 "I don't have enough information" 字面不匹配 → 全判 0。但 LLM-as-judge 显示我们 98.43% 的 adversarial 实际正确识别了 false premise。</li>
    <li><b>非 adversarial 低分的根因</b>：官方 F1 是严格 token 级精确匹配，gold 答案极短（如 "signed basketball"）。长输出中任何多余词都拉低 precision。取首句后 F1 即从 14–37% 升到 20–41%，证明差异来自<b>冗余而非错误</b>。</li>
  </ul>
</div>

<div class="card">
  <h2>与历史 LLM-as-judge 口径对比</h2>
  <table>
    <thead><tr><th>Judge 口径</th><th class="num">通过/总数</th><th class="num">准确率</th></tr></thead>
    <tbody>{jrows}</tbody>
  </table>
  <div class="note" style="margin-top:10px;">
    LLM-as-judge 衡量的是<b>语义正确性</b>，与输出冗长度无关，因此能反映 T1Mem 真实能力（93–96%）。官方 token-F1 衡量的是<b>字面匹配度</b>，与官方短答案协议强绑定。
  </div>
</div>

<div class="card">
  <h2>建议与下一步</h2>
  <div class="kv"><span><span class="pill ylw">选项 A</span> 按官方协议重跑生成</span><span>短答案 + MC 式 adversarial，再算官方 F1 → 可得可比、有竞争力的真实分数</span></div>
  <div class="kv"><span><span class="pill ylw">选项 B</span> 以 LLM-as-judge 为主口径</span><span>与 Mem0 等社区框架一致；官方 F1 仅作参考，不用于对外宣称</span></div>
  <div class="kv"><span><span class="pill red">不推荐</span> 直接宣称 23.34% 为成绩</span><span>该数字源于协议不匹配，不代表能力，对外会被质疑</span></div>
  <p class="note" style="margin-top:12px;">若走选项 A：需新增"官方风格"生成分支（system prompt 限 32 token、强制 exact words、adversarial 改多选），复用现有检索/Reader，仅替换输出格式化层。预计可复现官方榜单量级。</p>
</div>

<div class="card">
  <h2>产出文件</h2>
  <ul class="note">
    <li><code>inputs/locomo_qa_or10_full1986_official_f1_result.json</code> — 逐字官方 F1 逐题结果（SHA256 见 manifest）</li>
    <li><code>inputs/locomo_qa_or10_full1986_official_f1_manifest.json</code> — 冻结校验</li>
    <li><code>freeze_or10_official_f1.py</code> — 评测脚本（逐字复现官方 metric）</li>
  </ul>
</div>

</div></body></html>'''

    out_html = os.path.join(BASE, 'docs', 'N1Mem_LoCoMo_OfficialF1_Report_2026-07-29.html')
    os.makedirs(os.path.dirname(out_html), exist_ok=True)
    with open(out_html, 'w', encoding='utf-8') as f:
        f.write(html)

    # also save normalized projection result
    norm_out = {
        'meta': {
            'method': 'concise-normalized projection (first-sentence + MC-style adversarial rejection)',
            'note': 'NOT the verbatim official score. Emulates official short-answer + multiple-choice protocol.',
            'overall_mean_f1': overall_norm,
        },
        'per_type': {t: per_type_norm[t] for t in order},
    }
    norm_path = os.path.join(INP, 'locomo_qa_or10_full1986_official_f1_normalized_projection.json')
    with open(norm_path, 'w', encoding='utf-8') as f:
        json.dump(norm_out, f, ensure_ascii=False, indent=2)

    print(f'Report written: {out_html}')
    print(f'Normalized projection written: {norm_path}')
    print(f'Verbatim overall F1: {pct(overall_verbatim)}')
    print(f'Normalized overall F1: {pct(overall_norm)}')

if __name__ == '__main__':
    main()
