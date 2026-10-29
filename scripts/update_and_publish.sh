#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")/.."
PYTHON_CMD="${VULTURE_PYTHON:-/home/train/miniconda3/bin/python}"
"$PYTHON_CMD" -m vulture.symbols
"$PYTHON_CMD" -m vulture.pipeline || FETCH_STATUS=$?
"$PYTHON_CMD" -m vulture.publish
exit "${FETCH_STATUS:-0}"
