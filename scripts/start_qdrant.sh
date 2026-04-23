#!/usr/bin/env bash
# Start Qdrant binary with persistent storage (no Docker required).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PROJECT_DIR/data/qdrant"

mkdir -p "$DATA_DIR"

# Check if already running (bypass proxy for localhost)
if curl --noproxy '*' -sf http://localhost:6333/healthz >/dev/null 2>&1; then
    echo "[start_qdrant] Qdrant is already running."
    exit 0
fi

echo "[start_qdrant] Starting Qdrant binary..."
QDRANT__STORAGE__STORAGE_PATH="$DATA_DIR" \
QDRANT__SERVICE__HTTP_PORT=6333 \
QDRANT__SERVICE__GRPC_PORT=6334 \
nohup qdrant >"$PROJECT_DIR/data/qdrant.log" 2>&1 &

echo "[start_qdrant] Waiting for Qdrant to be ready..."
for i in $(seq 1 30); do
    if curl --noproxy '*' -sf http://localhost:6333/healthz >/dev/null 2>&1; then
        echo "[start_qdrant] Qdrant is ready."
        exit 0
    fi
    sleep 1
done

echo "[start_qdrant] ERROR: Qdrant did not become ready in 30s." >&2
exit 1
