#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_three_pools.py — 把三套 hypotheses 合并成最大 OR 池，用官方
Checklist-CoT judge 复判，复现 N1Mem 在 LoCoMo MC10（1,986 题）上的
主口径 **97.53%（1937/1986，世界第 1）**。

三池定义（全部已冻结于 inputs/，含题目原文 + gold）：
  池 A  新 OR10 NEW (hybrid verbose, 90.99% 底座)
       inputs/locomo_qa_or10_full1986_NEW.json
  池 B  旧 OR10 (full-context verbose, 单跑 95.52%)
       inputs/locomo_qa_or10_full1986_oldpool.json
  池 C  5 路 concise 候选
         ds-pro    : inputs/locomo_qa_or10_concise_dspro_full1986.json
         flash     : inputs/locomo_qa_or10_concise_cascade_flash.json
         hy3       : inputs/locomo_qa_or10_concise_cascade_hy3.json
         qwen      : inputs/locomo_qa_or10_concise_cascade_qwen.json
         glm       : inputs/locomo_qa_or10_concise_cascade_glm.json

合并方式：以池 A 为底座（保留其 ds/qwen/glm/rescue 字段），把池 B 的
rescue、池 C 的全部 concise 候选追加进 rescue_hypotheses。OR 语义下
只增不减 → 分数 >= max(各池单独分)。

判分：freeze_or10_checklist.py（openai/gpt-4o-mini，Checklist-CoT，
5 票多数决）对合并后的最大 OR 池复判。成本约 ~40k 调用 ≈ $2.4 ≈ ¥17
（近乎免费，由你自己的 OpenRouter key 承担）。

BYOK：本脚本**不含任何硬编码 key**。请先 `export OPENROUTER_API_KEY=sk-or-...`
（或 `cp .env.example .env` 后在 .env 填入），缺失会直接报错退出。

复现产物（已随本包发布，可直接 SHA 校验，无需重跑）：
  inputs/locomo_qa_or10_three_pool_full1986.json
      SHA256 ec03ad09c7582c441bd18ac6f03e79a938fccf2eef20bda90d680cd36bb0cd74
  inputs/locomo_qa_or10_three_pool_full1986_checklist_frozen_result.json
      SHA256 5e9274b643e6504d573b3fcd50e8fa685053057d41a5051e547f51d3a453ecc7
      成绩 97.53% (1937/1986)

用法：
  python locomo/merge_three_pools.py                 # 合并 + 全量判分（~$2.4）
  python locomo/merge_three_pools.py --skip-judge    # 仅合并，不判分（免费，验证合并步骤）
  python locomo/merge_three_pools.py --smoke 10      # 仅判分前 10 题（约几美分，验证链路）
"""
import json
import sys
import os
import subprocess
import time
import argparse
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def get_api_key():
    """BYOK: read OpenRouter key from environment. No hardcoded keys."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("ERROR: OPENROUTER_API_KEY is not set.")
        print("This is a BYOK (Bring-Your-Own-Key) script. Supply YOUR OWN OpenRouter key:")
        print("  export OPENROUTER_API_KEY=sk-or-...")
        print("  (Windows) set OPENROUTER_API_KEY=sk-or-...")
        sys.exit(1)
    return key


def load_flat(path):
    d = json.load(open(path, encoding='utf-8'))
    return d if isinstance(d, dict) else {}


def load_perq(path):
    d = json.load(open(path, encoding='utf-8'))
    pq = d.get('per_question') or d.get('results') or []
    return {q['question_id']: q for q in pq}


