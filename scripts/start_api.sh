#!/usr/bin/env bash
# Start the FastAPI service — single worker is MANDATORY (see CLAUDE.md §3).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"
exec uvicorn adacascade.api.app:app \
    --host "${APP_HOST:-0.0.0.0}" \
    --port "${APP_PORT:-8080}" \
    --workers 1
