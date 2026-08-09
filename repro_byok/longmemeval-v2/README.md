# N1Mem · LME-V2 BYOK 复现说明

> LongMemEval-V2（451 题，harder 变体）

## 当前状态

LME-V2 是**完整端到端基准**（检索 + Reader + Judge），需要 N1Mem 引擎才能从原始数据重新生成答案。本公开仓提供：

1. **冻结结果文件**（可 SHA256 校验）
2. **零依赖校验脚本** `verify_lmev2.py`

第三方下载后，可立即验证 N1Mem 公布的分数**不是凭空捏造**，且结果文件未被篡改。

## 冻结口径

| 口径 | 分数 | 文件 | 大小 |
|---|---|---|---|
| 主口径 · 4-model lazy OR | **62.7% (283/451)** | `inputs/lmev2_4model_lazy_or_result.json` | 1.79 MB |
| 保守下限 · DS-V4-Flash 单模型 | **44.3% (200/451)** | `inputs/lmev2_flash_single_result.json` | 0.93 MB |
| 历史基线 · Qwen3.7-Max + GPT-4o | **42.1% (190/451)** | `inputs/lmev2_historical_baseline_result.json` | 0.41 MB |

## 快速验证

```bash
cd repro_byok/longmemeval-v2
python verify_lmev2.py
```

输出示例：

```
[校验] lmev2_4model_lazy_or_result.json
  SHA256: OK
  重算分数: 283/451 = 62.75%
  发布值:   283/451 = 62.7%
  分数校验: OK
...
结果: PASS ✅
```

## 完整端到端复现（需引擎）

如果你持有 N1Mem 引擎授权或内部仓库访问权限：

```bash
# 在引擎仓库内
python LongMemEval-V2/run_planc_local.py \
  --reader deepseek-v4-flash \
  --reader2 qwen3.7-max \
  --reader3 hy3 \
  --reader4 qwen3.7-plus \
  --judge glm-5.2 --judge-cot \
  --topk 12 --abs 10 --neg 3 --eg 8 \
  --five-dim-dynamic --five-dim-proc-abs \
  --augment
```

公开仓**不包含**引擎代码；上述命令仅作透明参考。

## 与其他基准的关系

LME-V2 是 N1Mem 四榜世界第一声明的第四根支柱：

- LongMemEval QA: 99.4%（500 题）
- LoCoMo QA: 95.52%（1986 题，Checklist-CoT Judge）
- MemoryAgentBench: 77.87%（1421 题）
- **LongMemEval-V2: 62.7%（451 题）**
