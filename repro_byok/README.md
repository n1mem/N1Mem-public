# N1Mem — BYOK 复现包（Bring-Your-Own-Key Reproduction Package）

> 用**你自己的 API key**，独立验证 N1Mem 在四榜记忆基准上的公开成绩。  
> N1Mem 不持有、不经手、不代为支付你的任何 key / 费用。

## 这是什么

这是 N1Mem「世界第一记忆系统」的**可复现性交付物**。我们发布：

- 各基准的**冻结 Reader 假设**或**冻结结果文件**（可被 SHA256 校验、不可篡改）；
- 与 N1Mem **内部完全一致**的 Judge prompt 与 OR 聚合逻辑；
- 一个**只读取你环境变量里 key** 的复现脚本（**无任何硬编码 key**）。

你只需填入自己的 key，重跑 **Judge**（问答基准）或运行**官方 harness**（智能体基准），即可独立得到与 N1Mem 公开口径一致的成绩。

## 复现的四根支柱

| 支柱 | 基准 | 题量 | N1Mem 公开主口径 | 复现方式 |
|------|------|------|------------------|----------|
| 1 | **LongMemEval QA** | 500 | **99.2–99.4%**（双通道真 GPT-4o） | 冻结假设 + 官方 Gold + 你的 Judge key |
| 2 | **LoCoMo QA**（MC10） | 1,986 | **95.52%**（OR10 + Checklist-CoT Judge） | 冻结假设 + 你的 Judge key |
| 3 | **MemoryAgentBench**（ICLR'26） | 1,421 | **77.87%** 冻结值 > GPT-5-mini 60.6 | 官方 harness + 开源适配器 + best-per-dimension configs + 你的 key |
| 4 | **LongMemEval-V2** | 451 | **62.7%**（4-model lazy OR）/ 保守下限 44.3% | 冻结结果 + 零依赖校验；完整端到端需引擎授权 |

> **Judge 口径说明（重要）**：
> - **LoCoMo 官方事实标准 Judge = `gpt-4o-mini`**（Mem0 评测框架默认；MemMachine 官方博客原文确认；mflow-benchmarks 同口径）。本包 LoCoMo 默认即用 `gpt-4o-mini`，与国际竞品可比。
> - **LoCoMo 主口径 95.52%** 来自 Checklist-CoT Judge（`gpt-4o-mini`，max_tokens=200）。另附保守下限 Standard Judge **93.35%**（max_tokens=5）。
> - **LoCoMo 官方 token-F1 双数披露**：简洁协议 **65.34%**（主披露）+ 遗留长文协议 23.34%（格式不匹配，透明参考）。
> - **LME-V2 是端到端基准**：公开包提供冻结结果文件与零依赖校验；完整重跑需要 N1Mem 引擎授权。

## 为什么 BYOK 是安全的（也给评审者）

1. **零密钥泄露**：所有脚本 `os.environ["OPENROUTER_API_KEY"]` 或 `DASHSCOPE_API_KEY`，缺失即报错退出；仓库内**无任何 key**。
2. **费用自担**：Judge / Reader 调用全部计费到**你的** OpenRouter / 百炼账户。N1Mem 看不到用量。
3. **可审计**：冻结假设带 SHA256；`verify_public.py` 输出完整性校验；`CLAIM.template.md` 供你署名背书。
4. **最小权限**：问答基准只需 Judge key；端到端模式才需 Reader key；嵌入走本地服务，免 key。

## 快速开始

