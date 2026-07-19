#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}src" python -m memorycore.demo.runner "$@"
