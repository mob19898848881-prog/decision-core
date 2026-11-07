# 衡决 · Decision Core

> 在 GTX 1060 3GB 本机部署的开源**快速决策模型**，按《李紫圣思维与价值体系_致所有AI共识文件_v1.0》改造**架构与权重**，目标快速决策能力**远超 JOV（Jev AI）**。
>
> 唯一内核：**价值度量权必须回归价值创造者本人。**

## 这是什么

一个三件套：

1. **决策协议引擎**（`decision_engine/`，纯标准库）：G0 问题编译 → 路由 → 模型 → G1–G5 六闸门 → ADD-only 哈希链账本。共识文件七条请求全部**代码化强制**，不是提示词倡议。
2. **双路径本地模型**：快路径 Qwen3-1.7B Q4_K_M（对标 Jev 的结构化快速决策）+ 深路径 Qwen3-4B-Instruct-2507 Q4_K_M（复杂决策），均 Apache 2.0。
3. **权重改造管线**（`scripts/train_qlora.py` 等）：66 条种子语料（Step-5 按共识文件直书）→ 云端蒸馏扩到 660 条 → QLoRA 微调（Pascal sm_61 适配）→ 合并量化 → DQB 基准验收。

## 快速开始

```powershell
# 1. 下载（模型走 hf-mirror；llama.cpp 二进制走 GitHub 续传，较慢）
bash scripts/download_stack_v2.sh

# 2. 冒烟测试（不依赖真实模型，模型桩验证协议链路）
python scripts/smoke_test.py

# 3. 起推理服务（llama.cpp 到位后；Qwen3 必须 --reasoning off 否则输出全进思考段）
#    CPU 构建：runtime\llama-b12000-cpu\llama-server.exe -ngl 0
#    CUDA 构建：runtime\llama-b12000-cuda\llama-server.exe -ngl 99
#    ⚠ --grammar-file 是结构合规的代码级保证（输出锁进协议 JSON 骨架），训练版模型必加
runtime\llama-b12000-cuda\llama-server.exe -m models\qwen3-1.7b-hengjue-q4_k_m.gguf -ngl 99 -c 8192 --port 8081 --reasoning off --grammar-file configs/gbnf_decision.gbnf
runtime\llama-b12000-cuda\llama-server.exe -m models\Qwen3-4B-Instruct-2507-Q4_K_M.gguf -ngl 32 -c 4096 --port 8082 --reasoning off
#    或用一键脚本：powershell -File scripts\run_stack.ps1

# 4. 起决策引擎（零依赖；注意用绝对路径 python，勿用 WindowsApps 存根）
python decision_engine/server.py configs/decision_protocol.json 8390

# 5. 决策
curl -X POST http://127.0.0.1:8390/decide -H "Content-Type: application/json" -d "{\"question\":\"是否应该先电话核验再处理？\"}"

# 6. 基准验收
python scripts/benchmark.py --engine-url http://127.0.0.1:8390
```

## 目录

| 路径 | 内容 |
|---|---|
| `docs/01-deep-research-report.md` | 深度研究报告：硬件实测、Jev 解剖、候选对比、选型、DQB 判据 |
| `docs/02-architecture-design.md` | 架构设计：六闸门协议引擎、推理栈、降级协议 |
| `docs/03-weight-tuning-plan.md` | 权重方案：蒸馏数据、QLoRA 配置、合并量化 |
| `docs/04-model-card.md` | 模型卡（HF 发布用：训练方法/基准/用法/已知局限） |
| `decision_engine/` | 协议引擎源码（protocol/gates/router/ledger/engine/server） |
| `configs/decision_protocol.json` | 引擎配置（端点/采样/闸门阈值/账本路径） |
| `configs/env.example` | 蒸馏语料环境变量模板（云端 API 密钥配置样例，只含占位符） |
| `data/seed_corpus.jsonl` | 66 条种子语料（六类各 11，含 6 条缺陷问题） |
| `scripts/` | 下载/训练/蒸馏/基准/合并量化/冒烟测试/引擎重试单测/API 发布 |
| `scripts/setup_gen_env.ps1` | 蒸馏环境变量交互式配置（SecureString 输入不回显，密钥零落盘） |
| `models/` `runtime/` | GGUF 模型与 llama.cpp 二进制（下载产物，不入库） |

