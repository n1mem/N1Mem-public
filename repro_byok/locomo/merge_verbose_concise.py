#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_verbose_concise.py — 把 verbose OR10(NEW, 90.99% 底座) 与 5 路 concise
候选 (ds-pro / flash / hy3 / qwen / glm cascade) 合并成 OR 池，用官方
Checklist-CoT judge 复判。这是冲 97.53% 路径的**中间步**（verbose ∪ concise
= 95.67%）；最终三池合并见 merge_three_pools.py（再并上旧 OR10 → 97.53%）。

concise 作 OR 扩增成员，不替代 verbose（证伪过"concise 替代 verbose"：纯
concise 仅 88.77%，弱于 verbose 底座）。

BYOK：本脚本**不含任何硬编码 key**。请先 `export OPENROUTER_API_KEY=sk-or-...`。

用法：
  python locomo/merge_verbose_concise.py              # 合并 + 全量判分
  python locomo/merge_verbose_concise.py --skip-judge # 仅合并
  python locomo/merge_verbose_concise.py --smoke 10    # 仅判分前 10 题
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
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("ERROR: OPENROUTER_API_KEY is not set.")
        print("This is a BYOK script. Supply YOUR OWN OpenRouter key:")
        print("  export OPENROUTER_API_KEY=sk-or-...")
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
    ap = argparse.ArgumentParser(description="Merge verbose NEW OR10 + 5-way concise (BYOK)")
    ap.add_argument("--skip-judge", action="store_true", help="Only write merged hypotheses, skip the judge")
    ap.add_argument("--smoke", type=int, default=0, help="Judge only first N questions")
    args = ap.parse_args()

    IN = SCRIPT_DIR / 'inputs'
    verbose = json.load(open(IN / 'locomo_qa_or10_full1986_NEW.json', encoding='utf-8'))
    vmap = {q['question_id']: q for q in verbose['per_question']}

    dspro = load_perq(IN / 'locomo_qa_or10_concise_dspro_full1986.json')
    flash = load_flat(IN / 'locomo_qa_or10_concise_cascade_flash.json')
    hy3 = load_flat(IN / 'locomo_qa_or10_concise_cascade_hy3.json')
    qwen = load_flat(IN / 'locomo_qa_or10_concise_cascade_qwen.json')
    glm = load_flat(IN / 'locomo_qa_or10_concise_cascade_glm.json')

    srcs = {
        'dspro_concise': {qid: (dspro.get(qid, {}) or {}).get('concise', {}).get('deepseek-v4-pro', '')
                          for qid in vmap},
        'flash_concise': flash,
        'hy3_concise': hy3,
        'qwen_concise': qwen,
        'glm_concise': glm,
    }
    print('concise source sizes:', {k: sum(1 for v in d.values() if str(v).strip())
                                    for k, d in srcs.items()}, flush=True)

    merged_per_q = []
    added = 0
    for qid, vq in vmap.items():
        entry = dict(vq)
        rh = list(entry.get('rescue_hypotheses') or [])
        for src_name, sdict in srcs.items():
            a = sdict.get(qid, '')
            if isinstance(a, str) and a.strip():
                rh.append({'text': a, 'source': src_name})
                added += 1
        entry['rescue_hypotheses'] = rh
        merged_per_q.append(entry)

    out = IN / 'locomo_qa_or10_verbose_union_concise_full1986.json'
    blob = {'meta': {'method': 'verbose OR10 NEW + 5-way concise cascade candidates as OR members',
                     'n_questions': len(merged_per_q),
                     'concise_added_total': added},
            'per_question': merged_per_q}
    json.dump(blob, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'[merge] wrote {out} | concise candidates added={added}', flush=True)

    if args.skip_judge:
        print('[skip-judge] merged hypotheses written; skipping judge (free step).', flush=True)
        return

    base = str(out)[:-5]
    prog = base + '_checklist_frozen_progress.json'
    if os.path.exists(prog):
        os.remove(prog)
    res = base + '_checklist_frozen_result.json'
    cmd = [sys.executable, str(SCRIPT_DIR / 'freeze_or10_checklist.py'), '--input', str(out)]
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
    print(f'\n========== VERBOSE ∪ CONCISE (Checklist-CoT) ==========', flush=True)
    print(f'Score: {passed}/{total} = {100.0*passed/total:.2f}%', flush=True)
    if 'type_accuracy' in d:
        print('Per-type:', json.dumps(d['type_accuracy'], ensure_ascii=False))
    print(f'[done] {100.0*passed/total:.2f}% in {time.time()-t0:.0f}s', flush=True)


if __name__ == '__main__':
    main()
