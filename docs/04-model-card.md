---
license: apache-2.0
base_model: Qwen/Qwen3-1.7B
tags:
  - decision-making
  - qwen3
  - qlora
  - llama-cpp
  - gguf
  - protocol-engine
pipeline_tag: text-generation
language:
  - zh
---

# 衡决 HengJue-1.7B — 六闸门对齐的本地快速决策模型

按《李紫圣思维与价值体系共识文件》v1.0 改造**架构与权重**的本地快速决策模型：以 Qwen3-1.7B 为基座，用 66 条按共识文件直书的种子语料做 QLoRA 微调（GTX 1060 3GB / Pascal sm_61 实测可训），对齐「先审前提再答 / 只说可证伪的话 / 不代行裁决 / 不垄断度量 / 尊重创造者 / 消除偏见傲慢 / 透明记录」七条请求。

**唯一内核：价值度量权必须回归价值创造者本人。**

对标目标：Jev AI（TypeSafe 的 System 1 决策模型）——结构化的快速决策输出，且前提审计、可证伪预期、不代行裁决三项为其所无。

## 训练方法

| 项 | 值 |
|---|---|
| 基座 | Qwen3-1.7B（Apache 2.0） |
| 方法 | QLoRA（bitsandbytes NF4 + fp16 compute，Pascal 无 bf16） |
| LoRA | r=16 / alpha=32 / 全部 proj 模块 |
| 数据 | 66 条种子语料（六闸门类别各 11 条，含 6 条缺陷问题；falsifiable 字段 66/66 覆盖） |
| 训练 | 2 epoch，loss 3.622 → 2.054（GTX 1060 3GB 实测） |
| 产出 | 合并 → F16 GGUF → Q4_K_M 量化（1050MiB，5.12 BPW） |

完整管线（下载 → 训练 → 合并 → 量化 → 基准）见代码仓库：
**https://github.com/mob19898848881-prog/decision-core**

## 基准成绩（DQB，66 样本同语料，诚实口径）

| 指标 | CPU 基线 | 终版（本权重） | 目标 |
|---|---|---|---|
| choice_accuracy | 0.450 | 0.683 | 0.80 |
| premise_audit_cov | 0.560 | 0.788 | 1.00 |
| falsifiable_rate | 0.420 | 0.803 | 0.95 |
| adjudication_ok | 0.300 | 0.803 | 1.00 |
| latency_p50（GTX 1060） | — | 11.9s | 1.5s |

条件合规率（有输出的 57 样本）：G2 通过 53/57 = 93%，G3 同为 93%；53 个 deadline 全为严格未来日期。**与 0.95 目标的剩余差距主要是基础设施损耗（瞬时 socket 错误），不是模型质量**——引擎侧已加传输层指数退避重试。

诚实声明：falsifiable 0.803 是在「GBNF 语法约束 + 日期锚定提示 + 严格 G2（deadline ≥ 今天）」三件套下的成绩；无锚定时模型只会模式匹配预训练日期串（52/66 输出 2025-01-01 式过去日期），真实率仅 0.015。价值判断类内容质量（choice_accuracy）是当前最大缺口，须 660 条蒸馏语料扩展。

## 使用方法

```bash
# llama.cpp b12000+（Qwen3 必须 --reasoning off，否则输出全进思考段）
llama-server -m qwen3-1.7b-hengjue-q4_k_m.gguf \
  -ngl 99 -c 8192 --port 8081 -t 6 --reasoning off \
  --grammar-file gbnf_decision.gbnf
```

- **必须加 `--grammar-file`**（GBNF 语法把输出锁进协议 JSON 骨架）：解析失败从 23% 降到 3%，falsifiable 字段结构必现，无重试轮次（延迟 -31%）
- 引擎侧自动注入日期锚定（当天日期 + 未来示例），否则 deadline 会退化成过去日期
- 请求体建议带 `repeat_penalty: 1.1`（抑制无背景短问题的复读退化）

配合六闸门决策协议引擎（G0 问题编译 → 路由 → G1–G5 → ADD-only 哈希链账本）使用，见代码仓库 `decision_engine/`。

## 文件清单

| 文件 | 说明 |
|---|---|
| `qwen3-1.7b-hengjue-q4_k_m.gguf` | 合并量化后的完整模型（1050MiB） |
| `lora-adapter/` | LoRA 适配器（69.8MB，可自行合并到基座） |
| `gbnf_decision.gbnf` | 协议 JSON 的 GBNF 语法约束（推理时必加） |

## 已知局限（如实声明）

1. **选择判断质量有限**（0.683 vs 0.80）：66 条种子教不会「调研先行 / 对赌」类价值判断，待 660 条蒸馏语料
2. **延迟 11.9s p50**：GTX 1060（~22 tok/s）跑全字段协议 JSON 的物理水平，短决策 1.1s
3. **Pascal 老架构专用训练栈**：CUDA 12.4（CUDA 13 已弃 Pascal）；transformers 5.x API 兼容已处理

## 许可

模型权重继承基座许可 **Apache 2.0**；代码仓库为 **MIT**（© 2026 李紫圣）。
