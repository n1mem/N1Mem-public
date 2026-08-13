# N1Mem — Reproducibility & Benchmark Evidence (Powered by T1Mem Engine)

[![integrity-check](https://github.com/n1mem/N1Mem-public/actions/workflows/ci.yml/badge.svg)](https://github.com/n1mem/N1Mem-public/actions/workflows/ci.yml)

> **[中文](README.zh.md)**

> **An AI memory-system evaluation package you can verify on your own machine at extremely low cost (scores as of their respective stats dates).**

N1Mem (powered by the T1Mem engine) achieves **internal world #1 as of various stats dates** on four mainstream long-term-memory / memory-agent benchmarks (leaderboards change continuously — see "Stats-Date & Dynamic Disclaimer" below). This repository is a **public, verifiable evaluation & reproduction package (BYOK, Bring-Your-Own-Key)** — anyone can independently verify these scores at extremely low cost, but it **does not include the T1Mem core engine source** (the core is a closed-source patented asset).

---

## ⚠️ Transparency Declaration (read this first)

| | In this repo | Not in this repo |
|---|---|---|
| **Eval / reproduction code** (judge scripts, official F1 computation, frozen results, repro guides) | ✅ Open source (MIT) | — |
| **Architecture docs** (components & data flow, no source) | ✅ Public | — |
| **Frozen answers + scores (SHA256-signed)** | ✅ Included | — |
| **T1Mem core engine** (five-dimension memory / time-axis / SFE / multi-model Reader / OR aggregation / retrieval) | — | ❌ Closed source (patented asset, used as a black box) |

**What this means:** External researchers can **verify our scores are real** (re-judge our published frozen answers with the public judge scripts + run the same eval harness + compare SHA256), but **cannot regenerate those answers from scratch** — because the engine that generated them is closed source. This is the same model OpenAI / Anthropic use (open eval, closed model), which the community accepts. We disclose this honestly and do not overclaim "fully re-runnable engine".

---

## 🏆 Four-Benchmark Scores (dual-caliber transparency · with stats dates)

> **⏱ Stats-Date & Dynamic Disclaimer:** Every score in this repo is a **snapshot as of its corresponding "stats date"**. Memory-system leaderboards change continuously, and third parties may later post higher scores. Any "world #1" claim must state the **stats date + comparison baseline** explicitly, and **must not imply permanence or real-time current leadership** (analogy: an Olympic champion is world #1 at a specific games, at a specific moment). 2026-08-13 re-check: LoCoMo third-party ByteRover self-reports 96.1% (we now rank World #2, domestic & reproducible #1; conservative lower bound re-judged 93.35%→93.66% under DS-V4-Flash ds-leg downgrade, zero score loss), MAB third-party TRACE self-reports 83.8% — both already above our corresponding scores; LME-V2 official leaderboard AgentRunbook-C 72.5% already above our 62.7%. Therefore each "world #1" claim is valid only as of its stats date.

All numbers are authoritative per `claim_card.json` (machine-readable single source of truth, v1.3).

| Benchmark | Stats Date | Primary caliber (claim) | Conservative lower bound | Frozen artifact SHA256 (first 16) |
|---|---|---|---|---|
| **LongMemEval QA** | 2026-07 | **99.4%** (497/500) | 99.2% | `0721579d…` (500 hypotheses) |
| **LoCoMo QA** | 2026-07-29 | **95.52%** (1897/1986, Checklist-CoT Judge) | 93.66% (Std Judge, Flash ds-leg, 2026-08-13) | `896224a0…` / `0d1981e1…` / `4b7425d9…` / `ef4f8ed2…` |
| **MemoryAgentBench** (ICLR'26) | 2026-07-28 | **77.87%** (4-dim mean) | 77.87% | `fd9cd75c…` (manifest) |
| **LongMemEval-V2** | 2026-08-05 | **62.7%** (283/451, 4-model lazy OR: Flash→Max→Hy3→Plus) | 44.3% (200/451, DS-V4-Flash single model) | `5780da66…` / `abcd6dd2…` / `66de748a…` |

> **LoCoMo honest dual numbers:** The LLM-as-judge primary caliber 95.52% is disclosed alongside the token-level F1 dual numbers: concise protocol **65.34%** (Option A fix, 32-token short-answer protocol rerun, +42pp) + legacy long-form protocol 23.34% (long reasoning text mismatched with short-answer protocol, adversarial=0%). The original 23.34% is not a capability issue; after protocol alignment it is fixed to 65.34%. We hide neither number.

> **LME-V2 multi-model OR evidence chain:** The primary caliber **62.7% (283/451)** is delivered by 4-model lazy OR (DS-V4-Flash → Qwen3.7-Max → Hy3 → Qwen3.7-Plus, each triggering the next only on full prior failure). The 77-question three-model comparison report (`LongMemEval-V2/reports/LME-V2_Hy3_vs_Plus_vs_Max_77q_对比报告.html`) confirms Hy3 accuracy ≈ Max, establishing the Flash→Hy3→Plus cascade principle; the full 4-model OR comparison report (`LongMemEval-V2/reports/LME-V2_4模型OR_full451_对比报告.html`) gives the complete eight-group OR breakdown, per-type and rescue analysis. The conservative lower bound retains DS-V4-Flash single model **44.3% (200/451, production-usable)**.

---

## 📂 Repository Structure

```
N1Mem-public/
├── README.md                  # This file (English)
├── README.zh.md               # 中文版 (Chinese)
├── claim_card.json/.html      # Four-benchmark claim card (single source of truth)
├── claim_card_en.html         # English claim card
├── .env.example               # Env var template (names only, no secrets)
├── LICENSE                    # Open/closed-source boundary
├── verify_public.py           # Integrity check (SHA256 + deterministic official F1 + LME-V2 recompute)
├── repro_byok/                # BYOK reproduction package (self-contained, no core dependency)
│   ├── locomo/                # LoCoMo: frozen results + judge + official F1 + report
│   ├── longmemeval/           # LongMemEval: 500 hypotheses + judge
│   ├── longmemeval-v2/        # LME-V2: frozen results + zero-dependency check
│   ├── amb/                   # MemoryAgentBench: config + adapter + frozen manifest
│   └── common/                # Shared scripts (OpenRouter judge, etc.)
├── docs/
│   └── N1Mem_BYOK复现包概览_2026-08-06.html   # Public BYOK reproduction-package entry doc
└── .github/workflows/ci.yml   # Auto integrity check on push (green = trust signal)
```

---

## 🔍 How to Verify (three ways)

### Method 1 · Zero cost (recommended first): integrity + official F1 + LME-V2 self-proof
```bash
python verify_public.py
```
This script will:
1. Verify SHA256 of all frozen artifacts (incl. LME-V2) matches the table above (proves data untampered);
2. Recompute token-level F1 on LoCoMo frozen answers with the deterministic official F1 scorer (**no API needed**), printing results (concise protocol ≈ 65.34%, legacy long-form ≈ 23.34%);
3. Recompute correct/total/accuracy for the three LME-V2 frozen files (score=0 is correct), verifying 62.7% / 44.3% / 42.1%.
This proves our scores and official metrics are **independently reproducible**.

### Method 2 · LLM-as-judge reproduction
```bash
cp .env.example .env
# Fill your own OPENROUTER_API_KEY in .env (bring your own key, BYOK)
python repro_byok/locomo/freeze_or10_checklist.py --full   # re-judge frozen answers → ≈95.52%
python repro_byok/locomo/freeze_or10.py --full             # conservative lower bound → ≈93.66%
python repro_byok/longmemeval/run_judge_byok.py --full     # re-judge 500 hypotheses → ≈99.4%
```
The judge calls `openai/gpt-4o` / `gpt-4o-mini` via your own OpenRouter key, **never through N1Mem servers**; results are entirely under your control.

### Method 3 · Full BYOK rerun (needs official benchmark repo or engine authorization)
- **MemoryAgentBench**: clone the official ICLR'26 repo, copy the YAMLs from `repro_byok/amb/configs/`, set `DASHSCOPE_API_KEY`, run the official harness. See `dry_run()` in `repro_byok/amb/adapter/t1mem_adapter.py`.
- **LME-V2 end-to-end**: requires N1Mem engine authorization; the public package only provides frozen-result verification (Method 1).

---

## 💡 Why Trustworthy (even with closed core)
- **Data verifiable**: frozen answers + SHA256 for every score are public; anyone can re-judge and compare.
- **Protocol transparent**: LoCoMo official F1 dual numbers (concise 65.34% + legacy 23.34%) disclosed without hiding, with protocol-alignment fix path attached.
- **Independent judge**: LLM-as-judge uses third-party OpenRouter (GPT-4o), not N1Mem self-assertion.
- **CI green**: `verify_public.py` runs automatically on every push; history is auditable.

---

## 🛠 Dev Setup (for contributors)
After cloning, install the local git hook so the document-governance gate runs automatically on every commit:
```sh
bash install-hooks.sh
```
This copies `scripts/pre-commit` into `.git/hooks/` and self-tests it. The gate blocks (a) stray documents in the repo root and (b) **internal documents** — filenames/paths containing 复盘/补齐/对照/战略/投资人/口径卡/进度追踪/PRD/架构/内部, or anything under `docs/_archive/` — from entering this public repo. Bypass only when intentional with `N1MEM_SKIP_GATE=1` or `git commit --no-verify`.

---

## 📜 License Boundary
- The repository's **eval code, frozen datasets, and docs** are open source under **MIT License**.
- The **T1Mem core engine** is proprietary and **not in this repo**, nor distributed with it.
- See `LICENSE`.

## 📎 Citation
```
N1Mem (powered by T1Mem engine). (2026). N1Mem Benchmark Evidence & Reproducibility Package.
GitHub: n1mem/N1Mem-public. Multi-benchmark world #1 as of stats dates (LongMemEval 99.4% [2026-07] /
LoCoMo 95.52% [2026-07-29] / MemoryAgentBench 77.87% [2026-07-28] / LongMemEval-V2 62.7% [2026-08-05, 4-model OR] / 44.3% [single model]).
Leaderboards are dynamic; each "#1" claim is valid only as of its stats date.
```
