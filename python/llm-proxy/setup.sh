#!/usr/bin/env bash
# setup.sh — Python project setup (requirements.txt)
# Creates .venv with uv and installs dependencies.
set -euo pipefail

echo "🐍 LLM Proxy setup — creating virtual environment..."

if ! command -v uv &>/dev/null; then
    echo "❌ uv not found — install it first: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

if [ ! -d .venv ]; then
    uv venv
    echo "✅ .venv created"
fi

echo "📦 Installing dependencies..."
uv pip install -r requirements.txt

echo "✅ Setup complete — run: .venv/bin/uvicorn main:app --reload"
