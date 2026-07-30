#!/usr/bin/env bash
# run.sh — Diagrams (static SVG)
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

echo "📐 Diagrams in $DIR:"
for svg in *.svg; do
    [ -f "$svg" ] || continue
    echo "   📄 $svg"
done
echo
echo "Open with:  xdg-open <file>  or  explorer.exe <file> (WSL)"
