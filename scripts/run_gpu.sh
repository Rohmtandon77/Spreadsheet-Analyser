#!/usr/bin/env bash
# Ensure the real driver libcuda.so is found before CUDA toolkit stubs.
# Required on this machine to avoid "Error 802: system not yet initialized".
export LD_LIBRARY_PATH="/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

VENV="$(dirname "$0")/../.venv/bin/python"
exec "$VENV" "$@"