## 模型权重与产物（不入库）

本仓库包含**全链路源码、脚本、语料与基准证据**；以下大文件按 GitHub 规范（单文件 100MB 上限）不入库，均可由本仓库脚本再生：

| 产物 | 体积 | 获取方式 |
|---|---|---|
| Qwen3-1.7B / Qwen3-4B GGUF（基座） | 1.2G / 2.4G | `bash scripts/download_stack_v2.sh`（hf-mirror 高速通道） |
| Qwen3-1.7B safetensors（训练基座） | 4.1G | 同上 |
| llama.cpp b12000 二进制 | ~280M | `bash scripts/download_segmented.sh`（6 段并行 + ZIP 校验）或 GitHub Releases |
| **衡决训练版权重** `qwen3-1.7b-hengjue-q4_k_m.gguf` | 1.1G | 管线自产：`setup_train_env.ps1` → `train_qlora.py` → `merge_quantize.ps1`（见 docs/03） |

训练版权重（六闸门对齐后的 QLoRA 微调版）完整复现路径：种子语料 `data/seed_corpus.jsonl`（66 条，已含 falsifiable 增强）→ QLoRA（Pascal sm_61 适配，见 scripts/setup_train_env.ps1）→ 合并 → GGUF 量化。五轮 DQB 基准证据见 `data/dqb_result_*.json` 与 `data/dqb_decisions.jsonl`。

## 语料蒸馏（进阶：使用者自配置）

仓库自带的 66 条种子语料已足够跑通**训练与基准全链路**（v3 基准：accuracy 0.783 / falsifiable 0.864 / 条件合规率 93.4%）。若要冲击更高指标，可用云端大模型把语料蒸馏扩到 660 条——这一步**需要使用者自备云端 API 密钥**（本项目不内置、不分发任何密钥）。

