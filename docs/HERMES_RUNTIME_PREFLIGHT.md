# Isolated Hermes SDK preflight

## Finding and limits

PR #14 at `ec64e5db71b15ed7f5585088f97490eba71240a2` records MCP discovery
followed by a missing OpenAI SDK module during isolated Hermes startup. It does
not include the original traceback, interpreter path, Hermes commit, or package
inventory. The precise cause in that Windows environment is therefore unproven.

Upstream Hermes inspected on 2026-11-04 at commit
`3a1e9ef50a570b1544795ddad197ad2dcde430ab` has:

- `.python-version`: `3.14`.
- `pyproject.toml`: `requires-python = ">=3.11,<3.15"`, explicitly retaining
  older interpreters for updater compatibility, while its core dependency is
  `openai==2.54.0; python_version >= '3.14'`.
- `agent/process_bootstrap.py:_load_openai_cls`: a lazy
  `from openai import OpenAI`. This explains how discovery can precede a model
  client import failure. It does not imply the model provider must be OpenAI.
- A separate MCP extra (`mcp==2.3.0` in this inspected revision). Memorycore's
  own service uses MCP 1.x. Keep client and service environments separate.
- Bootstrap-managed dependency activation and interpreter relaunch. A raw Python
  probe describes that interpreter, not necessarily the environment selected by
  the normal Hermes launcher after bootstrap.

