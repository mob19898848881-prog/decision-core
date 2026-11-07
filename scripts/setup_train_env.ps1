# 衡决·Decision Core — 训练环境安装与 Pascal 实测门
# 在 PowerShell 中运行：powershell -ExecutionPolicy Bypass -File scripts\setup_train_env.ps1
# 原则：宁可明示残缺，不可伪装齐备——每一步都有显式 PASS/FAIL，失败给出回退路径。
# 注意：不用 $ErrorActionPreference="Stop"——PS5.1 会把原生命令（pip/python）写进 stderr 的
# 任何内容（如 torch 的 numpy UserWarning）经 2>&1 合并后变成终止性错误。成败一律靠
# $LASTEXITCODE 与 Test-Path 显式判定，比依赖 Stop 偏好更可靠。
$ErrorActionPreference = "Continue"
$ROOT = Split-Path -Parent $PSScriptRoot
$VENV = Join-Path $ROOT "runtime\venv-train"

# ---------- 0. 解析可用的 python（避开 WindowsApps 存根） ----------
# Windows 上 PowerShell 的 `python` 可能解析到 Microsoft\WindowsApps\python.exe（商店占位存根，
# 静默返回 0 但不做事）。依次探测 PATH 中的 py/python/python3（排除存根）+ 常见安装位置，
# 并用 `-c` 可执行验证，返回第一个真实解释器。
function Resolve-BasePython {
    $candidates = @()
    foreach ($cmd in @("py", "python", "python3")) {
        $src = Get-Command $cmd -ErrorAction SilentlyContinue | ForEach-Object { $_.Source } |
               Where-Object { $_ -notlike '*WindowsApps*' }
        foreach ($s in $src) { $candidates += $s }
    }
    $candidates += (Get-ChildItem -Path "$env:LOCALAPPDATA\Programs\Python\Python*\python.exe" -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
    $candidates += (Get-ChildItem -Path "C:\Python*\python.exe" -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
    foreach ($c in $candidates) {
        if (-not $c) { continue }
        if (-not (Test-Path $c)) { continue }
        $out = & $c -c "import sys; print('OK')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out -match 'OK') { return $c }
    }
    return $null
}
$BASE_PY = Resolve-BasePython
if (-not $BASE_PY) { Write-Host "[FAIL] 找不到可用的 Python 解释器（WindowsApps 存根不算）"; exit 1 }
Write-Host "== 衡决训练环境安装（GTX 1060 3GB / Pascal sm_61 / Win64）=="
Write-Host "  解释器: $BASE_PY"

# ---------- 0b. venv ----------
if (-not (Test-Path $VENV)) {
    Write-Host "[0/4] 创建虚拟环境 $VENV"
    & $BASE_PY -m venv $VENV
    if (-not (Test-Path (Join-Path $VENV "Scripts\python.exe"))) {
        Write-Host "[FAIL] venv 创建失败（Scripts\python.exe 不存在）——上面应有真实报错"; exit 1
    }
} else {
    Write-Host "[0/4] 虚拟环境已存在，跳过创建"
}
$PY = Join-Path $VENV "Scripts\python.exe"
& $PY -m pip install -U pip -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn | Out-Null

# ---------- 1. 安装依赖（torch CUDA 12.x 系：Pascal 需要；CUDA 13 已弃 Pascal） ----------
Write-Host "[1/4] 安装 torch/transformers/peft/bitsandbytes（可能耗时数分钟）"
# 镜像顺序：NJU → download.pytorch.org（均已核实有 cp313 wheel；SJTU 无 cp313 故不列）
$MIRRORS = @(
    "https://mirrors.nju.edu.cn/pytorch/whl/cu126",
    "https://download.pytorch.org/whl/cu126"
)
$torchOK = $false
foreach ($m in $MIRRORS) {
    Write-Host "  trying torch index: $m"
    # 注意：PS5.1 下原生命令 stderr 经 2>&1 合并会在 Stop 偏好下变成终止性错误，
    # 此处显式容错：临时 Continue + try/catch，靠 $LASTEXITCODE 判定成败。
    $prevPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $PY -m pip install torch --index-url $m 2>&1 | Select-Object -Last 2
    } catch {
        Write-Host "  [warn] 安装器报错（继续尝试下一个镜像）: $($_.Exception.Message)"
    }
    $ErrorActionPreference = $prevPref
    & $PY -c "import torch; print('torch', torch.__version__)" 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { $torchOK = $true; break }
    Write-Host "  -> 该镜像不可用，尝试下一个"
}
if (-not $torchOK) { Write-Host "[FAIL] torch CUDA 安装失败——检查镜像可达性"; exit 1 }
# PyPI 镜像链：阿里优先（pip 26.x 实测清华索引解析失败"from versions: none"，阿里正常）
$PYPI_MIRRORS = @(
    "https://mirrors.aliyun.com/pypi/simple",
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://pypi.org/simple"
)
$depsOK = $false
foreach ($m in $PYPI_MIRRORS) {
    Write-Host "  trying pypi index: $m"
    $prevPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $PY -m pip install transformers peft accelerate datasets gguf sentencepiece --index-url $m 2>&1 | Select-Object -Last 1
        & $PY -m pip install bitsandbytes --index-url $m 2>&1 | Select-Object -Last 1
    } catch {
        Write-Host "  [warn] 安装器报错（尝试下一个镜像）: $($_.Exception.Message)"
    }
    $ErrorActionPreference = $prevPref
    $depCheck = & $PY -c "import torch, transformers, peft, bitsandbytes; print('deps OK', torch.__version__)" 2>&1
    if ($LASTEXITCODE -eq 0) { $depsOK = $true; Write-Host "  依赖校验: $depCheck"; break }
    Write-Host "  -> 该镜像不可用，尝试下一个"
}
if (-not $depsOK) {
    Write-Host "[FAIL] 依赖校验失败（最后错误）: $depCheck"
    Write-Host "  可尝试锁定旧版组合: pip install transformers==4.57.1 peft==0.17.0"
    exit 1
}

