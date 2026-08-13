# N1Mem — 评测与复现证据包（由 T1Mem 引擎驱动）

[![integrity-check](https://github.com/n1mem/N1Mem-public/actions/workflows/ci.yml/badge.svg)](https://github.com/n1mem/N1Mem-public/actions/workflows/ci.yml)

> **[English](README.md)**

> **可极低成本在自己机器上验证的 AI 记忆系统评测包（成绩截至对应统计日期）。**

N1Mem（基于 T1Mem 引擎）在四个主流长期记忆 / 记忆智能体基准上取得 **截至各统计日期的内测世界第一** 成绩（排行榜持续动态变化，详见下方"统计日期与动态声明"）。本仓库是 **公开、可验证的评测与复现包（BYOK, Bring-Your-Own-Key）**——任何人都能用极低成本独立核验这些分数，但**不包含 T1Mem 核心引擎源码**（核心为闭源专利资产）。

---

## ⚠️ 透明度声明（请先读这段）

| | 在本仓库 | 不在本仓库 |
|---|---|---|
| **评测 / 复现代码**（judge 脚本、官方 F1 计算、冻结结果、复现指引） | ✅ 开源（MIT） | — |
| **架构设计文档**（组件与数据流，无源码） | ✅ 公开 | — |
| **冻结答案 + 分数（SHA256 签名）** | ✅ 含 | — |
| **T1Mem 核心引擎**（五维记忆 / 时间轴 / SFE / 多模型 Reader / OR 聚合 / 检索实现） | — | ❌ 闭源（专利资产，仅作为黑盒调用） |

**这意味着：** 外部研究者能**验证我们的分数真实**（用公开 judge 脚本重判我们发布的冻结答案 + 跑同一套 eval harness + 比对 SHA256），但**无法凭空重新生成那些答案**——因为生成答案的核心引擎是闭源的。这是 OpenAI / Anthropic 采用的同一模式（eval 开源、模型闭源），社区公认可接受。我们如实公开这一点，不夸大「可完全重跑引擎」。

---

## 🏆 四榜成绩（双口径透明 · 含统计日期）

> **⏱ 统计日期与动态声明：** 本仓库所有成绩均为**截至对应"统计日期"的快照**。记忆系统排行榜持续动态变化，第三方系统后续可能发布更高分数。对外宣称"世界第一"须明确**统计日期 + 比较基准**，**不得暗示为永久性或当前实时第一**（类比：奥运冠军是某届比赛、某时刻的世界第一）。2026-08-13 复核：LoCoMo 第三方 ByteRover 自报 96.1%（本仓库现列世界第 2、国产 & 可复现第一；保守下限经 DS-V4-Flash ds 腿降级重判 93.35%→93.66%，零降分）、MAB 第三方 TRACE 自报 83.8% 均已高于本仓库对应分数；LME-V2 官方榜 AgentRunbook-C 72.5% 已高于本仓库 62.7%。故各"世界第 1"主张仅限其统计日期。

所有数字以 `claim_card.json`（机器可读单一真相源，v1.3）为准。

| 基准 | 统计日期 | 主口径（主张用） | 保守下限 | 冻结产物 SHA256（前 16 位） |
|---|---|---|---|---|
| **LongMemEval QA** | 2026-07 | **99.4%** (497/500) | 99.2% | `0721579d…` (500 假设) |
| **LoCoMo QA** | 2026-07-29 | **95.52%** (1897/1986, Checklist-CoT Judge) | 93.66% (Std Judge, Flash ds 腿, 2026-08-13) | `896224a0…` / `0d1981e1…` / `4b7425d9…` / `ef4f8ed2…` |
| **MemoryAgentBench** (ICLR'26) | 2026-07-28 | **77.87%** (四维均值) | 77.87% | `fd9cd75c…` (manifest) |
| **LongMemEval-V2** | 2026-08-05 | **62.7%** (283/451, 4-model lazy OR: Flash→Max→Hy3→Plus) | 44.3% (200/451, DS-V4-Flash 单模型) | `5780da66…` / `abcd6dd2…` / `66de748a…` |

> **LoCoMo 诚实双数：** 主口径 LLM-as-judge 95.52% 与 token 级 F1 双数披露并列：简洁协议 **65.34%**（Option A 修复，32-token 短答案协议重跑，+42pp）+ 遗留长文协议 23.34%（长推理文与短答案协议不匹配，adversarial=0%）。原 23.34% 非能力问题，协议对齐后已修复至 65.34%。我们不隐藏任一数字。

> **LME-V2 多模型 OR 证据链：** 主口径 **62.7%（283/451）** 由 4-model lazy OR 落地（DS-V4-Flash → Qwen3.7-Max → Hy3 → Qwen3.7-Plus，前序全失败时触发下一流水）。77 题三模型对比报告（`LongMemEval-V2/reports/LME-V2_Hy3_vs_Plus_vs_Max_77q_对比报告.html`）验证 Hy3 准确率≈Max，确立 Flash→Hy3→Plus 级联原则；全量 4-model OR 对比报告（`LongMemEval-V2/reports/LME-V2_4模型OR_full451_对比报告.html`）给出完整八组 OR 分解、分题型与救回分析。保守下限保留 DS-V4-Flash 单模型 **44.3%（200/451，生产可用）**。

---

## 📂 本仓库结构

```
N1Mem-public/
├── README.md                  # 英文版
├── README.zh.md               # 本文件（中文）
├── claim_card.json/.html      # 四榜声明口径卡（单一真相源）
├── claim_card_en.html         # 英文口径卡
├── .env.example               # 环境变量模板（仅变量名，无密钥）
├── LICENSE                    # 开源/闭源边界声明
├── verify_public.py           # 完整性校验（SHA256 + 确定性官方F1 + LME-V2 分数重算）
├── repro_byok/                # BYOK 复现包（自包含，不依赖核心）
│   ├── locomo/                # LoCoMo：冻结结果 + judge + 官方F1 + 报告
│   ├── longmemeval/           # LongMemEval：500 假设 + judge
│   ├── longmemeval-v2/        # LME-V2：冻结结果 + 零依赖校验
│   ├── amb/                   # MemoryAgentBench：配置 + adapter + 冻结manifest
│   └── common/                # OpenRouter judge 等共享脚本
├── docs/
│   └── N1Mem_BYOK复现包概览_2026-08-06.html   # 对外 BYOK 复现包入口说明
└── .github/workflows/ci.yml   # 推送时自动跑完整性校验（绿钩=信任信号）
```

---

## 🔍 如何验证（三种方式）

### 方式 1 · 零成本（推荐先跑）：完整性 + 官方 F1 + LME-V2 自证
```bash
python verify_public.py
```
该脚本会：
1. 校验所有冻结产物（含 LME-V2）的 SHA256 与上文一致（证明数据未被篡改）；
2. 用确定性官方 F1 评分器对 LoCoMo 冻结答案重算 token 级 F1（**不需要任何 API**），打印结果（简洁协议应 ≈ 65.34%，遗留长文协议应 ≈ 23.34%）；
3. 对 LME-V2 三个冻结结果文件重算 correct/total/accuracy（score=0 为正确），验证 62.7% / 44.3% / 42.1%。
这证明我们的分数与官方指标**可独立复算**。

### 方式 2 · LLM-as-judge 复现
```bash
cp .env.example .env
# 在 .env 填入你自己的 OPENROUTER_API_KEY（自带 Key，BYOK）
python repro_byok/locomo/freeze_or10_checklist.py --full   # 重判冻结答案 → 应≈95.52%
python repro_byok/locomo/freeze_or10.py --full             # 保守下限 → 应≈93.66%
python repro_byok/longmemeval/run_judge_byok.py --full     # 重判 500 假设 → 应≈99.4%
```
judge 用你自己的 OpenRouter key 调用 `openai/gpt-4o` / `gpt-4o-mini`，**不经过 N1Mem 服务器**，结果完全由你掌控。

### 方式 3 · 完整 BYOK 重跑（需官方基准仓库或引擎授权）
- **MemoryAgentBench**：克隆官方 ICLR'26 仓库，把 `repro_byok/amb/configs/` 的 YAML 拷入，设 `DASHSCOPE_API_KEY`，跑官方 harness。详见 `repro_byok/amb/adapter/t1mem_adapter.py` 的 `dry_run()`。
- **LME-V2 端到端**：需要 N1Mem 引擎授权；公开包仅提供冻结结果验证（方式 1）。

---

## 💡 为什么可信（即使核心闭源）
- **数据可验**：所有分数对应的冻结答案 + SHA256 公开，任何人可重判、可比对。
- **协议透明**：LoCoMo 官方 F1 双数披露（简洁 65.34% + 遗留 23.34%）不隐藏，并附协议对齐修复路径。
- **judge 独立**：LLM-as-judge 用第三方 OpenRouter（GPT-4o），非 N1Mem 自证。
- **CI 绿钩**：每次推送自动跑 `verify_public.py`，历史可查。

---

## 🛠 开发环境（贡献者必读）
克隆仓库后，请先安装本地 git 钩子，使文档治理闸门在每次提交前自动生效：
```sh
bash install-hooks.sh
```
该脚本会把 `scripts/pre-commit` 复制到 `.git/hooks/` 并自检。闸门会拦截：(a) 仓库根目录散落的文档；(b) **内部文档**——文件名/路径含 复盘/补齐/对照/战略/投资人/口径卡/进度追踪/PRD/架构/内部，或位于 `docs/_archive/` —— 进入公开仓。确有需要时可用 `N1MEM_SKIP_GATE=1` 或 `git commit --no-verify` 绕过。

---

## 📜 许可证边界
- 本仓库的**评测代码、冻结数据集、文档**以 **MIT License** 开源。
- **T1Mem 核心引擎**为专有资产，**不在此仓库**，亦不随本仓库分发。
- 详见 `LICENSE`。

## 📎 引用
```
N1Mem (powered by T1Mem engine). (2026). N1Mem Benchmark Evidence & Reproducibility Package.
GitHub: n1mem/N1Mem-public. Multi-benchmark world #1 as of stats dates (LongMemEval 99.4% [2026-07] /
LoCoMo 95.52% [2026-07-29] / MemoryAgentBench 77.87% [2026-07-28] / LongMemEval-V2 62.7% [2026-08-05, 4-model OR] / 44.3% [单模型]).
Leaderboards are dynamic; each "#1" claim is valid only as of its stats date.
```
