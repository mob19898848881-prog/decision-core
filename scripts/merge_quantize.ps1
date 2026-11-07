# 衡决·Decision Core — LoRA 合并 + GGUF 量化 + 加载验证
# 前置：scripts/train_qlora.py 已产出 outputs/lora-adapter；runtime/llama-b12000-cpu 已就位；
#       convert_hf_to_gguf.py 用 runtime/llama.cpp-master/（b12000 的转换器不认 Qwen3 BPE
#       预分词器哈希，报 NotImplementedError——master 已修复）
# 运行：powershell -ExecutionPolicy Bypass -File scripts\merge_quantize.ps1
# 注意：全部步骤均为 CPU 操作，无需等 CUDA 构建。

# 同 setup_train_env.ps1：不用 Stop 偏好（PS5.1 会把原生命令 stderr 变终止性错误），
# 成败靠 $LASTEXITCODE 与 Test-Path 显式判定。
$ErrorActionPreference = "Continue"
$ROOT = Split-Path -Parent $PSScriptRoot
$VENV_PY = Join-Path $ROOT "runtime\venv-train\Scripts\python.exe"
# 合并/转换/量化都是 CPU 活：优先 CPU 构建，其次 CUDA 构建
$LLAMA = if (Test-Path (Join-Path $ROOT "runtime\llama-b12000-cpu\llama-quantize.exe")) {
    Join-Path $ROOT "runtime\llama-b12000-cpu"
} elseif (Test-Path (Join-Path $ROOT "runtime\llama-b12000-cuda\llama-quantize.exe")) {
    Join-Path $ROOT "runtime\llama-b12000-cuda"
} else { $null }
$CONVERT_PY = Join-Path $ROOT "runtime\llama.cpp-master\convert_hf_to_gguf.py"
$MERGED = Join-Path $ROOT "outputs\merged-fp16"
$GGUF_F16 = Join-Path $ROOT "outputs\merged-fp16.gguf"
$GGUF_Q4 = Join-Path $ROOT "models\qwen3-1.7b-hengjue-q4_k_m.gguf"

if (-not (Test-Path (Join-Path $ROOT "outputs\lora-adapter\adapter_model.safetensors"))) {
    Write-Host "[FAIL] 未找到 outputs/lora-adapter/adapter_model.safetensors——先跑 train_qlora.py"
    exit 1
}
if (-not $LLAMA) {
    Write-Host "[FAIL] 未找到 llama-quantize.exe（runtime\llama-b12000-cpu 或 -cuda）——先跑 scripts/download_segmented.sh"
    exit 1
}
if (-not (Test-Path $CONVERT_PY)) {
    Write-Host "[FAIL] 未找到 $CONVERT_PY——下载 master 源码（转换器）："
    Write-Host "  curl -L -o runtime/llama-master-src.tar.gz https://gh-proxy.com/https://github.com/ggml-org/llama.cpp/archive/refs/heads/master.tar.gz"
    Write-Host "  tar -xzf runtime/llama-master-src.tar.gz -C runtime"
    exit 1
}
if (-not (Test-Path $VENV_PY)) {
    Write-Host "[FAIL] 未找到 runtime/venv-train——先跑 setup_train_env.ps1"
    exit 1
}

Write-Host "[1/4] 合并 LoRA 到基座（fp16，含 tokenizer）"
& $VENV_PY -c @"
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
import inspect, torch, os
kw = 'dtype' if 'dtype' in inspect.signature(AutoModelForCausalLM.from_pretrained).parameters else 'torch_dtype'
base = AutoModelForCausalLM.from_pretrained(r'$ROOT\models\train-base', **{kw: torch.float16})
tok = AutoTokenizer.from_pretrained(r'$ROOT\models\train-base')
m = PeftModel.from_pretrained(base, r'$ROOT\outputs\lora-adapter')
m = m.merge_and_unload()
os.makedirs(r'$MERGED', exist_ok=True)
m.save_pretrained(r'$MERGED', safe_serialization=True)
tok.save_pretrained(r'$MERGED')  # 转换器需要 tokenizer 三件套，勿漏
print('merged ->', r'$MERGED')
"@
if ($LASTEXITCODE -ne 0) { Write-Host "[FAIL] 合并失败"; exit 1 }

Write-Host "[2/4] 转换为 GGUF F16（Python 转换器，宽字符路径无碍）"
& $VENV_PY $CONVERT_PY $MERGED --outfile $GGUF_F16 --outtype f16
if ($LASTEXITCODE -ne 0) { Write-Host "[FAIL] 转换失败"; exit 1 }

# 关键：PowerShell 5.1 向原生程序传含中文的绝对路径会编码错位（llama-quantize 收到乱码路径
# 报 No such file）。原生 llama 程序一律用 ASCII 相对参数；$ROOT 已由 .NET 宽字符 API 正确
# 设置为进程工作目录，相对解析无误。Python 调用不受此限。
Push-Location $ROOT
try {
    Write-Host "[3/4] 量化为 Q4_K_M（相对路径）"
    & (Join-Path $LLAMA "llama-quantize.exe") "outputs/merged-fp16.gguf" "models/qwen3-1.7b-hengjue-q4_k_m.gguf" "Q4_K_M" 2>&1 | Select-Object -Last 4
    if ($LASTEXITCODE -ne 0) { Write-Host "[FAIL] 量化失败"; exit 1 }

    Write-Host "[4/4] 加载验证（CPU 跑 1 个短提示，确认模型可用）"
    # 注意：llama-cli 跑完 -p 会进入交互模式等 stdin 挂起——喂空输入使其一次性退出
    "" | & (Join-Path $LLAMA "llama-cli.exe") -m "models/qwen3-1.7b-hengjue-q4_k_m.gguf" -p "决策：要不要先做读者调研？请用一句话回答。" -n 48 -ngl 0 --no-warmup 2>&1 | Select-Object -Last 6
    if ($LASTEXITCODE -ne 0) { Write-Host "[FAIL] 加载验证失败"; exit 1 }
} finally {
    Pop-Location
}
Write-Host "[done] $GGUF_Q4"
Write-Host "[next] 用本 GGUF 起 llama-server（端口 8081），更新 configs/decision_protocol.json 的 fast 端点，再跑 benchmark.py"