# ---------- 2. Pascal 实测门 ----------
Write-Host "[2/4] Pascal 实测门（CUDA 能力 + NF4 fp16 量化）"
$GATE = @'
import sys, torch
ok = True
msgs = []
if not torch.cuda.is_available():
    msgs.append("CUDA 不可用（驱动/运行时问题）"); ok = False
else:
    cap = torch.cuda.get_device_capability()
    msgs.append(f"device={torch.cuda.get_device_name()} sm_{cap[0]}{cap[1]}")
    if cap[0] < 6:
        msgs.append("低于 Pascal，不受支持"); ok = False
    try:
        from bitsandbytes.nn import Linear4bit
        layer = Linear4bit(128, 128, bias=False, compute_dtype=torch.float16).cuda()
        y = layer(torch.randn(1, 4, 128, dtype=torch.float16, device="cuda"))
        assert y.shape == (1, 4, 128)
        msgs.append("NF4 fp16 OK")
    except Exception as e:
        msgs.append(f"NF4 FAIL: {type(e).__name__}: {e}"); ok = False
print("GATE_" + ("PASS" if ok else "FAIL") + " | " + " ; ".join(msgs))
sys.exit(0 if ok else 3)
'@
$GATE | Out-File -FilePath (Join-Path $ROOT "runtime\_pascal_gate.py") -Encoding utf8
& $PY (Join-Path $ROOT "runtime\_pascal_gate.py")
$gateCode = $LASTEXITCODE

# ---------- 3. 结论与回退指引 ----------
Write-Host "[3/4] 结论"
if ($gateCode -eq 0) {
    Write-Host "[PASS] GPU QLoRA 路径可用。下一步："
    Write-Host "  & '$PY' scripts\train_qlora.py --dry-run"
    Write-Host "  & '$PY' scripts\train_qlora.py"
} else {
    Write-Host "[FAIL] GPU QLoRA 不可用（见上）。按降级协议启用 CPU 回退路径："
    Write-Host "  & '$PY' scripts\train_qlora.py --device cpu --seq 256 --epochs 2"
    Write-Host "  （CPU 训练 660 条约 6-12 小时；协议引擎本身不依赖训练即可工作）"
}
Write-Host "[4/4] 完成"
