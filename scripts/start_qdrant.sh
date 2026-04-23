#!/usr/bin/env bash
# Start Qdrant as a background docker container with persistent storage.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PROJECT_DIR/data/qdrant"

mkdir -p "$DATA_DIR"

if docker ps -a --format '{{.Names}}' | grep -q '^adac-qdrant$'; then
    echo "[start_qdrant] Container adac-qdrant already exists. Starting..."
    docker start adac-qdrant
else
    echo "[start_qdrant] Creating and starting adac-qdrant..."
    docker run -d --name adac-qdrant \
        -p 6333:6333 -p 6334:6334 \
        -v "$DATA_DIR:/qdrant/storage" \
        qdrant/qdrant:latest
fi

echo "[start_qdrant] Waiting for Qdrant to be ready..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:6333/healthz >/dev/null 2>&1; then
        echo "[start_qdrant] Qdrant is ready."
        exit 0
    fi
    sleep 1
done

echo "[start_qdrant] ERROR: Qdrant did not become ready in 30s." >&2
exit 1
