#!/usr/bin/env bash
# build.sh — Compila C++ com GCC ou Clang (Linux/WSL2).
#
#   ./scripts/build.sh cpp/gpt.cpp          # 🔧 build
#   ./scripts/build.sh cpp/gpt.cpp -run     # 🔧🚀 build + run
#   ./scripts/build.sh cpp/gpt.cpp -clang   # 🏗️ Clang

set -euo pipefail

die() { echo -e "\e[31m❌ $1\e[0m"; exit 1; }
ok()  { echo -e "\e[32m✅ $1\e[0m"; }

FILE="${1:-}"
RUN=false
USE_CLANG=false

[[ -z "$FILE" ]] && die "Uso: $0 <file.cpp> [-run] [-clang]"

shift || true
for arg in "$@"; do
  case "$arg" in
    -run)   RUN=true ;;
    -clang) USE_CLANG=true ;;
  esac
done

[[ ! -f "$FILE" ]] && die "Ficheiro não encontrado: $FILE"

OUT_NAME="${FILE%.*}"
OUT_PATH="$(pwd)/$OUT_NAME"

echo -e "\e[36m🔧 A compilar $(basename "$FILE")...\e[0m"

CXX="g++"
CXX_FLAGS="-std=c++23 -O2 -Wall -Wextra"

if $USE_CLANG; then
  CXX="clang++"
fi

if ! command -v "$CXX" &>/dev/null; then
  die "Compilador não encontrado: $CXX (instala g++ ou clang++)"
fi

$CXX $CXX_FLAGS -o "$OUT_PATH" "$FILE"
ok "Compilado: $OUT_PATH"

if $RUN; then
  echo -e "\e[36m🚀 A executar...\e[0m"
  "$OUT_PATH"
fi
