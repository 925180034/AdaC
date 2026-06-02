#!/usr/bin/env bash
# Start vLLM serving qwen3.5:9b on cuda:0.
set -euo pipefail

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export HF_HOME="${HF_HOME:-/app/data/hf_cache}"
export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-$HF_HOME/hub}"
export TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-$HF_HOME/transformers}"
export TORCH_HOME="${TORCH_HOME:-/app/data/torch_cache}"

MODEL_PATH="${LLM_MODEL_PATH:-/app/models/Qwen/Qwen3.5-9B}"
PORT="${LLM_LOCAL_PORT:-8001}"
GPU_MEMORY_UTILIZATION="${VLLM_GPU_MEMORY_UTILIZATION:-0.55}"
MAX_MODEL_LEN="${VLLM_MAX_MODEL_LEN:-4096}"
GUIDED_DECODING_BACKEND="${VLLM_GUIDED_DECODING_BACKEND:-xgrammar}"

exec vllm serve "$MODEL_PATH" \
    --served-model-name qwen3.5:9b \
    ${VLLM_QUANTIZATION:+--quantization "$VLLM_QUANTIZATION"} \
    --max-model-len "$MAX_MODEL_LEN" \
    --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
    --guided-decoding-backend "$GUIDED_DECODING_BACKEND" \
    --port "$PORT"
