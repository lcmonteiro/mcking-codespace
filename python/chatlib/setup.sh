#!/usr/bin/env bash
# setup.sh — chatlib package setup (pyproject.toml)
# Cria o .venv e instala TODAS as dependências.
# Se o uv não estiver instalado, instala-o automaticamente.
set -euo pipefail

echo "🐍 chatlib setup — preparing virtual environment..."

# Já está pronto? Skip (não exige uv).
if [ -x .venv/bin/python ] && .venv/bin/python -c "import textual" 2>/dev/null; then
    echo "✅ .venv already ready — skipping"
    exit 0
fi

# Localizar uv: PATH ou localizações comuns (inclui $PREFIX para Termux).
find_uv() {
    local cand
    for cand in "$(command -v uv 2>/dev/null || true)" \
        "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" \
        "/usr/local/bin/uv" "${PREFIX:-/usr}/bin/uv"; do
        if [ -x "$cand" ]; then
            echo "$cand"
            return 0
        fi
    done
    return 1
}

UV="$(find_uv || true)"

# Se não existe uv, instala automaticamente.
if [ -z "$UV" ]; then
    echo "⬇️  uv not found — installing automatically..."
    if command -v curl &>/dev/null; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget &>/dev/null; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        echo "❌ curl/wget not available — install uv manually: https://docs.astral.sh/uv/"
        echo "   (Termux: pkg install uv)"
        exit 1
    fi
    UV="$(find_uv || true)"
    if [ -z "$UV" ]; then
        echo "❌ uv installed but not found — adiciona ~/.local/bin ao PATH e corre de novo."
        echo "   (PATH atual: $PATH)"
        exit 1
    fi
    echo "✅ uv instalado em: $UV"
fi

if [ ! -d .venv ]; then
    "$UV" venv
    echo "✅ .venv created"
fi

echo "📦 Installing all dependencies..."
"$UV" sync
echo "✅ Setup complete — run: ./run.sh  (ou .venv/bin/python demo.py)"
