#!/usr/bin/env bash
# setup.sh — Root setup: prepares all projects in the repo
set -euo pipefail

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
