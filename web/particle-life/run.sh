#!/usr/bin/env bash
# run.sh — Particle Life (static)
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
FILE="$DIR/index.html"

echo "🦠 Opening $FILE..."
if command -v xdg-open &>/dev/null; then
    xdg-open "$FILE"
elif command -v explorer.exe &>/dev/null; then
    explorer.exe "$(wslpath -w "$FILE")"
else
    echo "Open manually: $FILE"
fi
