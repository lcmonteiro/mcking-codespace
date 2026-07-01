#!/usr/bin/env bash
# build.sh — Compile codec-share to WASM via Emscripten
# Run from the chat-codec project root:  ./wasm/build.sh
#
# Prerequisites (GitHub Codespace):
#   sudo apt install emscripten   OR
#   git clone https://github.com/emscripten-core/emsdk.git
#   cd emsdk && ./emsdk install latest && ./emsdk activate latest
#   source ./emsdk_env.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WASM_DIR="$SCRIPT_DIR"
PUBLIC_DIR="$PROJECT_DIR/public"

# ── paths ────────────────────────────────────────────────
CODEC_DIR="${CODEC_DIR:-$SCRIPT_DIR/codec-share}"
BUILD_DIR="$WASM_DIR/build"

# ── validate ─────────────────────────────────────────────
if ! command -v em++ &>/dev/null; then
    echo "ERROR: em++ not found. Activate Emscripten SDK first."
    echo "  source /path/to/emsdk/emsdk_env.sh"
    exit 1
fi
if [ ! -d "$CODEC_DIR/include" ]; then
    echo "ERROR: codec-share submodule not found at $CODEC_DIR"
    echo "  git submodule update --init wasm/codec-share"
    echo "  or: CODEC_DIR=/path/to/codec-share bash wasm/build.sh"
    exit 1
fi

# ── build ────────────────────────────────────────────────
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

EM_FLAGS=(
    -std=c++17
    -O3
    -s WASM=1
    -s MODULARIZE=1
    -s EXPORT_NAME='CodecShare'
    -s ALLOW_MEMORY_GROWTH=1
    -s MAXIMUM_MEMORY=128MB
    -s FILESYSTEM=0
    -s SINGLE_FILE=0
    -s DISABLE_EXCEPTION_CATCHING=0
    -flto
    --closure 1
    -s EXPORTED_FUNCTIONS='[
        "_enc_begin","_enc_next","_enc_reset",
        "_dec_create","_dec_feed","_dec_get","_dec_reset",
        "_mem_free","_last_error","_ping",
        "_malloc","_free"
    ]'

    -s EXPORTED_RUNTIME_METHODS='[ccall,getValue,setValue,HEAPU8,HEAP32,UTF8ToString]'
    -I "$CODEC_DIR"
)

echo "→ Compiling codec-share WASM..."
em++ "${EM_FLAGS[@]}" \
    -o "$PUBLIC_DIR/codec_share.js" \
    "$WASM_DIR/codec_wrapper.cpp"

echo "✓ Output:"
echo "  $PUBLIC_DIR/codec_share.js"
echo "  $PUBLIC_DIR/codec_share.wasm"
echo "  $PUBLIC_DIR/codec_share.wasm.map (if dwarf)"
du -h "$PUBLIC_DIR/codec_share."*
