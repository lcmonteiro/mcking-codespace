#!/usr/bin/env bash
# setup.sh — C++ project setup
# Checks compiler availability and compiles the project.
set -euo pipefail

echo "🔧 C++ setup — checking compiler..."

if command -v g++ &>/dev/null; then
    CXX="g++"
elif command -v clang++ &>/dev/null; then
    CXX="clang++"
else
    echo "❌ No C++ compiler found (g++ or clang++)"
    exit 1
fi

echo "✅ Compiler found: $CXX ($($CXX --version | head -1))"

# Build the main project if a source file exists
for src in *.cpp; do
    [ -f "$src" ] || continue
    bin="${src%.cpp}"
    if [ ! -f "$bin" ] || [ "$src" -nt "$bin" ]; then
        echo "🔨 Building $src → $bin"
        $CXX -std=c++23 -O2 -Wall -Wextra -o "$bin" "$src"
    fi
done

echo "✅ Setup complete"
