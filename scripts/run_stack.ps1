# 衡决·Decision Core — 一键启动（推理服务 + 决策引擎）
# 用法：powershell -ExecutionPolicy Bypass -File scripts\run_stack.ps1
# 前置：models/*.gguf 与 runtime\llama-b12000-cpu（或 -cuda）就绪（见 README 状态板）
# 注意：原生 llama-server 的参数一律用 ASCII 相对路径（PS5.1 传中文绝对路径会编码错位），
#       工作目录设为 $ROOT（宽字符 API 继承，相对解析无误）。

$ErrorActionPreference = "Continue"
$ROOT = Split-Path -Parent $PSScriptRoot
$LLAMA = if (Test-Path (Join-Path $ROOT "runtime\llama-b12000-cuda\llama-server.exe")) {
    Join-Path $ROOT "runtime\llama-b12000-cuda"
} elseif (Test-Path (Join-Path $ROOT "runtime\llama-b12000-cpu\llama-server.exe")) {
    Join-Path $ROOT "runtime\llama-b12000-cpu"
} else { $null }
$NGLL = if ($LLAMA -like "*cuda*") { "99" } else { "0" }

function Test-File($p) { Test-Path $p }

Write-Host "== 衡决启动 =="
if (-not $LLAMA) {
    Write-Host "[FAIL] 未找到 llama-server.exe（runtime\llama-b12000-cpu 或 -cuda）——先完成下载"
    exit 1
}
Set-Location $ROOT

# 快路径：Qwen3-1.7B 全量 offload（1.1GB，8k ctx）
# Qwen3 instruct 默认思考模式；--reasoning off 关闭思考（b12000 新语法；旧版用 --chat-template-kwargs）
# 若已训练出 models/qwen3-1.7b-hengjue-q4_k_m.gguf 则优先用它（改造后权重）
$FAST_GGUF = if (Test-File (Join-Path $ROOT "models\qwen3-1.7b-hengjue-q4_k_m.gguf")) {
    "models/qwen3-1.7b-hengjue-q4_k_m.gguf" } else { "models/Qwen3-1.7B-Q4_K_M.gguf" }
Write-Host "[1/3] 启动快路径 llama-server :8081 ($FAST_GGUF, -ngl $NGLL)"
Start-Process -FilePath (Join-Path $LLAMA "llama-server.exe") -WorkingDirectory $ROOT -ArgumentList @(
    "-m", $FAST_GGUF,
    "-ngl", $NGLL, "-c", "8192", "--port", "8081",
    "--reasoning", "off",
    "--grammar-file", "configs/gbnf_decision.gbnf")

Start-Sleep -Seconds 2

# 深路径：Qwen3-4B 部分 offload（3GB 显存约束，-ngl 32，4k ctx）
if (Test-File (Join-Path $ROOT "models\Qwen3-4B-Instruct-2507-Q4_K_M.gguf")) {
    Write-Host "[2/3] 启动深路径 llama-server :8082 (Qwen3-4B Q4_K_M, -ngl 32)"
    Start-Process -FilePath (Join-Path $LLAMA "llama-server.exe") -WorkingDirectory $ROOT -ArgumentList @(
        "-m", "models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
        "-ngl", "32", "-c", "4096", "--port", "8082",
        "--reasoning", "off")
}

Write-Host "[3/3] 启动决策引擎 :8390"
# 注意：PowerShell 中裸 `python` 会命中 WindowsApps 存根（静默无操作），必须用真实解释器
$py = $null
if (Test-Path (Join-Path $ROOT "runtime\venv-train\Scripts\python.exe")) {
    $py = Join-Path $ROOT "runtime\venv-train\Scripts\python.exe"
} else {
    foreach ($cmd in @("python", "python3", "py")) {
        $src = Get-Command $cmd -ErrorAction SilentlyContinue | ForEach-Object { $_.Source } |
               Where-Object { $_ -notlike '*WindowsApps*' } | Select-Object -First 1
        if ($src -and (Test-Path $src)) { $py = $src; break }
    }
}
if (-not $py) {
    throw "找不到可用 Python（WindowsApps 存根不可用）——先运行 scripts\setup_train_env.ps1，或安装 Python 3.10+"
}
Start-Process -FilePath $py -ArgumentList @(
    (Join-Path $ROOT "decision_engine\server.py"),
    (Join-Path $ROOT "configs\decision_protocol.json"), "8390")

Write-Host ""
Write-Host "就绪。测试："
Write-Host "  curl -X POST http://127.0.0.1:8390/decide -H `"Content-Type: application/json`" -d `"{\`"question\`":\`"是否应该先电话核验再处理？\`"}`""
Write-Host "  基准：python scripts\benchmark.py --engine-url http://127.0.0.1:8390"
Write-Host "（模型加载需要 30-90 秒，首次决策前请等待 llama-server 日志出现 'model loaded'）"