**交互式配置（推荐，密钥零落盘）**：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_gen_env.ps1
# 按提示输入：出题模型 BaseUrl / API Key（SecureString，输入不回显）/ 模型名；
# 证伪审查模型三件套可留空跳过（降级为 schema 单扫，质量打折）。
# 密钥仅设置进当前 PowerShell 会话的 $env:，不写入任何文件，会话结束即失效。
```

**手动配置**：照 `configs/env.example` 模板在会话中设置 `HENGJUE_GEN_*`（必需）与 `HENGJUE_CRITIC_*`（可选，极我互校），任何 OpenAI 兼容端点均可：

```powershell
$env:HENGJUE_GEN_BASE_URL="https://api.deepseek.com/v1"    # 填到 /v1 为止
$env:HENGJUE_GEN_API_KEY="sk-你的密钥"
$env:HENGJUE_GEN_MODEL="deepseek-chat"
python scripts\gen_corpus.py --per-category 100 --out data\corpus_full.jsonl
```

**密钥获取路径**：DeepSeek → platform.deepseek.com → API Keys；Moonshot（Kimi）→ platform.moonshot.cn → API Keys。生成 660 条的总调用量约 170 万 token，成本几元钱量级。脚本纪律：密钥只从环境变量读取、不落盘、不打印；无密钥时 `--dry-run` 输出计划后退出（宁可明示残缺，不可伪装齐备）。

## 当前状态（2026-11-07）

| 项 | 状态 |
|---|---|
| 深度研究与选型 | ✅ 完成（docs/01） |
| 协议引擎代码 + 冒烟测试 | ✅ 7/7 通过（模型桩，scripts/smoke_test.py） |
| 种子语料 66 条 | ✅ 完成 + falsifiable 增强 66/66 覆盖（scripts/enrich_seed_falsifiable.py，50 条合成均标 synthesized+basis） |
| Qwen3-4B GGUF（2.5GB） | ✅ 已下载（字节数与 LFS 标称一致） |
| Qwen3-1.7B GGUF（1.28GB） | ✅ 已下载（GGUF v3 头有效，LFS 字节数核对一致） |
| train-base safetensors（4.06GB） | ✅ 已下载（index.json total_size 核对一致） |
| llama.cpp b12000 CUDA 12.4 | ✅ 已就位（runtime/llama-b12000-cuda/，6 段并行下载，ZIP 校验 53 条目通过） |
| llama.cpp b12000 CPU 构建 | ✅ 已就位（runtime/llama-b12000-cpu/） |
| llama.cpp master 源码（转换器） | ✅ 已就位（runtime/llama.cpp-master/，b12000 转换器不认 Qwen3 BPE 预分词器） |
| 真实模型链路测试 | ✅ 已通过（scripts/real_link_test.py：G0 预设拒绝 0.0s / 真实 JSON 决策 / 闸门逐项生效 / 降级如实标注） |
| 训练环境 | ✅ Pascal 实测门通过：torch 2.14.1+cu126（arch list 含 sm_61）/ transformers 5.22.1 / peft 0.21.2 / bnb 0.50.2；NF4 fp16 在 GTX 1060 3GB 实测 OK |
| LoRA 训练 → 合并 → 量化全链路 | ✅ 已跑通（管线验证跑：loss 3.687→1.975；产出 models/qwen3-1.7b-hengjue-q4_k_m.gguf 1.1GB） |
| G0 缺陷捕获 | ✅ 6/6（预设注入 3/3 + 伪开放/锚定 3/3，0 误伤——CPU 基准归因后发现并修复的模式库缺口） |
| DQB 基准（CPU 基线，base 模型） | ✅ 已测：accuracy 0.45 / premise 0.56 / falsifiable 0.42 / adjudication 0.30 |
| DQB 基准（GPU，训练版 v1） | ✅ 已测：accuracy 0.633 / premise 0.621 / falsifiable 0.136 / adjudication 0.773（LoRA 使 adjudication +47pp；falsifiable 因训练信号稀释倒退，已定位并修复） |
| v2 重训 + 合并量化 | ✅ 完成（loss 3.622→2.054；falsifiable 恒填 66/66；Q4_K_M 1050MiB；v1 版已留档 *-v1* 后缀） |
| DQB 基准（v2，无语法） | ✅ 已测：accuracy 0.367 / premise 0.515 / falsifiable 0.288 / adjudication 0.636 / p50 15.1s（falsifiable +15pp 修复生效；但输出变长致解析失败 9%→23%，准确率被稀释） |
| DQB 基准（v2，GBNF 语法约束） | ✅ 已测：accuracy 0.650 / premise 0.773 / falsifiable 0.788 / adjudication 0.833 / p50 10.4s（**四创全线最好成绩**；OK 率 45/66；解析失败 15→2。语法约束=结构合规的代码级保证：输出锁进协议 JSON 骨架、falsifiable 字段必现、无重试轮次） |
| G2 闸门加固（deadline ≥ 今天） | ✅ 已上线（单测 11/11）：实测模型 52/66 输出过去日期（2025-01-01 式），存在性判定放大虚假达标；已加严格未来日期约束（绝对日期解析比较/相对期限天然未来/M月D日跨年推断）+ 重试反馈带具体截止日 |
| 日期锚定（engine._user_prompt） | ✅ 已上线：模型不会推算日历只会模式匹配预训练日期串——注入当天日期+未来示例（today+14d/today+24d 动态生成）后，12/12 样本输出严格未来 deadline |
| DQB 基准（v2，语法+G2 加固无锚定） | ✅ 已测：accuracy 0.633 / premise 0.636 / **falsifiable 0.015** / adjudication 0.833 / p50 19.9s（诚实口径暴露真实水平：模型无法靠重试反馈自我修正过去日期，falsifiable 崩塌证明这是数据缺口） |
| DQB 基准（终版：语法+锚定+严格G2+550token） | ✅ 已测：accuracy 0.683 / premise 0.788 / **falsifiable 0.803** / adjudication 0.803 / p50 11.9s。**条件合规率（有输出的 57 样本）：G2 53/57=93%，deadline 全为严格未来**。剩余稀释=基础设施失败 9/66（解析 4+socket 5） |
| 引擎传输层重试+采样参数（v3） | ✅ 已上线（scripts/test_engine_retry.py 7/7 + 冒烟 8/8 零回归）：① socket 瞬时错误独立重试预算 + 指数退避 1s/2s/4s（不消耗闸门重试）；② 解析失败重试时 token 上限 1.5x 升级（截断场景）；③ sampling 段接线——repeat_penalty 1.1 / top_p 0.9 抑制复读退化；④ 实测**解析失败 5→0，UNDECIDABLE 9→5** |
| DQB 基准（v3：重试+采样） | ✅ 已测：accuracy **0.783** / premise **0.803** / falsifiable **0.864** / adjudication **0.864** / p50 14.99s（重试退避代价 +3.1s，四项全线新高；残留 5/66 均为 Pascal 长会话周期性僵死，4 次尝试×退避仍未恢复，属本机基础设施极限） |
| 660 条蒸馏语料 + 终训 | ⬜ 进阶项（使用者自配置）：`scripts/setup_gen_env.ps1` 交互引导配置云端 API 密钥（SecureString 零落盘）→ `gen_corpus.py` 蒸馏 → 终训。不配置亦可跑通全链路（种子 66 条） |

## 已知环境坑（2026-11-07 实测，均已在脚本中修复）

1. **PowerShell 中 `python` 可能是 WindowsApps 存根**：商店占位存根静默返回 0 但不做事，
   `python -m venv` 会"成功"但不建目录。所有 .ps1 已改为 PATH 探测（排除存根）+ 存在性校验。
2. **.ps1 必须带 UTF-8 BOM**：无 BOM 的 .ps1 被 PS 5.1 按 GBK 解析，中文注释会错位成语法错误。
3. **PS 5.1 + `$ErrorActionPreference=Stop` + 原生命令 `2>&1`**：pip 的 stderr 会变成
   终止性错误，镜像回退循环被打断。已改为临时 Continue + try/catch + `$LASTEXITCODE` 判定。
4. **llama-server 进程生命周期**：`(cmd &)` 启动的进程随工具调用结束被清理杀掉；
   长驻服务必须用后台任务方式启动。另 `response_format: json_object` 在 b12000 上会击穿
   服务端（已从引擎移除，结构化保证改走系统提示 + GBNF + 引擎校验）。
5. **Qwen3 默认思考模式**：输出全进 `reasoning_content`，`content` 为空——
   llama-server 用 `--reasoning off`（b12000 新语法）。
6. **GitHub 直连 ~30-100KB/s**：模型走 hf-mirror（2.8MB/s）；llama.cpp 二进制若过慢可试
   `https://gh-proxy.com/<原始URL>`（实测 ~100KB/s 可用，支持 Range——`scripts/download_segmented.sh`
   6 段并行约 10 分钟）。**断点续传曾把 zip 下坏（体积超限+testzip 报错）**，大文件优先分段下载。
