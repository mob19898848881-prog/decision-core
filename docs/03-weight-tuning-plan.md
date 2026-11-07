# 衡决·Decision Core — 权重改造方案（LoRA 微调）

> 目标：把共识文件的操作层（七请求 + 关键命题）从提示词层**内化进权重**，让快路径模型在协议框架外也保持决策品格。
> 硬件前提：GTX 1060 3GB（Pascal sm_61）/ 16GB RAM / i5-9400F。

---

## 1. 可行性核实（关键结论均有来源）

| 事实 | 结论 | 来源与分级 |
|---|---|---|
| bitsandbytes NF4/FP4 量化与 8-bit 优化器支持 **Pascal（CC 6.0+，GTX 10X0）** | QLoRA 可在本机 GPU 运行 | bitsandbytes 官方文档（HF transformers v4.57 + 安装指南）★★★ |
| Windows wheel（CUDA 11.8–12.6 构建）目标含 **sm50/sm60/sm75…sm90** | 必须锁定 CUDA 12.x 系 bnb 版本；新版（CUDA 12.8+）Windows wheel 仅 sm70+ | 同上，安装指南 wheel 表 ★★★ |
| LLM.int8() 需 Turing（7.5+） | 不用 int8 推理路径 | 同上 ★★★ |
| PyTorch 对 sm_61 的支持随 CUDA 版本漂移 | setup 脚本运行**实测门**（tiny matmul + NF4 测试），失败即回退 CPU 路径，不静默 | 工程纪律（A2） |
| 小模型 + 每域千条级 LoRA 数据可显著提升 | 1.7B 路线成立 | DistilQwen2.5（arXiv 2504.04030，~100 万对，IFEval +5.85）★★★；Atomight-V2.5-1.7B（免费 T4，每域 ~2000 条）★★ |

## 2. 训练数据构造（蒸馏 + 人工种子）

### 2.1 语料 schema（每行一个样本）

```json
{
  "id": "G1-0007",
  "category": "premise_audit|falsifiability|no_proxy_adjudication|value_sovereignty|bias_arrogance|transparent_record",
  "situation": "情境（中文，含完整背景）",
  "question": "待决策问题（缺陷类样本含预设注入/伪开放/锚定）",
  "allowed_answers": ["选项A", "选项B", "..."],
  "expected": {
    "choice": "选项B",
    "confidence": 0.82,
    "premise_flags": ["隐含前提：..."],
    "defect": "presupposition|pseudo_open|anchor|none",
    "falsifiable": {"deadline": "2026-11-14", "metric": "…"},
    "adjudication": "user",
    "notes": "为什么是这个答案（标注理由）"
  }
}
```

### 2.2 六大数据类别（对齐共识文件）

| 类别 | 对应共识条款 | 样本设计 | 目标条数 |
|---|---|---|---|
| premise_audit 前提审计 | 请求 1 / 命题 10 | 30% 为缺陷问题（预设注入、伪开放、锚定操纵），期望行为=指出缺陷并重写问题，**禁止直接作答** | 120 |
| falsifiability 可证伪 | 请求 3 / 命题 12 | 预测类决策，必须产出 deadline + 可观测 metric；反例=空泛断言 | 120 |
| no_proxy_adjudication 不代行裁决 | 请求 4 / 命题 9 | 高风险/价值权衡场景，期望行为=给方案+代价+交还裁决；反例=替用户拍板 | 120 |
| value_sovereignty 价值度量权 | 请求 5 / 命题 4 | 涉及"什么是好/值多少"的场景，期望=拒绝垄断价值定义，辅助测量 | 100 |
| bias_arrogance 偏见傲慢 | 请求 7 / 命题 2 | 对抗集：傲慢措辞、贬低旧事物/失败者、静默补全；期望=检出并修正 | 100 |
| transparent_record 透明记录 | 请求 2 / 命题 6 | 残缺场景（信息不足/通道故障），期望=显式声明缺失而非伪装齐备 | 100 |

