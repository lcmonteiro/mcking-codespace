#!/usr/bin/env bash
# run.sh — Mcking's universal runner. One script to rule them all.
#
#   ./run.sh cpp/gpt.cpp       # 🔧 compile & run C++
#   ./run.sh python/script.py  # 🐍 run python
#   ./run.sh web/index.html    # 🌐 open in browser
#   ./run.sh scripts/foo.js    # 📦 run with node
#   ./run.sh scripts/bar.ps1   # ⚡ run with pwsh
#
# Supported: cpp cc cxx c py js ts sh ps1 go rs html
# Shebang fallback for everything else.
# ----------------------------------------------------------------------

set -euo pipefail

die() { echo "❌ $1"; exit 1; }
need() { command -v "$1" &>/dev/null || die "$1 not found — install it first"; }

file="${1:?Usage: $0 <filename>}"
[ -f "$file" ] || die "File not found: $file"

base=$(basename "$file")
name="${base%.*}"
ext="${base##*.}"

case "$ext" in

  # ── C++ ──────────────────────────────────────────────
  cpp|cc|cxx|c++ )
    need g++
    echo "🔧 Compiling $base..."
    g++ -std=c++23 -O2 -Wall -Wextra -o "$name" "$file"
    echo "🚀 Running..."
    "./$name"
    ;;

  # ── C ────────────────────────────────────────────────
  c )
    need gcc
    echo "🔧 Compiling $base..."
    gcc -std=c11 -O2 -Wall -Wextra -o "$name" "$file"
    echo "🚀 Running..."
    "./$name"
    ;;

  # ── Python ───────────────────────────────────────────
  py )
    need python3
    echo "🐍 $base"
    python3 "$file"
    ;;

  # ── JavaScript ───────────────────────────────────────
  js )
    need node
    echo "📦 $base"
    node "$file"
    ;;

  # ── TypeScript ───────────────────────────────────────
  ts )
    if command -v tsx &>/dev/null; then
      echo "📦 $base (tsx)"
      tsx "$file"
    elif command -v ts-node &>/dev/null; then
      echo "📦 $base (ts-node)"
      ts-node "$file"
    else
      need npx
      echo "📦 $base (tsx via npx)"
      npx tsx "$file"
    fi
    ;;

  # ── Shell ────────────────────────────────────────────
  sh )
    echo "⚡ $base"
    bash "$file"
    ;;

  # ── PowerShell ───────────────────────────────────────
  ps1 )
    if command -v pwsh &>/dev/null; then
      echo "⚡ $base (pwsh)"
      pwsh "$file"
    elif command -v powershell &>/dev/null; then
      echo "⚡ $base (powershell)"
      powershell -File "$file"
    else
      die "PowerShell not found"
    fi
    ;;

  # ── Go ───────────────────────────────────────────────
  go )
    need go
    echo "🔧 $base"
    go run "$file"
    ;;

  # ── Rust ─────────────────────────────────────────────
  rs )
    need rustc
    echo "🔧 Compiling $base..."
    rustc -O -o "$name" "$file"
    echo "🚀 Running..."
    "./$name"
    ;;

  # ── HTML — open in browser ───────────────────────────
  html )
    echo "🌐 Opening $base..."
    case "$(uname -s)" in
      Linux*)   xdg-open "$file" 2>/dev/null || echo "   → open $file manually" ;;
      Darwin*)  open "$file" ;;
      CYGWIN*|MINGW*|MSYS*) start "$file" ;;
      *)        echo "   → open $file in your browser" ;;
    esac
    ;;

  # ── Fallback: shebang ────────────────────────────────
  * )
    read -r shebang < "$file"
    if [[ "$shebang" =~ ^#! ]]; then
      echo "⚡ $base (shebang)"
      "$file"
    else
      die "Unknown .$ext and no shebang — supported: cpp/cc/cxx/c/py/js/ts/sh/ps1/go/rs/html"
    fi
    ;;

esac
