# LoCoMo QA — BYOK 复现（支柱 2 / 4）

**目标**：用**你自己的 OpenRouter key** 重新跑一遍 Judge，验证 N1Mem 在 LoCoMo MC10（1,986 题）上的成绩是真实的、可复现的。

## Judge 口径（重要，请先读）

- **LoCoMo 官方事实标准 Judge = `openai/gpt-4o-mini`**。依据：Mem0 评测框架（社区事实标准 harness）默认 judge-LLM 即 gpt-4o-mini；MemMachine 官方博客原文明确："The Mem0 evaluation of LoCoMo benchmark historically uses the OpenAI **gpt-4o-mini** as the default **judge-LLM**"；mflow-benchmarks 等横向评测同样用 `gpt-5-mini(answer) + gpt-4o-mini(judge)`。
- 因此本包**默认 Judge = `openai/gpt-4o-mini`**，与 MemMachine / VAC / Memvid 等国际竞品处于**同一可比口径**。
- 本包提供两个 Judge 变体：
  - **Checklist-CoT Judge**（主口径 95.52%）：`gpt-4o-mini`，max_tokens=200，要求模型逐步核对 checklist 后再给 verdict。
  - **Standard Judge**（保守下限 93.35%）：`gpt-4o-mini`，max_tokens=5，直接输出 yes/no。

## 设计要点

- **Reader 输出已冻结（两套）**：
  - `inputs/locomo_qa_or3_full1986.json` — **OR3 假设**（Qwen 3.7 Max / GLM 5.2 / DS V4-Pro 三家模型，固定产物）。对应主口径**下限 85.75%**。
  - `inputs/locomo_qa_or10_full1986.json` — **OR10 假设**（OR3 三家 + 7 轮救援实验的救援假设并集，共 3,078 条假设；由 `build_or10_merged.py` 汇编，含题目原文 + gold）。对应**冻结主口径 95.52%（Checklist-CoT）/ 93.35%（Standard）**。
- **只重跑 Judge**：你用自己的 `OPENROUTER_API_KEY` 跑 `openai/gpt-4o-mini`，用**与 N1Mem 内部完全一致的 LoCoMo judge prompt**。
- **评分口径一致**：Checklist-CoT 每假设 1 票 checklist 输出 + 1 票最终 verdict；一题只要任一假设通过即计入 OR 并集。

> ✅ **OR10 已冻结**：`locomo_qa_or10_full1986.json`（假设集）+ `locomo_qa_or10_full1986_checklist_frozen_result.json`（95.52%）+ `locomo_qa_or10_full1986_frozen_result.json`（93.35%）+ 对应 `*_frozen_manifest.json`（SHA256 归档）。

## 运行

```bash
cd repro_byok
cp .env.example .env            # 填入你自己的 OPENROUTER_API_KEY
export $(grep -v '^#' .env | xargs)    # Windows: 逐行 set 变量

# ---- 主线：复现 Checklist-CoT 主口径 95.52% ----
python locomo/freeze_or10_checklist.py --smoke 10
python locomo/freeze_or10_checklist.py --full

# ---- 备选：复现 Standard 保守下限 93.35% ----
python locomo/freeze_or10.py --smoke 10
python locomo/freeze_or10.py --full

# ---- 备选：仅复现 OR3 下限 85.75% ----
python locomo/run_judge_byok.py --smoke 10
python locomo/run_judge_byok.py --full
```

输出：
- Checklist-CoT：`locomo/inputs/locomo_qa_or10_full1986_checklist_frozen_result.json` + `_checklist_frozen_manifest.json`
- Standard：`locomo/inputs/locomo_qa_or10_full1986_frozen_result.json` + `_frozen_manifest.json`

## 与官方声明比对

| 口径 | Judge | OR3（下限） | OR10（主口径） |
|------|-------|------------|---------------|
| **Checklist-CoT（本包主口径）** | `gpt-4o-mini` CoT | — | **95.52%（1897/1986）** |
| Standard（保守下限） | `gpt-4o-mini` 5 票 | 84.19%（1672） | **93.35%（1854）** |
| 更严交叉验证 | `gpt-4o` | 89.02%（1768） | 91.89%（1825） |

- 你用默认 `gpt-4o-mini` + Checklist-CoT 复现 OR10 应得 **≈95.52%**（自然方差 ±1pp 内）。
- 原内部声明 96.48% 因依赖宽松 `or_correct` 标记与救援文件历史投票，**无法被独立复现**，故不对外宣称。

## 官方 token-F1 双数披露

LoCoMo 官方指标是 token 级 F1（snap-research/locomo 官方协议）。N1Mem 强制双数披露：

- **简洁协议 65.34%**（主披露，SHA256 `4b7425d9…`）：官方 32-token 短答案协议重跑（deepseek-v4-pro，全量 1986），较遗留长文协议 +42pp。分题型：adversarial 89.24% / open_domain 70.04% / single_hop 57.94% / temporal 41.50% / multi_hop 33.44%。
- **遗留长文协议 23.34%**（透明参考，SHA256 `ef4f8ed2…`）：N1Mem 原生长推理文与官方短答案协议不匹配导致 F1 崩塌，现已修复。

> ⚠️ **公开仓中的 `locomo_qa_or10_concise_full1986.json` 是一个 40 题 stratified slice**（`is_slice: true`），用于快速验证简洁协议效果。完整 1986 题的简洁答案由 N1Mem 引擎生成，对应的完整官方 F1 结果以签名文件 `locomo_qa_or10_concise_full1986_official_f1_result.json`（SHA256 `4b7425d9…`）形式发布。第三方可用 `verify_public.py` 校验该签名文件的完整性。

## 安全

- 本脚本**不含任何硬编码 key**；缺失 `OPENROUTER_API_KEY` 会直接报错退出。
- 你对自己的 key、用量与费用完全负责；N1Mem 看不到、不经手你的 key。

## 全链路模式（可选，需百炼 key）

若你想从检索+Reader 端到端复现（而非用我们冻结的假设），参见顶层 `README.md` 的「Full end-to-end 模式」：设置 `DASHSCOPE_API_KEY`（百炼，Reader 用），本地起 BGE-M3 嵌入服务（8114/8115，免 key），运行引擎脚本重新生成假设，再用本脚本判分。

## 汇编脚本（内部）

- `locomo/build_or10_merged.py` — 汇编 OR10 假设集：OR3 三家 + 7 救援实验 + 题目原文。
- `locomo/freeze_or10_checklist.py` — 对 OR10 假设集重跑 Checklist-CoT Judge 并生成 SHA256 归档。
- `locomo/freeze_or10.py` — 对 OR10 假设集重跑 Standard Judge 并生成 SHA256 归档。
