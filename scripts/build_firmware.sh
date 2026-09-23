#!/usr/bin/env bash
# Compile the C/C++ flight controller (Linux / macOS / Git Bash).
cd "$(dirname "$0")/../firmware"

# A server that is still running keeps the built binary locked, which makes
# the linker fail with "Permission denied" / "Text file busy". Stop it first.
if pgrep -f "build/drone_controller" >/dev/null 2>&1; then
    echo "Stale drone_controller processes found - stopping them..."
    pkill -f "build/drone_controller" || true
    sleep 1
fi

if command -v make >/dev/null 2>&1; then
    make
else
    mkdir -p build
    g++ -std=c++17 -O2 -Wall -Iinclude src/main.cpp src/pid.cpp src/navigation.cpp src/telemetry.c -o build/drone_controller
fi
echo "OK → firmware/build/drone_controller"
