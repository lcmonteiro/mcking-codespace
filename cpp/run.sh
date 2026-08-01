#!/usr/bin/env bash
# run.sh — Build and run C++ project
set -euo pipefail

# Location-independent: run from this script's own directory
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Build if needed
if [ ! -f setup.sh ] || bash setup.sh; then
    :
fi

# Find the built binary
bin="${1:-}"
if [ -z "$bin" ]; then
    # Try the first .cpp file's binary
    for src in *.cpp; do
        [ -f "$src" ] || continue
        bin="${src%.cpp}"
        break
    done
fi

if [ -n "$bin" ] && [ -f "$bin" ]; then
    echo "🔧 Running $bin..."
    if [ -f input.txt ]; then
        ./"$bin" < input.txt
    else
        ./"$bin"
    fi
else
    echo "❌ No binary found to run"
    exit 1
fi
