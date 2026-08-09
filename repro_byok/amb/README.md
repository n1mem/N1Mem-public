# MemoryAgentBench (ICLR'26) — BYOK 复现（支柱 3 / 3）

**目标**：用**你自己的 API key**，通过**官方 MemoryAgentBench harness**，验证 T1Mem 在智能体记忆基准上的成绩。

## 冻结成绩（SHA256 已归档）

| 维度 | 冻结分数 | 配置 | 题数 |
|------|---------|------|------|
| AR · 精准检索 | 81.38% | v6 hybrid-k20-c2048, thinking ON, rn=20 | 50 |
| CR · 冲突解析 | 90.29% | v12, thinking ON, rn=15, KV prefix cache | 600 |
| TTL · 测试时学习 | 80.35% | v12b-opt, thinking OFF, rn=10 | 600 |
| LRU · 长程理解 | 59.48% | v12b-opt, thinking OFF, rn=10 | 171 |
| **简单均分** | **77.87%** | best-per-dimension | 1,421 |
| 报告口径 | 77.38% | (保守值) | — |
| 基线 GPT-5-mini | 60.6% | — | — |

> **分数说明**：冻结文件直接重算得 77.87%（CR=90.29%），报告文档记 77.38%（CR=88.3%）。
> 差异方向对 T1Mem 有利（冻结分更高），详见冻结报告。对外口径可用 77.38%（保守）或 77.87%（冻结值）。

## 为什么 AMB 的 BYOK 形态不同

LoCoMo / LongMemEval 是**问答基准**（有可替换的 Judge）。AMB 是**智能体基准**：由**官方 harness** 对一个 agent 在四类维度上打分。因此 BYOK 不是"重跑 Judge"，而是：

1. 你 `git clone` **官方 MemoryAgentBench 仓库**（ICLR'26 公开，HuggingFace: `ai-hyz/MemoryAgentBench`）。
2. 把 `amb/configs/` 下的 YAML 配置文件复制进 harness 的 `configs/agent_conf/RAG_Agents/glm-5.2/`。
3. 用**你自己的 key** 运行官方 harness（`DASHSCOPE_API_KEY` 给 GLM-5.2 reader）。T1Mem 不经手你的 key。
4. 官方 harness 输出四维分数（AR / CR / TTL / LRU）。
5. 用 `freeze_mab_results.py` 聚合得到最终分数。

## 关键方法论：Best-Per-Dimension

**没有单一统一配置能在四维同时最优。** 核心发现：

| 配置维度 | AR/CR (thinking ON) | TTL/LRU (thinking OFF) |
|----------|---------------------|----------------------|
| AR F1 | **81.38%** | 67.42% (-14pp) |
| CR-MH F1 | **82.00%** | 44.74% (-37pp) |
| TTL ICL acc | 79.60% | **90.60%** (+11pp) |

- **多跳推理（AR/CR）需要 thinking**（chain-of-thought 追踪事实链）
- **分类任务（TTL/LRU）禁用 thinking 更好**（直接判断 > 过度分析）
- **统一对齐 = 总分降 8pp**（77.4 → 69.6），故坚持 best-per-dimension

## 运行

```bash
cd repro_byok
cp .env.example .env            # 填入你自己的 DASHSCOPE_API_KEY（百炼，GLM-5.2 reader 用）
export $(grep -v '^#' .env | xargs)

# 1) 干跑：验证配置 + 打印复现指南（不发任何 API 调用）
python amb/adapter/t1mem_adapter.py

# 2) 验证配置文件完整性
python amb/adapter/t1mem_adapter.py --verify

# 3) 真跑：克隆官方仓库后，用你的 key 调用官方 harness
git clone <官方MemoryAgentBench> official_mab
# 复制 configs:
cp amb/configs/*.yaml official_mab/configs/agent_conf/RAG_Agents/glm-5.2/
# 运行四维:
cd official_mab
python main.py --agent-config t1mem_ar_glm-5.2.yaml --dataset Accurate_Retrieval
python main.py --agent-config t1mem_cr_glm-5.2.yaml --dataset Conflict_Resolution
python main.py --agent-config t1mem_ttl_glm-5.2.yaml --dataset Test_Time_Learning
python main.py --agent-config t1mem_lru_glm-5.2.yaml --dataset Long_Range_Understanding
# 聚合:
python freeze_mab_results.py
```

## 文件清单

| 文件 | 说明 |
|------|------|
| `adapter/t1mem_adapter.py` | 开源适配器薄层（集成契约 + dry-run + 配置清单），**不含核心算法** |
| `configs/t1mem_ar_glm-5.2.yaml` | AR 维度最优配置 |
| `configs/t1mem_cr_glm-5.2.yaml` | CR 维度最优配置 |
| `configs/t1mem_ttl_glm-5.2.yaml` | TTL 维度最优配置 |
| `configs/t1mem_lru_glm-5.2.yaml` | LRU 维度最优配置 |
| `run_agent_byok.py` | BYOK 编排器（环境检查 + dry-run + 官方 harness 调用） |
| `result_schema.json` | 结果 JSON schema |
| `N1Mem_MAB_arXiv_Technical_Report_2026-07-28.html` | arXiv 技术报告（方法论 + 冻结结果 + 复现说明） |

## 冻结产物（在 MemoryAgentBench 仓库内）

| 文件 | 说明 |
|------|------|
| `mab_frozen_manifest.json` | 15 文件 SHA256 归档清单 + 四维分数 |
| `freeze_mab_results.py` | 冻结脚本（从磁盘 JSON 重算分数 + 生成 manifest） |
| `docs/N1Mem_MAB_Frozen_Results_2026-07-28.html` | 冻结报告（人类可读，含 CR 差异说明） |
| `outputs/t1mem-v6-glm-hybrid-k20-c2048/` | AR 结果文件 |
| `outputs/t1mem-v12-glm-cr-*/` | CR 结果文件（6 子集） |
| `outputs/t1mem-v12b-glm-rag-opt-ab/` | TTL + LRU 结果文件 |

## 开源 vs 闭源边界

| 资产 | 公开？ | 说明 |
|------|--------|------|
| Agent YAML 配置（超参数） | ✅ 开源 | 维度特定配置 |
| 适配器薄层（t1mem_adapter.py） | ✅ 开源 | 集成契约 + dry-run，无算法 |
| 冻结结果 + SHA256 清单 | ✅ 公开 | 15 JSON + manifest |
| arXiv 技术报告 | ✅ 公开 | 方法论 + 结果 + 复现说明 |
| 多模型 Reader + OR 聚合 | ❌ 闭源 | 核心商业机密（MAB 未使用） |
| 时间轴 / SFE / 五维记忆 | ❌ 闭源 | 专利资产（MAB 未使用） |
| 检索引擎内部实现 | ❌ 闭源 | 仅 API 黑盒调用 |

## 安全

- 包内**无任何硬编码 key**；缺失 key 时给出明确报错。
- 你对自身 key、用量、费用负责；T1Mem 不经手你的 key。
- BYOK 付费规则：谁调 API 跑 harness，谁付费，除非我们主动邀请的。
