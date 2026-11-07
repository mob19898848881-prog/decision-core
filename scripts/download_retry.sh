#!/usr/bin/env bash
# 健壮续传：循环重试直到文件完整（GitHub 通道 502 抖动环境专用）
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/runtime/dl_retry.log"
cd "$ROOT/runtime"
exec >> "$LOG" 2>&1
echo "===== retry-loop start: $(date -Iseconds) ====="

dl() { # url outfile
  local url="$1" out="$2" round=0
  while [ $round -lt 40 ]; do
    round=$((round+1))
    curl -L --connect-timeout 20 --max-time 600 -C - -o "$out" "$url" 2>>"$LOG"
    rc=$?
    # 完整性：zip 以 PK\x05\x06 中央目录结尾（后 22 字节内可含注释）
    if [ -f "$out" ] && python -c "
import sys
d=open('$out','rb').read()
sys.exit(0 if d.rfind(b'PK\x05\x06') >= max(0, len(d)-66000) else 1)
" 2>/dev/null; then
      echo "[OK] $out round=$round size=$(stat -c%s "$out")"
      return 0
    fi
    echo "[retry] $out round=$round rc=$rc size=$(stat -c%s "$out" 2>/dev/null || echo 0)"
    sleep 3
  done
  echo "[GIVEUP] $out after 40 rounds"
  return 1
}

dl "https://github.com/ggml-org/llama.cpp/releases/download/b12000/llama-b12000-bin-win-cpu-x64.zip" "llama-b12000-bin-win-cpu-x64.zip"
if [ ! -d "llama-b12000-cpu" ]; then
  unzip -q -o "llama-b12000-bin-win-cpu-x64.zip" && mv llama-b12000-bin-win-cpu-x64 llama-b12000-cpu
fi
dl "https://github.com/ggml-org/llama.cpp/releases/download/b12000/llama-b12000-bin-win-cuda-12.4-x64.zip" "llama-b12000-bin-win-cuda-12.4-x64.zip"
if [ ! -d "llama-b12000" ]; then
  unzip -q -o "llama-b12000-bin-win-cuda-12.4-x64.zip" && mv llama-b12000-bin-win-cuda-12.4-x64 llama-b12000
fi
echo "===== retry-loop done: $(date -Iseconds) ====="
