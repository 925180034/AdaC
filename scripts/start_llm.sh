#!/usr/bin/env bash
# Start vLLM serving qwen3.5:9b (AWQ 4bit) on A100 #1.
# For development on 4090, point LLM_BASE_URL to a cloud API instead.
set -euo pipefail

export CUDA_VISIBLE_DEVICES=0

MODEL_PATH="${LLM_MODEL_PATH:-/root/models/qwen3.5-9b-awq}"

vllm serve "$MODEL_PATH" \
    --served-model-name qwen3.5:9b \
    --quantization awq \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.35 \
    --guided-decoding-backend outlines \
    --port 8000
