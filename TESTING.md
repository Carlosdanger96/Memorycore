# Testing Omni Memory Harness

## Supported environment

- Python 3.11 or newer.
- Windows PowerShell, Linux, or macOS.
- SQLite with FTS5, included with normal Python distributions.
- MCP extras for protocol and HTTP MCP tests.

## Install

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[mcp-test]"
```

Windows:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[mcp-test]"
```

## Offline judge path

```bash
./scripts/demo.sh
```

```powershell
.\scripts\demo.ps1
```

The demo creates an isolated temporary database and synthetic vault. It never
opens or overwrites the user's real Memorycore database or Obsidian vault.
On a clean checkout, the scripts create `.demo-venv`, install `.[mcp-test]`,
run the complete deterministic scenario, run the focused Omni test set, and
print exact REST and MCP startup commands. Set `MEMORYCORE_DEMO_PYTHON` to use
an already prepared interpreter in CI or controlled development environments.

## Test commands

```bash
python -m compileall src tests demo
pytest -q
python scripts/verify_demo.py
```

Expected implementation-session result:

```text
40 passed
```

Exact timing varies by machine.

Latest focused Omni verification:

```text
17 passed
```

The [latest hackathon branch workflow](https://github.com/Carlosdanger96/Memorycore/actions/workflows/omni-harness.yml?query=branch%3Ahackathon%2Fomni-memory-harness)
runs Python 3.11, 3.12, and 3.13, the deterministic source demo, isolated
wheel installation, the Windows source-and-wheel smoke test, and focused
security and migration checks. It uploads the wheel, source archive, evidence
bundle, structured demo report, schemas, and synthetic vault.

## Live GPT-5.6 mode

The offline provider remains the default. To request live structured extraction
and auditing, set these variables in the process environment:

```text
OPENAI_API_KEY=<project key>
MEMORYCORE_USE_LIVE_GPT56=true
MEMORYCORE_AUDIT_MODEL=gpt-5.6
MEMORYCORE_CORRECTION_MODEL=gpt-5.6
```

`OPENAI_BASE_URL` may override the API base URL. The provider uses the Responses
API with `store: false` and strict `text.format` JSON schemas. It never receives
authentication tokens, environment values, or unrestricted trajectory content.

The Platform project used during implementation accepted authentication but
did not have access to `gpt-5.6`; the bounded smoke test returned HTTP 403. Use
a project with model access or explicitly configure another authorized model.

Official API references used for the implementation:

- https://developers.openai.com/api/docs/guides/structured-outputs
- https://developers.openai.com/api/reference/resources/responses/methods/create

## Start services

MCP over stdio:

```bash
MEMORYCORE_DB=/absolute/path/memorycore.db memorycore-mcp
```

Authenticated Streamable HTTP MCP:

```bash
MEMORYCORE_HTTP_TOKENS_FILE=/private/tokens.json \
MEMORYCORE_TRANSPORT=streamable-http \
MEMORYCORE_HOST=127.0.0.1 \
memorycore-mcp
```

Authenticated REST API:

```bash
MEMORYCORE_HTTP_TOKENS_FILE=/private/tokens.json \
MEMORYCORE_DB=/absolute/path/memorycore.db \
MEMORYCORE_API_HOST=127.0.0.1 \
memorycore-api
```

## Scanner and projection roots

Repository scanning and Obsidian projection require explicit roots:

```text
MEMORYCORE_SCAN_ROOTS=/allowed/repository/root
MEMORYCORE_VAULT_ROOTS=/allowed/vault/root
```

Use the platform path separator to configure multiple roots. Paths are resolved
before use, and requests outside the configured roots are rejected.

## Troubleshooting

- `repository scanning requires explicit MEMORYCORE_SCAN_ROOTS`: configure the allowed source root.
- `vault path is outside the configured allowed roots`: configure `MEMORYCORE_VAULT_ROOTS` with the intended vault.
- HTTP 403 from Memorycore: verify bearer identity role and project allowlist.
- OpenAI HTTP 403: verify that the selected Platform project has access to the configured model.
- Sequence validation error: append the next trajectory event number; prior events are immutable.
