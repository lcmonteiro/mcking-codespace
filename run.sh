#!/usr/bin/env bash
# run.sh — Mcking's universal runner. One script to rule them all.
#
#   ./run.sh cpp/gpt.cpp              # 🔧 compile & run C++
#   ./run.sh python/script.py         # 🐍 run python
#   ./run.sh python/llm-proxy         # 🌐 run FastAPI project folder
#   ./run.sh web/index.html           # 🌐 open in browser
#   ./run.sh scripts/foo.js           # 📦 run with node
#   ./run.sh scripts/bar.ps1          # ⚡ run with pwsh
#
# Supported: cpp cc cxx c py js ts sh ps1 go rs html
# Folder support: auto-detects FastAPI projects, delegates to dir/run.sh
# Shebang fallback for everything else.
# ----------------------------------------------------------------------

set -euo pipefail

# Location-independent: run from the repo root regardless of cwd
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

die() { echo "❌ $1"; exit 1; }
need() { command -v "$1" &>/dev/null || die "$1 not found — install it first"; }

file="${1:?Usage: $0 <filename>}"

# ── Directory / Project folder ─────────────────────────
if [ -d "$file" ]; then
  cd "$file"
  pwd=$(pwd)

  # Check for project-local run.sh first
  if [ -f "run.sh" ]; then
    echo "📁 $file/run.sh — delegating..."
    bash run.sh "${@:2}"
    exit $?
  fi

  # FastAPI detection (main.py with FastAPI import)
  if [ -f main.py ] && grep -q "FastAPI" main.py 2>/dev/null; then
    need python3
    need uvicorn
    # Install deps if requirements.txt exists
    if [ -f requirements.txt ]; then
      echo "🌐 $file — FastAPI project, installing deps..."
      pip install -q -r requirements.txt 2>&1 | tail -1
    fi
    # Run seed.py if it exists
    if [ -f seed.py ]; then
      echo "🌱 Seeding database..."
      python3 seed.py
    fi
    echo "🚀 Starting uvicorn..."
    uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
    exit $?
  fi

  # Generic Python project (has requirements.txt, no FastAPI)
  if [ -f requirements.txt ] && [ -f main.py ]; then
    need python3
    echo "🐍 $file — Python project"
    pip install -q -r requirements.txt 2>&1 | tail -1
    python3 main.py "${@:2}"
    exit $?
  fi

  die "Don't know how to run directory: $file (no run.sh, main.py, or FastAPI detected)"
fi

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
    # Procura .venv a partir do dir do script subindo até à raiz do repo.
    # (ex: python/chatinho/examples/demo.py → python/chatinho/.venv)
    script_dir="$(dirname "$file")"
    search_dir="$script_dir"
    venv_py=""
    while [ "$search_dir" != "/" ]; do
      if [ -x "$search_dir/.venv/bin/python" ]; then
        venv_py="$search_dir/.venv/bin/python"
        break
      fi
      [ "$search_dir" = "$(pwd)" ] && break
      search_dir="$(dirname "$search_dir")"
    done
    # Sem .venv: se houver setup.sh + pyproject.toml, prepara o ambiente.
    if [ -z "$venv_py" ]; then
      search_dir="$script_dir"
      while [ "$search_dir" != "/" ]; do
        if [ -f "$search_dir/setup.sh" ] && [ -f "$search_dir/pyproject.toml" ]; then
          echo "🐍 setup.sh encontrado em $search_dir — a preparar .venv..."
          (cd "$search_dir" && bash setup.sh)
          if [ -x "$search_dir/.venv/bin/python" ]; then
            venv_py="$search_dir/.venv/bin/python"
          fi
          break
        fi
        [ "$search_dir" = "$(pwd)" ] && break
        search_dir="$(dirname "$search_dir")"
      done
    fi
    if [ -n "$venv_py" ]; then
      exec "$venv_py" "$file" "${@:2}"
    fi
    python3 "$file" "${@:2}"
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