7. **pip 26.x + 清华 PyPI 镜像解析失败**（"from versions: none"，curl 却 200）——阿里镜像正常。
   依赖安装已改为镜像链：阿里 → 清华 → pypi.org。
8. **PowerShell 5.1 向原生程序传中文绝对路径会编码错位**：llama-quantize 收到
   `D:\Ð¡Ëµ¹¤·»` 式乱码报 No such file。原生 llama 程序（quantize/cli/server）一律用
   ASCII 相对参数 + `$ROOT` 工作目录；Python 调用（宽字符 API）不受限。
9. **transformers 5.x 破坏性变更**：Trainer 的 `tokenizer` 参数改名 `processing_class`；
   `torch_dtype` 弃用改 `dtype`（train_qlora.py 已按签名探测兼容）。
10. **b12000 转换器不认 Qwen3 BPE 预分词器**（NotImplementedError）——GGUF 转换必须用
    master 源码的 convert_hf_to_gguf.py（runtime/llama.cpp-master/）。
11. **llama-cli 一次性验证会挂起**：跑完 -p 进入交互模式等 stdin——喂空输入 `"" | & ...`。
12. **llama-server 与引擎间的瞬时 socket 错误**（10054/502）偶发——引擎已按通道失败
    如实记 UNDECIDABLE + missing，服务本身不崩（日志证实全量请求均完成处理）。
