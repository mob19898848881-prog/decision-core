#!/usr/bin/env bash
# 分段并行下载 llama.cpp CUDA 构建（gh-proxy 支持 Range）
# 单连接 ~100KB/s → 6 段并行；完成后拼接并做 zip 完整性校验。
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RT="$ROOT/runtime"
BASE="https://gh-proxy.com/https://github.com/ggml-org/llama.cpp/releases/download/b12000"
NAME="llama-b12000-bin-win-cuda-12.4-x64.zip"
TOTAL=279912456
SEGS=6
CHUNK=$(( (TOTAL + SEGS - 1) / SEGS ))

echo "[seg] total=$TOTAL segs=$SEGS chunk=$CHUNK start=$(date -u +%H:%M:%S)"
pids=()
for i in $(seq 0 $((SEGS - 1))); do
    start=$((i * CHUNK))
    end=$((start + CHUNK - 1))
    if [ "$end" -ge "$TOTAL" ]; then end=$((TOTAL - 1)); fi
    if [ "$start" -ge "$TOTAL" ]; then break; fi
    part="$RT/${NAME}.part${i}"
    curl -sL --retry 5 --retry-all-errors --retry-delay 3 --max-time 3600 \
         -r "${start}-${end}" -o "$part" "$BASE/$NAME" &
    pids+=($!)
    echo "[seg] launched part$i range=${start}-${end}"
done

fail=0
for p in "${pids[@]}"; do wait "$p" || fail=1; done
if [ "$fail" -ne 0 ]; then echo "[seg] FAIL: 有分段下载失败"; exit 1; fi

# 拼接（按段序）
cat "$RT/${NAME}.part"* > "$RT/$NAME"
echo "[seg] concatenated, verifying zip integrity..."
python - "$RT/$NAME" <<'PYEOF'
import sys, zipfile
p = sys.argv[1]
try:
    z = zipfile.ZipFile(p)
    bad = z.testzip()
    n = len(z.namelist())
    if bad:
        print(f"[seg] ZIP CORRUPT first_bad={bad}"); sys.exit(1)
    print(f"[seg] ZIP OK entries={n}")
except Exception as e:
    print(f"[seg] ZIP CORRUPT: {type(e).__name__}: {e}"); sys.exit(1)
PYEOF
rc=$?
if [ "$rc" -eq 0 ]; then
    rm -f "$RT/${NAME}.part"* 2>/dev/null || true
    mkdir -p "$RT/llama-b12000-cuda"
    unzip -q -o "$RT/$NAME" -d "$RT/llama-b12000-cuda"
    echo "[seg] DONE: extracted to runtime/llama-b12000-cuda/"
else
    echo "[seg] 校验失败，保留分段文件供排查"
    exit 1
fi
