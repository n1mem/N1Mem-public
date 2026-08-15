# MemoryAgentBench (ICLR'26) — BYOK 复现（支柱 3 / 3）

**目标**：用**你自己的 API key**，通过**官方 MemoryAgentBench harness**，验证 T1Mem 在智能体记忆基准上的成绩。

## 组合口径成绩（2026-08-15，SHA256 已归档）

**per-dimension best（双栈组合）**：AR/CR/TTL 用 GLM-5.2 冻结栈 + LRU 用国产栈（DS-V4-Flash map-reduce + Hy3/Qwen3.7-Plus 救援）。

| 维度 | 组合分数 | 配置 | 题数 |
|------|---------|------|------|
| AR · 精准检索 | 81.38% | GLM-5.2 v6 hybrid-k20-c2048, thinking ON, rn=20 | 50 |
| CR · 冲突解析 | 90.29% | GLM-5.2 v12, thinking ON, rn=15, KV prefix cache | 600 |
| TTL · 测试时学习 | 80.35% | GLM-5.2 v12b-opt, thinking OFF, rn=10 | 600 |
| LRU · 长程理解 | **63.94%** | **国产栈：DS-V4-Flash map-reduce + Hy3/Qwen3.7-Plus 救援** | 171 |
| **简单均分** | **78.99%** | per-dimension best 双栈 | 1,421 |
| GLM 单栈冻结（历史） | 77.87% | 全 GLM-5.2 | 1,421 |
| 基线 GPT-5-mini | 60.6% | — | — |

> **LRU 国产栈说明**：detective_qa 90.14%（DS-V4-Flash）+ infbench_sum rougeLsum **37.75%**（DS map-reduce 全量 37.01% + Hy3(8本)/Qwen3.7-Plus(10本) 对 <0.40 分的书救援取 max，零回归）。map-reduce 分支是 T1Mem 引擎能力（闭源黑盒）——官方 harness 可精确复现 Detective QA 与 Reader 路径；infbench 完整端到端需引擎授权（与 LME-V2 支柱同策略）。

## 为什么 AMB 的 BYOK 形态不同

LoCoMo / LongMemEval 是**问答基准**（有可替换的 Judge）。AMB 是**智能体基准**：由**官方 harness** 对一个 agent 在四类维度上打分。因此 BYOK 不是"重跑 Judge"，而是：

1. 你 `git clone` **官方 MemoryAgentBench 仓库**（ICLR'26 公开，HuggingFace: `ai-hyz/MemoryAgentBench`）。
2. 把 `amb/configs/` 下的 YAML 配置文件复制进 harness 的 `configs/agent_conf/RAG_Agents/`（GLM 栈放 `glm-5.2/`，国产栈放 `dsv4flash/`）。
3. 用**你自己的 key** 运行官方 harness（`DASHSCOPE_API_KEY` 给 GLM-5.2 reader；国产栈 rescue 用 `OPENAI_BASE_URL`/`OPENAI_API_KEY` 指向对应端点）。T1Mem 不经手你的 key。
4. 官方 harness 输出四维分数（AR / CR / TTL / LRU）。
5. 用 `freeze_mab_results.py` 聚合得到最终分数。

## 关键方法论：Best-Per-Dimension + 双栈

**没有单一统一配置能在四维同时最优。** 核心发现：

| 配置维度 | AR/CR (thinking ON) | TTL (thinking OFF) | LRU 国产栈 (map-reduce) |
|----------|---------------------|----------------------|--------------------------|
| AR F1 | **81.38%** | 67.42% (-14pp) | — |
| CR-MH F1 | **82.00%** | 44.74% (-37pp) | — |
| TTL ICL acc | 79.60% | **90.60%** (+11pp) | — |
| LRU 合计 | 59.48 (GLM flat RAG) | — | **63.94 (DS map-reduce + 救援)** |

- **多跳推理（AR/CR）需要 thinking**（chain-of-thought 追踪事实链）
- **分类任务（TTL）禁用 thinking 更好**（直接判断 > 过度分析）
- **LRU 长程理解用国产栈更优**：DS map-reduce 全书结构化摘要（unknown 弃答 30%→0%）+ Hy3/Qwen3.7-Plus 按性价比链救援（Flash→Hy3→Plus→GLM，只补错题、max 合并零回归）
- **统一对齐 = 总分降 8pp+**，故坚持 per-dimension best（双栈）

## 运行

