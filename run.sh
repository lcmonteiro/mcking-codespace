#!/usr/bin/env bash
#
# run.sh — Unified runner for any file in mcking-codespace.
#
# Usage:
#   ./run.sh path/to/file.cpp   # compile C++ and run
#   ./run.sh path/to/file.py    # run Python
#   ./run.sh path/to/file.js    # run Node.js
#   ./run.sh path/to/file.ts    # run TypeScript (tsx / ts-node)
#   ./run.sh path/to/file.sh    # run as Bash script
#   ./run.sh path/to/file.ps1   # run as PowerShell script
#   ./run.sh path/to/file.go    # go run
#   ./run.sh path/to/file.rs    # compile Rust and run
#   ./run.sh path/to/file.c     # compile C and run
#
# If no extension is recognised, fallback to shebang detection.
# ---------------------------------------------------------------------------

set -euo pipefail

file="${1:?Usage: $0 <filename>}"

if [ ! -f "$file" ]; then
  echo "❌ File not found: $file"
  exit 1
fi

dir=$(dirname "$file")
base=$(basename "$file")
name="${base%.*}"
ext="${base##*.}"

case "$ext" in

  # ── C++ ─────────────────────────────────────────────────────────
  cpp|cc|cxx|c++ )
    echo "🔧 Compiling C++: $file"
    if command -v g++ &>/dev/null; then
      g++ -std=c++23 -O2 -Wall -Wextra -o "$name" "$file" && "./$name"
    elif command -v clang++ &>/dev/null; then
      clang++ -std=c++23 -O2 -Wall -Wextra -o "$name" "$file" && "./$name"
    else
      echo "❌ No C++ compiler found (g++ / clang++)"
      exit 1
    fi
    ;;

  # ── C ───────────────────────────────────────────────────────────
  c )
    echo "🔧 Compiling C: $file"
    if command -v gcc &>/dev/null; then
      gcc -std=c11 -O2 -Wall -Wextra -o "$name" "$file" && "./$name"
    elif command -v clang &>/dev/null; then
      clang -std=c11 -O2 -Wall -Wextra -o "$name" "$file" && "./$name"
    else
      echo "❌ No C compiler found (gcc / clang)"
      exit 1
    fi
    ;;

  # ── Python ──────────────────────────────────────────────────────
  py )
    if command -v python3 &>/dev/null; then
      python3 "$file"
    elif command -v python &>/dev/null; then
      python "$file"
    else
      echo "❌ Python not found"
      exit 1
    fi
    ;;

  # ── JavaScript ──────────────────────────────────────────────────
  js )
    if command -v node &>/dev/null; then
      node "$file"
    else
      echo "❌ Node.js not found"
      exit 1
    fi
    ;;

  # ── TypeScript ──────────────────────────────────────────────────
  ts )
    if command -v tsx &>/dev/null; then
      tsx "$file"
    elif command -v ts-node &>/dev/null; then
      ts-node "$file"
    elif command -v npx &>/dev/null; then
      npx tsx "$file"
    else
      echo "❌ No TS runner found (install tsx or ts-node)"
      exit 1
    fi
    ;;

  # ── Shell ───────────────────────────────────────────────────────
  sh )
    bash "$file"
    ;;

  # ── PowerShell ──────────────────────────────────────────────────
  ps1 )
    if command -v pwsh &>/dev/null; then
      pwsh "$file"
    elif command -v powershell &>/dev/null; then
      powershell -File "$file"
    else
      echo "❌ PowerShell not found"
      exit 1
    fi
    ;;

  # ── Go ──────────────────────────────────────────────────────────
  go )
    go run "$file"
    ;;

  # ── Rust ────────────────────────────────────────────────────────
  rs )
    echo "🔧 Compiling Rust: $file"
    rustc -O -o "$name" "$file" && "./$name"
    ;;

  # ── HTML (open in browser) ──────────────────────────────────────
  html )
    echo "🌐 Opening $file in browser..."
    case "$(uname -s)" in
      Linux*)   xdg-open "$file" 2>/dev/null || echo "  open manually" ;;
      Darwin*)  open "$file" ;;
      CYGWIN*|MINGW*|MSYS*) start "$file" ;;
      *)        echo "  open $file in your browser" ;;
    esac
    ;;

  # ── Fallback: try shebang ───────────────────────────────────────
  * )
    # Read first line and check for #!
    read -r shebang < "$file"
    if [[ "$shebang" =~ ^#! ]]; then
      echo "⚡ Running via shebang: $shebang"
      "$file"
    else
      echo "❌ Unknown extension '.$ext' and no shebang found."
      echo "   Supported: cpp/cc/cxx, c, py, js, ts, sh, ps1, go, rs, html"
      exit 1
    fi
    ;;
esac