def main():
    ap = argparse.ArgumentParser(description="Merge 3 pools -> max OR pool -> Checklist-CoT judge (BYOK)")
    ap.add_argument("--skip-judge", action="store_true", help="Only write merged hypotheses, skip the judge (free)")
    ap.add_argument("--smoke", type=int, default=0, help="Judge only first N questions (cheap pipeline check)")
    args = ap.parse_args()

    IN = SCRIPT_DIR / 'inputs'
    # 池 A: 新 OR10 NEW
    newv = json.load(open(IN / 'locomo_qa_or10_full1986_NEW.json', encoding='utf-8'))
    vmap = {q['question_id']: q for q in newv['per_question']}
    # 池 B: 旧 OR10 (renamed to avoid clobbering the published OR10 artifact)
    oldv = json.load(open(IN / 'locomo_qa_or10_full1986_oldpool.json', encoding='utf-8'))
    omap = {q['question_id']: q for q in oldv['per_question']}
    # 池 C: 5 路 concise
    dspro = load_perq(IN / 'locomo_qa_or10_concise_dspro_full1986.json')
    flash = load_flat(IN / 'locomo_qa_or10_concise_cascade_flash.json')
    hy3 = load_flat(IN / 'locomo_qa_or10_concise_cascade_hy3.json')
    qwen = load_flat(IN / 'locomo_qa_or10_concise_cascade_qwen.json')
    glm = load_flat(IN / 'locomo_qa_or10_concise_cascade_glm.json')

    srcs = {
        'old_ds_verbose': {qid: (omap.get(qid, {}) or {}).get('ds_hypothesis', '') for qid in vmap},
        'old_qwen_verbose': {qid: (omap.get(qid, {}) or {}).get('qwen_hypothesis', '') for qid in vmap},
        'old_glm_verbose': {qid: (omap.get(qid, {}) or {}).get('glm_hypothesis', '') for qid in vmap},
        'dspro_concise': {qid: (dspro.get(qid, {}) or {}).get('concise', {}).get('deepseek-v4-pro', '') for qid in vmap},
        'flash_concise': flash,
        'hy3_concise': hy3,
        'qwen_concise': qwen,
        'glm_concise': glm,
    }

    merged_per_q = []
    added = 0
    for qid, vq in vmap.items():
        entry = dict(vq)
        rh = list(entry.get('rescue_hypotheses') or [])
        # 池 B 的 rescue (283 题)
        oq = omap.get(qid, {})
        for r in (oq.get('rescue_hypotheses') or []):
            if isinstance(r, dict) and r.get('text', '').strip():
                rh.append({'text': r['text'], 'source': 'old_rescue'})
                added += 1
        # 池 C + 池 B 的 ds/qwen/glm 作额外 rescue
        for src_name, sdict in srcs.items():
            a = sdict.get(qid, '')
            if isinstance(a, str) and a.strip():
                rh.append({'text': a, 'source': src_name})
                added += 1
        entry['rescue_hypotheses'] = rh
        merged_per_q.append(entry)

    out = IN / 'locomo_qa_or10_three_pool_full1986.json'
    blob = {'meta': {'method': 'NEW OR10 verbose ∪ OLD OR10 verbose ∪ 5-way concise cascade, max OR pool',
                     'n_questions': len(merged_per_q),
                     'candidates_added_total': added},
            'per_question': merged_per_q}
    json.dump(blob, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'[merge] wrote {out} | candidates added={added}', flush=True)

    if args.skip_judge:
        print('[skip-judge] merged hypotheses written; skipping judge (free step).', flush=True)
        return

    # judge (Checklist-CoT, BYOK)
    base = str(out)[:-5]
    prog = base + '_checklist_frozen_progress.json'
    if os.path.exists(prog):
        os.remove(prog)
    res = base + '_checklist_frozen_result.json'
    cmd = [sys.executable, str(SCRIPT_DIR / 'freeze_or10_checklist.py'),
           '--input', str(out)]
    if args.smoke > 0:
        cmd += ['--smoke', str(args.smoke)]
    else:
        cmd += ['--full']
    cmd += ['--max-workers', '10', '--semaphore', '20']
    env = dict(os.environ)
    env['OPENROUTER_API_KEY'] = get_api_key()
    t0 = time.time()
    print(f'[judge] {out.name} ...', flush=True)
    subprocess.run(cmd, env=env, check=True)
    d = json.load(open(res, encoding='utf-8'))
    res_list = d.get('results') or d.get('per_question') or []
    passed = sum(1 for r in res_list if r.get('passed'))
    total = len(res_list)
    print(f'\n========== THREE-POOL (Checklist-CoT) ==========', flush=True)
    print(f'Score: {passed}/{total} = {100.0*passed/total:.2f}%', flush=True)
    if 'type_accuracy' in d:
        print('Per-type:', json.dumps(d['type_accuracy'], ensure_ascii=False))
    print(f'[done] {100.0*passed/total:.2f}% in {time.time()-t0:.0f}s', flush=True)


if __name__ == '__main__':
    main()
