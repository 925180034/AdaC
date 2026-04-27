#!/usr/bin/env bash
# Start vLLM serving qwen3.5:9b (AWQ 4bit) on cuda:0.
set -euo pipefail

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export HF_HOME="${HF_HOME:-/root/autodl-tmp/huggingface}"
export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-$HF_HOME/hub}"
export TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-$HF_HOME/transformers}"
export TORCH_HOME="${TORCH_HOME:-/root/autodl-tmp/torch}"

MODEL_PATH="${LLM_MODEL_PATH:-/root/autodl-tmp/models/qwen3.5-9b-awq}"
GPU_MEMORY_UTILIZATION="${VLLM_GPU_MEMORY_UTILIZATION:-0.35}"
MAX_MODEL_LEN="${VLLM_MAX_MODEL_LEN:-8192}"
GUIDED_DECODING_BACKEND="${VLLM_GUIDED_DECODING_BACKEND:-xgrammar}"

vllm serve "$MODEL_PATH" \
    --served-model-name qwen3.5:9b \
    --quantization awq \
    --max-model-len "$MAX_MODEL_LEN" \
    --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
    --guided-decoding-backend "$GUIDED_DECODING_BACKEND" \
    --port 8000
