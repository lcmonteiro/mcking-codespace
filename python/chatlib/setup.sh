#!/usr/bin/env bash
# setup.sh — chatlib package setup (pyproject.toml)
# Creates .venv and installs dependencies with uv.
set -euo pipefail

echo "🐍 chatlib setup — creating virtual environment..."

if ! command -v uv &>/dev/null; then
    echo "❌ uv not found — install it first: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

if [ ! -d .venv ]; then
    uv venv
    echo "✅ .venv created"
fi

echo "📦 Installing dependencies..."
uv sync
echo "✅ Setup complete — run: .venv/bin/python demo.py"
