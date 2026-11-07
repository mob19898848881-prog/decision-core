# 衡决·Decision Core — 蒸馏语料环境变量交互式配置（密钥零落盘）
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts\setup_gen_env.ps1
#   # 或全参数非交互：
#   powershell -File scripts\setup_gen_env.ps1 -GenBaseUrl "https://api.deepseek.com/v1" -GenApiKey "sk-..." -GenModel "deepseek-chat" -Yes
#
# 安全纪律：密钥经 Read-Host -AsSecureString 输入（不回显），仅设置进当前
# PowerShell 会话的 $env:，不写入任何文件、不进 git、不打印。会话结束即失效。
# 手动设置的模板见 configs\env.example。

param(
    [string]$GenBaseUrl,
    [string]$GenApiKey,
    [string]$GenModel,
    [string]$CriticBaseUrl,
    [string]$CriticApiKey,
    [string]$CriticModel,
    [int]$PerCategory = 100,
    [switch]$DryRunOnly,
    [switch]$Yes
)

$ErrorActionPreference = "Continue"

# ---------- 0. 解析可用的 python（避开 WindowsApps 存根） ----------
function Resolve-Python {
    $candidates = @(
        (Join-Path $PSScriptRoot "..\runtime\venv-train\Scripts\python.exe"),
        (Get-Command python -ErrorAction SilentlyContinue | ForEach-Object { $_.Source } | Where-Object { $_ -notlike '*WindowsApps*' })
    )
    foreach ($c in $candidates) {
        if (-not $c) { continue }
        if (-not (Test-Path $c)) { continue }
        $out = & $c -c "import sys; print('OK')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out -match 'OK') { return $c }
    }
    return $null
}

function Read-Secret([string]$prompt) {
    $secure = Read-Host -Prompt $prompt -AsSecureString
    $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    } finally {
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

$PY = Resolve-Python
if (-not $PY) {
    Write-Host "[FAIL] 找不到可用 Python（WindowsApps 存根不可用）。" -ForegroundColor Red
    Write-Host "       先运行 scripts\setup_train_env.ps1 创建 venv，或安装 Python 3.10+。"
    exit 1
}
Write-Host "[python] $PY"

# ---------- 1. 收集配置 ----------
# 交互策略：裸跑（无任何参数）= 全交互引导，适合下载用户首次使用；
# 带任意参数运行 = 脚本化模式，可选项直接跳过（缺失不询问，保证确定性）。
$Scripted = $PSBoundParameters.Count -gt 0

function Need-Interactive([string]$what) {
    if ($Scripted) {
        Write-Host "[FAIL] 脚本化模式缺少必需参数：$what" -ForegroundColor Red
        Write-Host "       用法：... -GenBaseUrl <url> -GenApiKey <key> -GenModel <model> [-Yes]"
        exit 1
    }
}

if (-not $GenBaseUrl) {
    Need-Interactive "GenBaseUrl"
    $GenBaseUrl = Read-Host "出题模型 BaseUrl（如 https://api.deepseek.com/v1）"
}
if (-not $GenApiKey) {
    Need-Interactive "GenApiKey"
    $GenApiKey = Read-Secret "出题模型 API Key（输入不回显）"
}
if (-not $GenModel) {
    Need-Interactive "GenModel"
    $GenModel = Read-Host "出题模型名（如 deepseek-chat / deepseek-v4-pro）"
}
if (-not $Scripted) {
    if (-not $CriticBaseUrl) { $CriticBaseUrl = Read-Host "证伪审查 BaseUrl（可留空跳过→降级 schema 单扫）" }
    if ($CriticBaseUrl -and -not $CriticApiKey) { $CriticApiKey = Read-Secret "证伪审查 API Key（可留空跳过）" }
    if ($CriticBaseUrl -and -not $CriticModel)  { $CriticModel = Read-Host "证伪审查模型名（如 kimi-k3 / moonshot-v1-128k）" }
}

if (-not $GenBaseUrl -or -not $GenApiKey -or -not $GenModel) {
    Write-Host "[FAIL] 出题模型三件套（BaseUrl/API Key/Model）为必需项。" -ForegroundColor Red
    exit 1
}

# ---------- 2. 设置进当前会话环境变量（零落盘） ----------
$env:HENGJUE_GEN_BASE_URL = $GenBaseUrl
$env:HENGJUE_GEN_API_KEY  = $GenApiKey
$env:HENGJUE_GEN_MODEL    = $GenModel
if ($CriticBaseUrl -and $CriticApiKey -and $CriticModel) {
    $env:HENGJUE_CRITIC_BASE_URL = $CriticBaseUrl
    $env:HENGJUE_CRITIC_API_KEY  = $CriticApiKey
    $env:HENGJUE_CRITIC_MODEL    = $CriticModel
    Write-Host "[env] 出题 + 证伪审查双通道已设置（互校模式）"
} else {
    Write-Host "[env] 出题通道已设置；证伪审查未配置 → 将降级为 schema 单扫"
}
Write-Host "[env] 密钥仅存在于本会话内存，未写入任何文件。"

# ---------- 3. dry-run 验证 ----------
$ROOT = Split-Path -Parent $PSScriptRoot
Push-Location $ROOT
& $PY "scripts\gen_corpus.py" --dry-run
Pop-Location
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($DryRunOnly) { Write-Host "[done] dry-run 完成"; exit 0 }

# ---------- 4. 正式生成 ----------
if (-not $Yes -and -not $DryRunOnly) {
    if ($Scripted) {
        Write-Host "[FAIL] 脚本化模式需显式 -Yes 才会正式生成（防止误跑云端计费）。" -ForegroundColor Red
        exit 1
    }
    $ans = Read-Host "开始生成？每类 $PerCategory 条，总计约 $(660 + $PerCategory * 6) 条 [y/N]"
    if ($ans -notmatch '^[yY]') { Write-Host "[abort] 已取消"; exit 0 }
}
Write-Host "[run] gen_corpus.py --per-category $PerCategory"
Push-Location $ROOT
& $PY "scripts\gen_corpus.py" --per-category $PerCategory --out "data\corpus_full.jsonl"
$code = $LASTEXITCODE
Pop-Location
exit $code
