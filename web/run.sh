#!/usr/bin/env bash
# run.sh — Web root: list sub-projects
set -euo pipefail

echo "🌐 Web projects in this repo:"
echo
for dir in cellular-automata fluid-sim particle-life thunderstorm; do
    if [ -d "$dir" ] && [ -f "$dir/index.html" ]; then
        abs="$(cd "$dir" && pwd)/index.html"
        echo "   📄 $dir/  →  $abs"
    fi
done
echo "   📂 diagrams/       → static SVGs"
echo "   💬 chat-codec/     → npm run dev (Node + WASM)"
echo
echo "To open:  xdg-open <path>  (Linux) or explorer.exe <path> (WSL)"