**合计 660 条目标**。分层生产：
- **L0 种子层（本会话已产）**：`data/seed_corpus.jsonl`，由 Step-5 按共识文件直书 66 条（每类 11 条），保证无外部依赖可用。
- **L1 蒸馏层（使用者自配置）**：`scripts/gen_corpus.py` 调用云端 OpenAI 兼容通道（默认示例：DeepSeek 出题与作答、Kimi/Moonshot 证伪筛题——沿用 triune 双模型互校结构），从 L0 种子扩展至 660 条。**密钥从环境变量读取，不落盘、不由本我读写**（作者铁律：env 为禁区）。下载使用者运行 `scripts/setup_gen_env.ps1` 交互配置（SecureString 输入不回显，密钥仅存当前会话），或照 `configs/env.example` 手动设置；不配置则停步 L0 种子层（66 条已可跑通全链路）。

### 2.3 数据质控（对应极我证伪角色）

1. Kimi-K3 对每条生成样本做证伪式审查：答案是否唯一合理？理由是否可证伪？不合格即弃。
2. 代码校验：schema 完整性、choice ∈ allowed_answers、defect 样本的期望必须是"拒绝作答并重写"。
3. 去重：situation+question 哈希去重。
4. 分裂：train 90% / dev 10%，dev 仅用于早停观测，不进梯度。

## 3. 训练配置（QLoRA）

| 项 | 值 | 说明 |
|---|---|---|
| 基座 | Qwen3-1.7B-Instruct-2507（缺失则 Qwen3-1.7B + enable_thinking=False） | 与快路径推理模型同源，保证适配器可直接合并 |
| 量化 | bnb NF4 + double quant | Pascal 官方支持路径 |
| LoRA | r=16, alpha=32, dropout=0.05, target=q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj | 决策任务需全线性层覆盖 |
| 序列 | 512（OOM 则 256 → 128，脚本自动降级） | 决策样本短 |
| batch | per_device 1 × grad_accum 8 | 3GB 显存 |
| 优化器 | paged_adamw_8bit | 显存 + Pascal 支持 |
| 精度 | fp16（**Pascal 不支持 bf16**，禁 bf16） | sm_61 硬约束 |
| lr / epoch | 2e-4 余弦 / 3 epochs（660 样本 ≈ 165 步/epoch） | 小数据防过拟合 |
| 梯度检查点 | 开 | 显存必要 |
| 预计耗时 | GPU：1.5–3h；CPU 回退：6–12h | 165 步 × 3 epoch ≈ 500 步量级 |

**训练三闸门（代码强制，缺一不可）**：
1. 训练前：NF4 实测门（见 setup_train_env.ps1）；
2. 训练中：dev loss 记录 + 每 epoch 存 checkpoint；
3. 训练后：合并 → 量化 → **DQB 基准 before/after 对比**，协议违背率上升即回滚（保留 base 权重，零回归）。

## 4. 合并与量化流程

```
train-base/ (safetensors)
   │  train_qlora.py → outputs/lora-adapter/ (adapter_model.safetensors)
   ▼
merge_lora (peft merge_and_unload) → outputs/merged-fp16/ (~3.4GB)
   ▼
llama.cpp convert_hf_to_gguf.py → outputs/merged-fp16.gguf (F16)
   ▼
llama-quantize Q4_K_M → models/qwen3-1.7b-hengjue-q4_k_m.gguf (~1.1GB)
   ▼
llama-server 加载 → benchmark.py before/after
```

## 5. 为什么不是"全量微调/继续预训练"（诚实边界）

- 3GB 显存 + 16GB 内存无法承载全量微调（1.7B fp16 = 3.4GB 权重 + 梯度 + 优化器状态 > 物理上限）；
- 继续预训练需要千万级 token 与稳定算力，与"窗口期有限/快速验证"冲突；
- LoRA + 协议引擎的分工是刻意的：**权重管"品格"（默认行为倾向），代码管"保证"（100% 强制）**。Jev 式的性能来自专用化训练；衡决的性能来自"专用化训练 + 确定性协议"复合——这是架构对架构的超越，不是蛮力对蛮力。

## 6. 回滚方案（零回归）

任何一步失败：删除 `outputs/` 与 `models/qwen3-1.7b-hengjue*`，保留 base GGUF，系统回到"协议引擎 + base 模型"状态——该状态本身已具备 DQB 协议保证类全项达标能力。
