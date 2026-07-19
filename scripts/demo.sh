#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

if [ -n "${MEMORYCORE_DEMO_PYTHON:-}" ]; then
    PYTHON=$MEMORYCORE_DEMO_PYTHON
else
    VENV="$ROOT/.demo-venv"
    if [ ! -x "$VENV/bin/python" ]; then
        "${PYTHON_BOOTSTRAP:-python3}" -m venv "$VENV"
    fi
    PYTHON="$VENV/bin/python"
    if ! "$PYTHON" -c "import memorycore, pytest, mcp" >/dev/null 2>&1; then
        "$PYTHON" -m pip install --upgrade pip
        "$PYTHON" -m pip install -e ".[mcp-test]"
    fi
fi

"$PYTHON" -m memorycore.demo.runner "$@"
if [ "${MEMORYCORE_DEMO_SKIP_TESTS:-false}" != "true" ]; then
    "$PYTHON" -m pytest -q \
        tests/test_omni_demo.py tests/test_omni_experience.py \
        tests/test_omni_scanner.py tests/test_omni_audit_provider.py \
        tests/test_omni_interfaces.py tests/test_omni_audit_projection.py
fi

echo "REST: MEMORYCORE_HTTP_TOKENS_FILE=/private/tokens.json memorycore-api"
echo "MCP:  MEMORYCORE_HTTP_TOKENS_FILE=/private/tokens.json MEMORYCORE_TRANSPORT=streamable-http memorycore-mcp"