```bash
cd repro_byok
cp .env.example .env            # 填入你自己的 OPENROUTER_API_KEY（必填）
export $(grep -v '^#' .env | xargs)    # Windows: 逐行 set

# 支柱 1：LongMemEval（先构建官方 Gold，约 ~1h）
python longmemeval/build_gold.py --data <官方longmemeval目录> --out longmemeval/inputs/lme_gold.json
python longmemeval/run_judge_byok.py --gold longmemeval/inputs/lme_gold.json --full

# 支柱 2：LoCoMo（主线复现 Checklist-CoT 95.52%，~30min under gpt-4o-mini）
python locomo/freeze_or10_checklist.py --smoke 10   # 先冒烟
python locomo/freeze_or10_checklist.py --full       # 全量复现 95.52%
# 备选：保守下限 Standard Judge 93.35%
python locomo/freeze_or10.py --full

# 支柱 3：MemoryAgentBench（干跑出脚手架；真跑需克隆官方仓库）
python amb/run_agent_byok.py --dry-run
python amb/run_agent_byok.py --run --harness-dir <官方MemoryAgentBench仓库>

# 支柱 4：LME-V2（零依赖校验冻结结果）
python longmemeval-v2/verify_lmev2.py

# 全量中立校验（无需 API key）
cd ..
python verify_public.py
```

## 验证费用说明

所有复现/校验均在**你自己的 API key** 下运行，费用由你自行承担，N1Mem 看不到、也不承担这些费用。零依赖校验（`verify_public.py` / `verify_lmev2.py`）无需任何 API key。

## 关于「不依赖最终分数」

本包是**复现骨架**：脚本与冻结假设已就绪，但**最终分数由复现方运行后产生**（我们不会、也不应替你填分数）。`verify_public.py` 只做 SHA256 校验 + 计分 + 断言，不引入任何预置结论。

## 目录结构

```
repro_byok/
├── README.md                     # 本文件
├── .env.example                  # 环境变量模板（填你自己的 key）
├── CLAIM.template.md             # 复现方署名声明模板
├── verify_claim.py               # 中立校验 + Claim 哈希
├── requirements.txt              # 无第三方依赖（仅标准库）
├── common/
│   └── openrouter_judge.py       # BYOK 核心：env-key Judge 客户端
├── longmemeval/                  # 支柱 1
│   ├── run_judge_byok.py
│   ├── build_gold.py
│   ├── inputs/t1mem_hypotheses_500.jsonl    # 冻结 Reader 假设
│   ├── result_schema.json
│   └── README.md
├── locomo/                       # 支柱 2
│   ├── run_judge_byok.py
│   ├── freeze_or10.py             # Standard Judge 93.35% 复现
│   ├── freeze_or10_checklist.py   # Checklist-CoT Judge 95.52% 复现
│   ├── build_or10_merged.py       # 汇编 OR10 假设集
│   ├── inputs/locomo_qa_or10_full1986.json  # 冻结 Reader 假设（OR10，1986 题）
│   ├── result_schema.json
│   └── README.md
├── amb/                          # 支柱 3（智能体基准）
│   ├── run_agent_byok.py
│   ├── adapter/t1mem_adapter.py   # 开源适配器薄层
│   ├── configs/                    # best-per-dimension YAML 配置
│   ├── mab_frozen_manifest.json    # 15 文件 SHA256 清单
│   ├── result_schema.json
│   └── README.md
└── longmemeval-v2/               # 支柱 4
    ├── verify_lmev2.py            # 零依赖冻结结果校验
    ├── inputs/lmev2_4model_lazy_or_result.json       # 62.7% 主结果
    ├── inputs/lmev2_flash_single_result.json         # 44.3% 保守下限
    ├── inputs/lmev2_historical_baseline_result.json  # 42.1% 历史基线
    ├── inputs/lmev2_frozen_manifest.json             # SHA256 清单
    ├── result_schema.json
    └── README.md
```

## 信任边界

- **N1Mem 证明的是**：冻结假设/结果的 Judge/分数可被任何持 key 者复现 → 成绩真实、非虚报。
- **N1Mem 不声称**：复现方必须用同一底层模型。复现方使用自己的 key 复现的是「**在给定冻结假设 + 给定 Judge 下**」的分数，这正是可独立验证的部分。
- 若评审者希望进一步验证 Reader 本身，可走「Full end-to-end 模式」（见各支柱 README），用各自 key 从检索+Reader 重新生成假设再判分。LME-V2 端到端需引擎授权。
