#!/usr/bin/env bash
# 衡决·Decision Core 下载脚本（后台执行）
# 内容：llama.cpp b12000 CUDA12.4 Windows 构建 + Qwen3 GGUF(Q4_K_M) + Qwen3-1.7B safetensors
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/runtime/download.log"
mkdir -p "$ROOT/runtime" "$ROOT/models"
exec >> "$LOG" 2>&1
echo "===== download start: $(date -Iseconds) ====="

HF_DIRECT="https://huggingface.co"
HF_MIRROR="https://hf-mirror.com"
pick_hf() {
  if curl -sI --max-time 8 "$HF_DIRECT" >/dev/null 2>&1; then echo "$HF_DIRECT"; else echo "$HF_MIRROR"; fi
}
HF=$(pick_hf)
echo "HF endpoint: $HF"

# ---------- 1. llama.cpp b12000 CUDA 12.4 ----------
cd "$ROOT/runtime"
ZIP="llama-b12000-bin-win-cuda-12.4-x64.zip"
if [ ! -d "llama-b12000" ]; then
  echo "[1/3] downloading llama.cpp b12000 cuda-12.4 ..."
  curl -L --retry 3 --max-time 900 -o "$ZIP" "https://github.com/ggml-org/llama.cpp/releases/download/b12000/$ZIP" && \
  unzip -q -o "$ZIP" && mv llama-b12000-bin-win-cuda-12.4-x64 llama-b12000 2>/dev/null
  echo "[1/3] llama.cpp done: $(ls llama-b12000/*.exe 2>/dev/null | head -5 | tr '\n' ' ')"
else
  echo "[1/3] llama-b12000 already exists, skip"
fi

# ---------- 2. GGUF 模型 ----------
probe_repo() { curl -s --max-time 15 "$HF/api/models/$1" | head -c 200 | grep -q '"id"' && echo yes || echo no; }
dl_gguf() { # repo file dest
  local repo="$1" file="$2" dest="$3"
  echo "  downloading $repo :: $file"
  curl -L --retry 3 --max-time 1800 -o "$dest" "$HF/$repo/resolve/main/$file"
  ls -la "$dest"
}

cd "$ROOT/models"
echo "[2/3] probing GGUF repos ..."
F4B_REPO=""
for r in "ggml-org/Qwen3-4B-Instruct-2507-GGUF" "unsloth/Qwen3-4B-Instruct-2507-GGUF" "bartowski/Qwen3-4B-Instruct-2507-GGUF"; do
  if [ "$(probe_repo "$r")" = "yes" ]; then F4B_REPO="$r"; break; fi
done
echo "  4B repo: ${F4B_REPO:-NONE}"
if [ -n "$F4B_REPO" ]; then
  FILES=$(curl -s --max-time 30 "$HF/api/models/$F4B_REPO" | python -c "
import json,sys
try:
  d=json.load(sys.stdin)
  for s in d.get('siblings',[]):
    n=s['rfilename']
    if n.endswith('.gguf') and 'q4_k_m' in n.lower(): print(n)
except Exception as e: pass")
  F=$(echo "$FILES" | head -1)
  if [ -n "$F" ]; then dl_gguf "$F4B_REPO" "$F" "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"; else echo "  no q4_k_m file found"; fi
fi

F17_REPO=""
for r in "ggml-org/Qwen3-1.7B-GGUF" "unsloth/Qwen3-1.7B-Instruct-GGUF" "unsloth/Qwen3-1.7B-GGUF" "bartowski/Qwen3-1.7B-GGUF"; do
  if [ "$(probe_repo "$r")" = "yes" ]; then F17_REPO="$r"; break; fi
done
echo "  1.7B repo: ${F17_REPO:-NONE}"
if [ -n "$F17_REPO" ]; then
  FILES=$(curl -s --max-time 30 "$HF/api/models/$F17_REPO" | python -c "
import json,sys
try:
  d=json.load(sys.stdin)
  for s in d.get('siblings',[]):
    n=s['rfilename']
    if n.endswith('.gguf') and 'q4_k_m' in n.lower(): print(n)
except Exception as e: pass")
  F=$(echo "$FILES" | head -1)
  if [ -n "$F" ]; then dl_gguf "$F17_REPO" "$F" "Qwen3-1.7B-Q4_K_M.gguf"; else echo "  no q4_k_m file found"; fi
fi

# ---------- 3. 训练用 safetensors ----------
echo "[3/3] probing Qwen3-1.7B instruct safetensors ..."
TRAIN_REPO=""
for r in "Qwen/Qwen3-1.7B-Instruct-2507" "Qwen/Qwen3-1.7B" "Qwen/Qwen2.5-1.5B-Instruct"; do
  if [ "$(probe_repo "$r")" = "yes" ]; then TRAIN_REPO="$r"; break; fi
done
echo "  train base repo: ${TRAIN_REPO:-NONE}"
if [ -n "$TRAIN_REPO" ]; then
  mkdir -p "train-base"
  for f in config.json generation_config.json tokenizer.json tokenizer_config.json merges.txt vocab.json; do
    curl -sL --retry 2 --max-time 120 -o "train-base/$f" "$HF/$TRAIN_REPO/resolve/main/$f"
  done
  SF=$(curl -s --max-time 30 "$HF/api/models/$TRAIN_REPO" | python -c "
import json,sys
try:
  d=json.load(sys.stdin)
  for s in d.get('siblings',[]):
    n=s['rfilename']
    if n.endswith('.safetensors'): print(n)
except Exception: pass" | head -2)
  for f in $SF; do
    echo "  downloading $f"
    curl -L --retry 3 --max-time 2400 -o "train-base/$f" "$HF/$TRAIN_REPO/resolve/main/$f"
  done
  ls -la train-base/
fi
echo "===== download done: $(date -Iseconds) ====="
