#!/usr/bin/env bash
# run.sh — Chat Codec (Node + WASM)
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

# Setup if needed
if [ ! -d node_modules ]; then
    bash setup.sh
fi

echo "💬 Starting Chat Codec dev server..."
exec npm run dev
