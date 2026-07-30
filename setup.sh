#!/usr/bin/env bash
# setup.sh — Mcking's universal setup. Prepares the environment for any project.
#
#   ./setup.sh                         # 🚀 setup all projects
#   ./setup.sh cpp/                    # 🔧 setup C++ only
#   ./setup.sh python/clai/            # 🐍 setup Python Clai only
#   ./setup.sh python/llm-proxy        # 🐍 setup LLM Proxy only
#   ./setup.sh web/chat-codec          # 🌐 setup Chat Codec only
#
# ----------------------------------------------------------------------

set -euo pipefail

die() { echo "❌ $1"; exit 1; }

# ── If an argument is given, delegate to that project's setup.sh ────
if [ $# -ge 1 ]; then
  target="$1"
  # Strip trailing slash
  target="${target%/}"

  if [ -d "$target" ]; then
    if [ -f "$target/setup.sh" ]; then
      echo "📁 $target/setup.sh — delegating..."
      (cd "$target" && bash setup.sh "${@:2}")
      exit $?
    else
      die "No setup.sh found in $target"
    fi
  fi

  # Maybe it's a Python script or something that needs its parent dir
  dir=$(dirname "$target")
  if [ -d "$dir" ] && [ -f "$dir/setup.sh" ]; then
    echo "📁 $dir/setup.sh — delegating..."
    (cd "$dir" && bash setup.sh)
    exit $?
  fi

  die "Don't know how to run setup for: $target"
fi

# ── No argument → setup everything ─────────────────────
echo "🚀 Mcking Codespace — full setup"
echo

setup_dir() {
    local dir="$1"
    local label="$2"
    if [ -f "$dir/setup.sh" ]; then
        echo "━━━ $label ($dir/setup.sh) ━━━"
        (cd "$dir" && bash setup.sh) && echo "   ✅ $label ready" || echo "   ⚠️  $label had issues"
        echo
    fi
}

setup_dir "cpp"          "C++"
setup_dir "python/clai"  "Python Clai"
setup_dir "python/llm-proxy" "Python LLM Proxy"
setup_dir "web/chat-codec" "Web Chat Codec"
setup_dir "web"          "Web static projects"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Root setup complete"
echo "Run individual projects with: ./run.sh <project>"