Sources: [Hermes metadata](https://github.com/NousResearch/hermes-agent/blob/3a1e9ef50a570b1544795ddad197ad2dcde430ab/pyproject.toml),
[runtime selection](https://github.com/NousResearch/hermes-agent/blob/3a1e9ef50a570b1544795ddad197ad2dcde430ab/.python-version),
[lazy SDK import](https://github.com/NousResearch/hermes-agent/blob/3a1e9ef50a570b1544795ddad197ad2dcde430ab/agent/process_bootstrap.py),
[bootstrap](https://github.com/NousResearch/hermes-agent/blob/3a1e9ef50a570b1544795ddad197ad2dcde430ab/hermes_bootstrap.py).

Installing this Hermes revision under Python 3.11–3.13 can succeed while skipping
the SDK. This is an interpreter/installation isolation trap, not a missing
Memorycore service dependency. Other possibilities remain: `--no-deps`, an
incomplete install, a different launcher interpreter, a shadowing `openai.py`,
or a missing nested module in an incompatible SDK. Do not add OpenAI to
Memorycore's core requirements or install an arbitrary latest SDK globally.

## Disposable Windows correction

Run from a fresh PowerShell session. Use a new sandbox directory and a local
Hermes source checkout; never point these commands at the installed application's
working tree. The independent clone matters because Hermes bootstrap can repair
or synchronize its checkout. Pin the exact revision being evaluated.

```powershell
$HermesSource = 'C:\path\to\hermes-agent'
$MemorycoreSource = 'C:\path\to\Memorycore'
$Sandbox = Join-Path $env:TEMP ('memorycore-hermes-' + [guid]::NewGuid().ToString('N'))
$Revision = (& git -C $HermesSource rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot identify Hermes revision' }
New-Item -ItemType Directory -Path $Sandbox -ErrorAction Stop | Out-Null
$ClientSource = Join-Path $Sandbox 'source'
& git clone --no-hardlinks --no-checkout $HermesSource $ClientSource
if ($LASTEXITCODE -ne 0) { throw 'Disposable clone failed' }
& git -C $ClientSource checkout --detach $Revision
if ($LASTEXITCODE -ne 0) { throw 'Pinned checkout failed' }
$env:HERMES_HOME = Join-Path $Sandbox 'home'
New-Item -ItemType Directory -Path $env:HERMES_HOME -ErrorAction Stop | Out-Null
# Discard inherited Python/PM activation paths in this disposable shell.
Remove-Item Env:PYTHONPATH, Env:PYTHONHOME, Env:VIRTUAL_ENV, Env:__HERMES_ACTIVATED, Env:HERMES_RUNTIME_DIR -ErrorAction SilentlyContinue
$Runtime = (Get-Content (Join-Path $ClientSource '.python-version') -Raw).Trim()
$Venv = Join-Path $Sandbox 'runtime'
& uv venv --python $Runtime $Venv
if ($LASTEXITCODE -ne 0) { throw 'Client environment creation failed' }
$ClientPython = Join-Path $Venv 'Scripts\python.exe'
& uv pip install --python $ClientPython -e "${ClientSource}[mcp]"
if ($LASTEXITCODE -ne 0) { throw 'Hermes dependency installation failed' }
& uv pip check --python $ClientPython
if ($LASTEXITCODE -ne 0) { throw 'Client dependency conflicts' }
& $ClientPython (Join-Path $MemorycoreSource 'scripts\check-hermes-runtime.py') --hermes-source $ClientSource
if ($LASTEXITCODE -ne 0) { throw 'SDK preflight failed; retain sanitized output' }
```

This installs the checkout's declared dependencies with its selected interpreter.
It deliberately does not reuse Memorycore's `.venv` or the production Hermes
environment. For the inspected revision the selected interpreter is Python 3.14.
For another revision, inspect its requirements rather than copying these pins.
`uv` may download the required interpreter. Uncommitted source changes are not
included by the clone; record them separately if they explain the failed run.

After preflight, configure only the new `$env:HERMES_HOME\config.yaml` with an
explicit intended provider/model and the MCP example. Supply a dedicated test
token and credentials privately. Do not copy production `state.db`, memories,
`auth.json`, or `.env`. Clear unrelated inherited provider credentials before
the test and avoid automatic fallback routes. Start Hermes from `$ClientSource`
using `$ClientPython -m hermes_cli.main --help` first, then the supported chat
command for that revision. Its bootstrap may select a managed runtime; record
that runtime and rerun the probe with the same dependency search paths if it
differs. A passing raw probe alone is insufficient.

If preflight reports a missing module on the correct runtime, reinstall the
checkout's declared requirements into this disposable environment. For missing
symbols or nested modules, compare reported SDK version/origin with that
checkout's pin and investigate local module shadowing. Preserve the original
traceback privately; do not change imports merely to suppress an error.

Rollback: close the disposable client, close this PowerShell session (restoring
the parent environment), then remove only the newly created sandbox. Do not
delete a Memorycore service database or the production Hermes home.

## Verification gates

The probe imports SDKs only; it reads no credentials, launches no Hermes
bootstrap, makes no provider request, and never opens a memory database.

| Check | What it establishes |
| --- | --- |
| Exact interpreter, package version, import origin and required symbols | Client SDK availability; no model authentication claim |
| Hermes ordinary non-tool response with explicit provider/model | Provider authentication and model execution |
| Authenticated MCP discovery and scoped read through real Hermes | Client connection, token identity and basic tool dispatch |
| Vibe adds pending record; Hermes reviews, approves and corrects it | Model-selected tools and distinct writer/approver roles |
| Vibe retrieves replacement and both clients inspect history after service restart | Real-client shared-memory handoff and persistence |
| Backup/restore preserves record IDs, links, history, scope and retrieval | Recovery gate |

Use one disposable central HTTP service/database, separate project-scoped client
tokens and a unique test marker. Check tool results and server-side audit/IDs,
not just model claims. A writer must not approve its own proposal; ensure an
unrelated project cannot be read. Restart only this disposable service.

Vibe's rejected Mistral API key is independent of Hermes' SDK import failure.
A valid Mistral credential is required for that provider path. The release plan
also records a real Ollama-backed Vibe write without a Mistral key; that path can
proceed if intentionally selected and available, but its prior tool-result
handling/turn-limit problem still needs testing. Do not silently change a
production provider to bypass either blocker.

Memorycore unit/protocol tests, isolated SDK checks and disposable MCP checks can
proceed without either production client. Full Windows launcher and model-driven
handoff checks require the actual clients and usable provider access. Keep the
roadmap gates open for production ownership/operations, external HTTPS/OAuth,
ChatGPT discovery/scoped read and Omni adapter verification. Earlier CI failures
are not evidence that the latest PR head fails.

## Validation in this change (2026-11-04)

- Linux Python 3.12.14, Memorycore MCP 1.30.0: the probe reports MCP import
  success, missing `openai`, and a checkout-runtime mismatch against the pinned
  Hermes metadata. A resolver dry run of that metadata's exact OpenAI requirement
  under 3.12 makes no changes: the environment marker excludes the SDK.
- Separate Python 3.14.9 environment with `openai==2.54.0` and `mcp==2.3.0`:
  all SDK preflight imports/symbols pass; `uv pip check` passes. This is an SDK
  compatibility check, not a complete Hermes installation or model execution.
- Memorycore suite: 53 passed, 6 PostgreSQL tests skipped because
  `MEMORYCORE_TEST_POSTGRES_URL` was not configured. Seven added preflight cases
  cover runtime mismatch, missing package/nested/transitive modules, missing
  symbols and sanitized import failures.
- Windows PowerShell procedure, actual Hermes bootstrap/managed activation,
  provider authentication and the real-client handoff were not executed here.
  No production routing, credentials or existing memories were changed.
