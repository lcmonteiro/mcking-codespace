#!/usr/bin/env bash
# setup.sh — chatlib package setup (pyproject.toml)
# Creates .venv and installs dependencies with uv (se disponível).
# Se o .venv já está pronto, faz skip — não exige uv no PATH.
set -euo pipefail

echo "🐍 chatlib setup — preparing virtual environment..."

# Já está pronto? Skip (não exige uv).
if [ -x .venv/bin/python ] && .venv/bin/python -c "import textual" 2>/dev/null; then
    echo "✅ .venv already ready — skipping"
    exit 0
fi

# Localizar uv: PATH ou localizações comuns (~/.local/bin, ~/.cargo/bin, /usr/local/bin).
UV=""
for cand in "$(command -v uv 2>/dev/null || true)" "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" "/usr/local/bin/uv"; do
    if [ -x "$cand" ]; then
        UV="$cand"
        break
    fi
done

if [ -z "$UV" ]; then
    echo "❌ uv not found — install it first: curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "   (PATH atual: $PATH)"
    exit 1
fi

if [ ! -d .venv ]; then
    "$UV" venv
    echo "✅ .venv created"
fi

echo "📦 Installing dependencies..."
"$UV" sync
echo "✅ Setup complete — run: ./run.sh  (ou .venv/bin/python demo.py)"
