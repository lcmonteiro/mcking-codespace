#!/usr/bin/env bash
# setup.sh — Python demos setup
# Creates a .venv using uv and installs the shared dependencies for the one-shot demos.
# Idempotent: safe to run multiple times.
set -euo pipefail

# Location-independent: run from this script's own directory
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v uv &>/dev/null; then
    echo "❌ uv not found. Please install uv (https://github.com/astral-sh/uv) or ensure it's in PATH."
    exit 1
fi

if [ ! -d .venv ]; then
    echo "🐍 Creating .venv with uv..."
    uv venv
fi

echo "📦 Installing dependencies..."
uv pip install -r requirements.txt

echo "✅ Python demos ready — run with: ./run.sh <demo.py>  (or from root: ./run.sh python/<demo.py>)"