13. **GTX 1060 3GB 实测生成速度 ~22 tok/s**（prompt eval 150-180 tok/s）：短决策 1.1s
    达标，但长输出（150-340 token）+ 闸门重试会把端到端 p50 推到 ~18s——延迟目标需与
    输出长度/重试策略联合优化（见 docs/01 第 5 节判据的修订讨论）。**GBNF 语法约束后
    p50 降至 10.4s**（无重试轮次 + 输出锁进 JSON 骨架），但距 1.5s 目标仍差一个数量级——
    全字段协议 JSON 在本机速度下物理不可及，判据修订需作者裁决。
14. **模型会把 deadline 泛化成过去日期**（2025-01-01/2025-12-31 式，实测 52/66）：
    G2 仅查日期格式存在性会放大虚假达标——已加 `deadline ≥ date.today()` 约束
    （gates._deadline_is_future，单测 9/9）。
15. **后台任务完成通知可能错发**：曾收到"completed (exit 0) / 15m19s"通知，实际进程
    仅运行 1 分钟且最终以 exit 1 正常结束——判定基准结果**只认 TaskOutput 实取输出**，
    通知的 exit code 与 duration 不可轻信（本次因此险些据虚假数字出报告）。
16. **GitHub 主站可能被出口代理封锁**（CONNECT 502 / 直连超时），但 api.github.com 与
    codeload.github.com 可达——git push 的智能 HTTP 协议走 github.com:443 会失败。
    备用通道：`scripts/publish_via_api.py` 经 Git Data API（blob→tree→commit→ref）
    在 api.github.com 上构建等价 commit。另注意 git 全局配置里可能残留失效代理
    （http.proxy 指向已死的 127.0.0.1 端口），推送前先 `git config --global --list | grep proxy` 核对。
17. **llama-server 在 Pascal 上长时间会话会周期性僵死**（10054/502，实测 20 分钟会话
    约 8% 请求命中，4 次尝试 × 1s/2s/4s 退避仍未恢复）——瞬时抖动可被传输层重试吸收，
    持续僵死只能重启服务端缓解。引擎已把传输重试（transport_retry=3）与闸门重试
    （retry_max=1）拆成独立预算，互不消耗。
18. **模型对无背景短问题会复读退化**：整段回显提示词，撞 length 上限后 JSON 收不了尾
    （实测 5/66 解析失败）。两个确定性缓解：请求体带 `repeat_penalty: 1.1`（采样抑制，
    configs 的 sampling 段已接线）+ 解析失败重试时 token 上限 1.5x 升级。修复后解析失败归零。

## 与 Jev 的对标（详见 docs/01 第 5 节）

| 维度 | Jev | 衡决 |
|---|---|---|
| 前提审计 | 无 | G0 代码强制 100% |
| 可证伪输出 | 无 | G2 强制 deadline+metric |
| 不代行裁决 | 无 | G3 强制 proposal_only |
| 偏见傲慢扫描 | 无 | G4 模式库+复审 |
| 透明记录 | 无 | G5 ADD-only 哈希链 |
| 可用性 | 中国大陆 451 封锁 | 本地 100% |
| 延迟 | 0.4s（其云端） | 快路径目标 p50 ≤1.5s（本机零边际成本） |

## 纪律

- 功能必须代码化，提示词只做调用（闸门全是确定性代码）。
- 宁可明示残缺，不可伪装齐备（无推理通道时返回 UNDECIDABLE + missing 声明）。
- 裁决权永远在作者（真我）：引擎只出提案，`adjudication=user` 是代码强制字段。
- 零回归：回滚 = 删除 `outputs/` 与 `models/qwen3-1.7b-hengjue*`，保留 base GGUF。