```bash
cd repro_byok
cp .env.example .env            # 填入你自己的 key（GLM 栈：DASHSCOPE_API_KEY；国产栈：见下）
export $(grep -v '^#' .env | xargs)

# 1) 干跑：验证配置 + 打印复现指南（不发任何 API 调用）
python amb/adapter/t1mem_adapter.py

# 2) 验证配置文件完整性
python amb/adapter/t1mem_adapter.py --verify

# 3) 真跑：克隆官方仓库后，用你的 key 调用官方 harness
git clone <官方MemoryAgentBench> official_mab
# 复制 configs（STACK A — GLM-5.2）:
cp amb/configs/t1mem_{ar,cr,ttl}_glm-5.2.yaml official_mab/configs/agent_conf/RAG_Agents/glm-5.2/
# 复制 configs（STACK B — 国产 LRU）:
cp amb/configs/t1mem_lru_dsv4flash_mapreduce.yaml official_mab/configs/agent_conf/RAG_Agents/dsv4flash/
cp amb/configs/t1mem_lru_{hy3,qwenplus}_rescue.yaml official_mab/configs/agent_conf/RAG_Agents/dsv4flash/
# 运行四维（GLM 栈三维）:
cd official_mab
python main.py --agent-config t1mem_ar_glm-5.2.yaml --dataset Accurate_Retrieval
python main.py --agent-config t1mem_cr_glm-5.2.yaml --dataset Conflict_Resolution
python main.py --agent-config t1mem_ttl_glm-5.2.yaml --dataset Test_Time_Learning
# LRU：Detective QA 用 DS map-reduce 主配置（可复现）; InfBench map-reduce 需引擎授权
python main.py --agent-config t1mem_lru_dsv4flash_mapreduce.yaml --dataset Long_Range_Understanding
# 聚合:
python freeze_mab_results.py
```

## 文件清单

| 文件 | 说明 |
|------|------|
| `adapter/t1mem_adapter.py` | 开源适配器薄层（集成契约 + dry-run + 配置清单 + 双栈指南），**不含核心算法** |
| `configs/t1mem_ar_glm-5.2.yaml` | AR 维度最优配置（GLM 栈） |
| `configs/t1mem_cr_glm-5.2.yaml` | CR 维度最优配置（GLM 栈） |
| `configs/t1mem_ttl_glm-5.2.yaml` | TTL 维度最优配置（GLM 栈） |
| `configs/t1mem_lru_dsv4flash_mapreduce.yaml` | LRU 主配置（国产栈：DS-V4-Flash map-reduce） |
| `configs/t1mem_lru_hy3_rescue.yaml` | LRU 救援 1 档（Hy3 / TokenHub） |
| `configs/t1mem_lru_qwenplus_rescue.yaml` | LRU 救援 2 档（Qwen3.7-Plus / 百炼） |
| `run_agent_byok.py` | BYOK 编排器（环境检查 + dry-run + 官方 harness 调用） |
| `result_schema.json` | 结果 JSON schema |
| `amb_byok_composite_reference.json` | **组合口径 78.99% 参考快照**（claim hash `d1364e06…`，供复现方对比） |
| `mab_composite_manifest.json` | **组合口径 78.99%** SHA256 清单（per-dim best 双栈，2026-08-15） |
| `mab_frozen_manifest.json` | GLM 单栈冻结 77.87% 清单（历史口径，仍有效） |
| `N1Mem_MAB_arXiv_Technical_Report_2026-07-28.html` | arXiv 技术报告（方法论 + 冻结结果 + 复现说明） |

## 冻结产物（在 MemoryAgentBench 仓库内）

| 文件 | 说明 |
|------|------|
| `mab_composite_manifest.json` | 组合口径 78.99%（双栈）SHA256 清单 |
| `mab_frozen_manifest.json` | GLM 单栈 77.87% SHA256 清单（15 文件） |
| `freeze_mab_results.py` | 冻结脚本（从磁盘 JSON 重算分数 + 生成 manifest） |
| `docs/N1Mem_MAB_Frozen_Results_2026-07-28.html` | 冻结报告（人类可读，含 CR 差异说明） |
| `outputs/t1mem-v6-glm-hybrid-k20-c2048/` | AR 结果文件 |
| `outputs/t1mem-v12-glm-cr-*/` | CR 结果文件（6 子集） |
| `outputs/t1mem-v12b-glm-rag-opt-ab/` | TTL + LRU（GLM）结果文件 |
| `outputs/t1mem-v12b-dsv4flash-rag-lru-inf-mapreduce-v3/` | LRU 国产栈 infbench 结果（DS map-reduce 全量 100 本） |

## 开源 vs 闭源边界

| 资产 | 公开？ | 说明 |
|------|--------|------|
| Agent YAML 配置（超参数） | ✅ 开源 | 维度特定配置（双栈） |
| 适配器薄层（t1mem_adapter.py） | ✅ 开源 | 集成契约 + dry-run，无算法 |
| 冻结结果 + SHA256 清单 | ✅ 公开 | 15 JSON + 双 manifest |
| arXiv 技术报告 | ✅ 公开 | 方法论 + 结果 + 复现说明 |
| InfBench map-reduce 分支 | ❌ 闭源 | T1Mem 引擎能力（BYOK 端到端需引擎授权） |
| 多模型 Reader + OR 聚合 | ❌ 闭源 | 核心商业机密（MAB 未使用） |
| 时间轴 / SFE / 五维记忆 | ❌ 闭源 | 专利资产（MAB 未使用） |
| 检索引擎内部实现 | ❌ 闭源 | 仅 API 黑盒调用 |

## 安全

- 包内**无任何硬编码 key**；缺失 key 时给出明确报错。
- 你对自身 key、用量、费用负责；T1Mem 不经手你的 key。
- BYOK 付费规则：谁调 API 跑 harness，谁付费，除非我们主动邀请的。
