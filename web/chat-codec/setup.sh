#!/usr/bin/env bash
# setup.sh — Chat Codec project setup
# Installs Node dependencies, initialises git submodule, and checks Emscripten.
set -euo pipefail

echo "🌐 Chat Codec setup..."

# ── Node dependencies ─────────────────────────────────
if [ -f package.json ]; then
    if [ ! -d node_modules ]; then
        echo "📦 Installing npm packages..."
        npm install
    else
        echo "✅ node_modules already exists"
    fi
fi

# ── Git submodule (codec-share) ──────────────────────
if [ -f .gitmodules ] || [ -d wasm/codec-share ]; then
    if [ ! -f wasm/codec-share/include/codec.hpp ]; then
        echo "📦 Initialising git submodule..."
        git submodule update --init wasm/codec-share
    else
        echo "✅ codec-share submodule ready"
    fi
fi

# ── Emscripten check (for WASM build) ────────────────
if ! command -v em++ &>/dev/null; then
    echo "⚠️  Emscripten not found. To build WASM, activate it first:"
    echo "   source /path/to/emsdk/emsdk_env.sh"
    echo "   Or install: sudo apt install emscripten"
else
    echo "✅ Emscripten found: $(em++ --version | head -1)"
fi

echo "✅ Setup complete — run: npm run dev"
