#!/usr/bin/env bash
# setup.sh — Web projects root setup
# Static projects (cellular-automata, diagrams, fluid-sim, particle-life, thunderstorm)
# need no setup — just open index.html in a browser.
set -euo pipefail

echo "🌐 Web projects — checking sub-projects..."
echo

for dir in cellular-automata diagrams fluid-sim particle-life thunderstorm; do
    if [ -d "$dir" ]; then
        if [ -f "$dir/index.html" ]; then
            echo "   ✅ $dir — static, ready (open $dir/index.html)"
        else
            echo "   📁 $dir — present"
        fi
    fi
done

echo
echo "🌐 chat-codec — run: cd chat-codec && bash setup.sh"
echo "✅ Web root setup complete"
