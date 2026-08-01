#!/usr/bin/env bash
# run.sh — Python demos runner
#
#   ./run.sh                    # 📋 list available demos
#   ./run.sh metaballs          # 🐍 run a demo (with or without .py)
#   ./run.sh metaballs.py --foo # 🐍 pass extra args through
#
# Uses .venv if present (see setup.sh), otherwise falls back to system python3.
set -euo pipefail

# Location-independent: run from this script's own directory
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PY="python3"
[ -x .venv/bin/python ] && PY=".venv/bin/python"

list_demos() {
    echo "🐍 Python demos in this folder:"
    echo
    for f in *.py; do
        [ "$f" = "test_fractal.py" ] && continue
        [ "$f" = "test_password_generator.py" ] && continue
        desc=$(grep -m1 -oP '(?<=— ).*' "$f" 2>/dev/null | head -1 || true)
        [ -z "$desc" ] && desc=$(grep -m1 -oP '(?<=# ).*' "$f" 2>/dev/null | head -1 || true)
        echo "   🎬 ${f%.py}  ${desc:+— $desc}"
    done
    echo
    echo "To run:  ./run.sh <demo>   (or from root:  ./run.sh python/<demo>.py)"
}

if [ $# -eq 0 ]; then
    list_demos
    exit 0
fi

demo="$1"
shift

# Normalize: accept "metaballs", "metaballs.py", or "python/metaballs.py"
case "$demo" in
    *.py) file="$demo" ;;
    */*)  file="$demo" ;;
    *)    file="$demo.py" ;;
esac

if [ ! -f "$file" ]; then
    echo "❌ Demo not found: $file"
    echo
    list_demos
    exit 1
fi

echo "🐍 $file"
exec "$PY" "$file" "$@"
