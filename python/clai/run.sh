#!/usr/bin/env bash
# run.sh — Run Clai CLI
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

# Setup if needed
if [ ! -d .venv ]; then
    bash setup.sh
fi

echo "🐍 Running clai..."
exec "$DIR/.venv/bin/clai" "$@"
