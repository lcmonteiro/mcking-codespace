#!/usr/bin/env bash
# run.sh — Run LLM Proxy (FastAPI via uvicorn)
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

# Setup if needed
if [ ! -d .venv ]; then
    bash setup.sh
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

echo "🌐 Starting LLM Proxy on http://$HOST:$PORT"
exec "$DIR/.venv/bin/uvicorn" main:app --host "$HOST" --port "$PORT" --reload
