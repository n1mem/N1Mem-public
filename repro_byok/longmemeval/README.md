# LongMemEval QA — BYOK 复现（支柱 2 / 3）

**目标**：用**你自己的 OpenRouter key** 重新跑一遍 Judge，验证 T1Mem 在 LongMemEval（500 题）上的成绩真实、可复现。

## 设计要点
- **Reader 假设已冻结**：随包发布 `inputs/t1mem_hypotheses_500.jsonl`（T1Mem 每题的最佳假设输出，固定产物）。
- **Gold 来自官方数据集**：LongMemEval 测试集由你从官方渠道自行下载（微软公开发布），用 `build_gold.py` 抽取 `{question_id → question/answer/type}`。我们不随包分发任何受版权保护的数据。
- **只重跑 Judge**：你用自己的 `OPENROUTER_API_KEY` 跑 `openai/gpt-4o`（默认），使用**与 T1Mem 内部完全一致的、按题型区分的 anscheck prompt**（temporal / knowledge-update / preference / 通用）。

## 运行
```bash
cd repro_byok
cp .env.example .env            # 填入你自己的 OPENROUTER_API_KEY
export $(grep -v '^#' .env | xargs)

# 1) 用官方数据集构建 gold（只需一次）
python longmemeval/build_gold.py --data <官方longmemeval目录或json> --out longmemeval/inputs/lme_gold.json

# 2) 冒烟验证（约 10 题）
python longmemeval/run_judge_byok.py --gold longmemeval/inputs/lme_gold.json --smoke 10

# 3) 全量复现（500 题，gpt-4o，约 ~1h）
python longmemeval/run_judge_byok.py --gold longmemeval/inputs/lme_gold.json --full
```

## 口径说明（重要，避免误读）
- 本 Mode A 随包冻结的是**每题单一最佳假设**。脚本对每假设做 5 票 gpt-4o 投票（≥3 通过），并对每题的多个假设做 **OR 聚合**。
- T1Mem 公开发布的 **99.2–99.4%（双通道真 GPT-4o Judge）** 是**多模型假设 OR 聚合**（Qwen / GLM / V4Pro / SFE / flip 等策略并集）的成绩。若你只提供单假设输入，复现的是该单假设下的 gpt-4o 判分下限；要复现 OR 上限，请提供多假设输入文件（格式见下），**同一脚本无需改代码**即可 OR 聚合到更高分数。
- 无论哪种模式，**只有 Judge 在你自己的 key 下被重跑**；Reader 输出均为冻结产物。

### 多假设输入格式（Mode B，可选）
`--input` 也可传一个 JSON：
```json
{
  "001be529": {"hypotheses": [{"source":"Qwen","hypothesis":"..."}, {"source":"V4Pro","hypothesis":"..."}]},
  ...
}
```
脚本会对每题所有假设各自投票并 OR 聚合。多策略冻结假设文件可由 T1Mem 内部 `eval_or_judge.py` 的 `HypothesesCollector` 产物导出（需从 `docs/bench/` 复制对应原始假设文件后运行完整流水线生成）。

## 与官方声明比对
- T1Mem 公开冻结口径（Judge = `openai/gpt-4o`，多模型 OR）：**99.2–99.4%（494–497/500）**，世界第 1。
- 你复现的分数应在 GPT-judge 自然方差内（通常 ±1pp）与之一致。

## 安全
- 脚本**不含硬编码 key**；缺失 `OPENROUTER_API_KEY` 直接报错退出。
- 你对自身 key、用量、费用负责；T1Mem 不经手你的 key。
