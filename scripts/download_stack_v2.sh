#!/usr/bin/env bash
# 衡决·Decision Core 下载脚本 v2（模型走 hf-mirror 高速通道；llama.cpp 走 GitHub 续传）
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/runtime/download.log"
mkdir -p "$ROOT/runtime" "$ROOT/models/train-base"
exec >> "$LOG" 2>&1
echo "===== download v2 start: $(date -Iseconds) ====="
HF="https://hf-mirror.com"

# ---------- 1. 模型（hf-mirror 高速） ----------
cd "$ROOT/models"
echo "[1/3] Qwen3-1.7B Q4_K_M (instruct, 快路径) ..."
curl -L --retry 3 --max-time 3600 -C - -o "Qwen3-1.7B-Q4_K_M.gguf" \
  "$HF/ggml-org/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf"
ls -la "Qwen3-1.7B-Q4_K_M.gguf"

echo "[2/3] Qwen3-4B-Instruct-2507 Q4_K_M (深路径) ..."
curl -L --retry 3 --max-time 3600 -C - -o "Qwen3-4B-Instruct-2507-Q4_K_M.gguf" \
  "$HF/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/main/Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
ls -la "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"

echo "[3/3] Qwen3-1.7B safetensors (LoRA 训练基座) ..."
cd "$ROOT/models/train-base"
for f in config.json generation_config.json tokenizer.json tokenizer_config.json merges.txt vocab.json model.safetensors.index.json; do
  curl -sL --retry 2 --max-time 120 -o "$f" "$HF/Qwen/Qwen3-1.7B/resolve/main/$f"
done
for f in model-00001-of-00002.safetensors model-00002-of-00002.safetensors; do
  curl -L --retry 3 --max-time 3600 -C - -o "$f" "$HF/Qwen/Qwen3-1.7B/resolve/main/$f"
done
ls -la

# ---------- 4. llama.cpp b12000 CUDA 12.4（GitHub 慢速续传，后台挂着） ----------
cd "$ROOT/runtime"
ZIP="llama-b12000-bin-win-cuda-12.4-x64.zip"
if [ ! -d "llama-b12000" ]; then
  echo "[4/4] llama.cpp b12000 cuda-12.4 (resume) ..."
  curl -L --retry 5 --retry-all-errors --max-time 10800 -C - -o "$ZIP" \
    "https://github.com/ggml-org/llama.cpp/releases/download/b12000/$ZIP"
  if unzip -q -o "$ZIP" 2>/dev/null; then
    mv llama-b12000-bin-win-cuda-12.4-x64 llama-b12000 2>/dev/null
    echo "[4/4] llama.cpp OK: $(ls llama-b12000/ | head -5 | tr '\n' ' ')"
  else
    echo "[4/4] llama.cpp 下载不完整或解压失败（可重跑本脚本续传）"
  fi
else
  echo "[4/4] llama-b12000 exists, skip"
fi
echo "===== download v2 done: $(date -Iseconds) ====="
