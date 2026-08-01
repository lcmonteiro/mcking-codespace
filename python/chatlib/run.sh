#!/usr/bin/env bash
# run.sh — Run the chatlib demo app
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

# Setup if needed
if [ ! -d .venv ]; then
    bash setup.sh
fi

exec "$DIR/.venv/bin/python" "$DIR/demo.py" "$@"
