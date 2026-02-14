#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN=""

if [ -x "${SCRIPT_DIR}/.venv/bin/python" ]; then
  PYTHON_BIN="${SCRIPT_DIR}/.venv/bin/python"
elif [ -x "${SCRIPT_DIR}/myenv/bin/python" ]; then
  PYTHON_BIN="${SCRIPT_DIR}/myenv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "ERROR: Python not found. Install Python 3.9+ or provide .venv."
  exit 1
fi

"${PYTHON_BIN}" "${SCRIPT_DIR}/app/launcher/launch.py"
