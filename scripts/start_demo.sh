#!/usr/bin/env bash
# Start the stable local browser demo path.
#
# The frontend must call the API through Vite's same-origin proxy. Leaving
# VITE_API_BASE_URL empty makes browser requests relative to the Vite origin,
# avoiding localhost:5173 -> localhost:8080/6008 CORS issues.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

cleanup() {
    if [[ -n "${API_PID:-}" ]] && kill -0 "$API_PID" 2>/dev/null; then
        kill "$API_PID" 2>/dev/null || true
        wait "$API_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

printf 'Starting AdaCascade API on http://localhost:6008 (single worker)...\n'
APP_PORT=6008 NO_PROXY=localhost,127.0.0.1 bash scripts/start_api.sh &
API_PID=$!

printf 'Starting Vite demo with same-origin API proxy...\n'
printf 'Open http://localhost:5173, or the next Vite port if 5173 is occupied.\n'
VITE_API_BASE_URL= npm --prefix frontend run dev -- --host 0.0.0.0
