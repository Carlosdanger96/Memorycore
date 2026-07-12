# Memorycore

Memorycore is a shared memory system for multiple LLMs.

Its one purpose is to let different LLMs store, retrieve, and share the same persistent memories through a common memory layer. Instead of every LLM maintaining a separate and isolated memory system, Memorycore provides one provider-neutral source of memory that can be used by ChatGPT, Mistral, Hermes, Gemini, Claude, Codex, local models, and other LLM systems.

Everything in this repository—the database, `MemoryService`, search, MCP adapter, APIs, permissions, provenance, and future synchronization work—exists only to support that goal.

Memorycore is not primarily a note-taking application, database experiment, agent framework, or general knowledge-management platform. It is a shared memory layer for multiple LLMs.

## Current architecture

Version 0.1 establishes the durable storage foundation required for shared LLM memory:

```text
Multiple LLM clients
            ↓
   One Memorycore MCP service
            ↓
 policy, lifecycle, audit, retrieval
            ↓
SQLite (local prototype) → PostgreSQL (shared production)
```

The current release focuses on one durable SQLite database and one `MemoryService`. It includes an optional stdio MCP adapter with the same record contract for every client, including a real stdio client integration test; the next release gate is deployment guidance and Windows validation.

## Status

The repository contains the canonical v0.1 storage implementation plus a tested MCP integration boundary. It is not a stable release until GitHub Actions and Windows storage validation pass. The previous experimental implementation remains preserved on the `archive/pre-v0.1-experimental` branch.

The storage core is the first implementation layer of the shared-memory system. It is not the final product by itself. Memorycore reaches its main goal when multiple LLMs can reliably use the same memories through validated integrations.

## Requirements and downloads

Required:

- Python 3.11 or newer: https://www.python.org/downloads/
- Git: https://git-scm.com/downloads

Optional:

- SQLite command-line tools: https://www.sqlite.org/download.html
- uv: https://docs.astral.sh/uv/getting-started/installation/
- MCP Python SDK for shared-LLM integration work: https://github.com/modelcontextprotocol/python-sdk

Python already provides SQLite through the built-in `sqlite3` module. A separate database server is not required.

## Install on Windows

```powershell
git clone https://github.com/Carlosdanger96/Memorycore.git
cd Memorycore
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[test]"
memorycore --db .\data\memorycore.db init
memorycore --db .\data\memorycore.db doctor
```

### One-command Windows setup

After cloning the repository, PowerShell can set up the local prototype:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup-windows.ps1
```

Use `-StartService` to initialize and immediately start the local Streamable
HTTP MCP service. Use `.\scripts\verify-windows.ps1` later to re-run health
checks and the test suite.

The base installation has no runtime dependency beyond Python's standard library.

## Python usage

```python
from memorycore import MemoryService

service = MemoryService("data/memorycore.db")
memory = service.add_memory(
    project_id="example",
    memory_type="decision",
    content="Memorycore provides shared persistent memory for multiple LLMs.",
    tags=["shared-memory"],
)
context = service.retrieve_context(
    query="shared persistent memory",
    project_id="example",
)
print(context["context_text"])
service.close()
```

## Storage operations

The current storage foundation supports:

- creating and initializing the shared SQLite database;
- adding a memory;
- retrieving a memory by ID;
- project-scoped FTS5 search;
- recent-memory retrieval;
- updating content, summaries, tags, metadata, and status;
- archiving memories without deleting them;
- health checks;
- persistence after process restart.

These operations provide the durable memory layer that future LLM integrations will share.

## Test

```powershell
python -m compileall src tests
pip install -e ".[mcp-test]"
pytest
```

The storage test suite covers SQLite CRUD, FTS5 search, project scoping, update/archive behavior, CLI initialization, health checks, and restart persistence.

## Shared LLM integration

MCP is the planned first common interface for connecting multiple LLMs to Memorycore. Install the optional dependency with:

```powershell
pip install -e ".[mcp]"
```

Run a local stdio instance only for development or a host that cannot use HTTP:

```powershell
memorycore --db .\data\memorycore.db serve
```

For the shared service, run exactly one central MCP process:

```powershell
memorycore --db .\data\memorycore.db serve-http --host 127.0.0.1 --port 8000
```

Clients then connect to `http://127.0.0.1:8000/mcp`. Do not expose this local
prototype endpoint publicly. The production deployment target is one central
service backed by PostgreSQL and protected with MCP-compatible OAuth; the
SQLite backend remains the local single-host mode.

To switch the central service to PostgreSQL, copy `.env.example`, start the
included local PostgreSQL container, install `.[postgres,mcp]`, then set
`MEMORYCORE_DATABASE_URL`. See [Central Service Architecture](docs/CENTRAL_SERVICE_ARCHITECTURE.md).

Each memory records its writer and provenance: `created_by`, `updated_by`,
`client_id`, `model_provider`, `model_name`, `session_id`, `source_type`,
`source_uri`, `source_id`, and optional `confidence` (0–1). The MCP tools are
`memory_add`, `memory_get`, `memory_search`, `memory_retrieve_context`,
`memory_update`, `memory_archive`, and `memory_health`.

Each local MCP process receives its identity from its environment. This prevents
an LLM tool call from impersonating another client. Supported roles are
`reader`, `writer`, `approver`, and `administrator`. Writers create pending
memories and can edit only their own pending records; approvers and
administrators can approve, reject, or archive records. The server also exposes
`memory_approve` and `memory_reject` for those controlled lifecycle changes.

For shared or remote deployments, configure the server instead of trusting the
client:

```powershell
$env:MEMORYCORE_READ_ONLY = "true"                  # block every write
$env:MEMORYCORE_ALLOWED_PROJECTS = "memorycore,hermes" # limit all reads/writes
$env:MEMORYCORE_REQUIRE_APPROVAL = "true"           # new MCP writes start pending
$env:MEMORYCORE_CLIENT_ID = "mistral-vibe"           # assigned by this server process
$env:MEMORYCORE_CLIENT_ROLE = "writer"               # reader|writer|approver|administrator
$env:MEMORYCORE_MODEL_PROVIDER = "mistral"
$env:MEMORYCORE_MODEL_NAME = "codestral"
```

An unset allowlist permits all projects. `MEMORYCORE_REQUIRE_APPROVAL` lets a
trusted client promote a reviewed memory from `pending` to `active` with
`memory_approve`. Normal search and context retrieval return only `active`
memories; an explicit `status` argument is required to retrieve history.
Future supported integrations must preserve this contract and
the same shared database rather than creating provider-specific memory silos.

## v0.1.0 storage release gate

The `v0.1.0` tag should be created only after:

1. GitHub Actions passes on Python 3.11, 3.12, and 3.13.
2. Database initialization and `doctor` pass on Windows.
3. Add, retrieve, search, update, archive, close, reopen, and retrieve are verified on Windows.
4. Backup and restore instructions are added and tested.
5. Setup instructions are confirmed from a clean checkout.

## Project direction

All future work must directly improve the ability of multiple LLMs to store, retrieve, and share the same memory safely and reliably.

Planned supporting capabilities include validated MCP and API access, provenance, permissions, correction and supersession, retrieval quality, synchronization, and LLM-specific connectors. Storage engines, embeddings, graphs, consolidation, and other technical components should only be added when they materially improve the shared-memory goal.

See [Design Decisions](docs/DESIGN_DECISIONS.md) and the
[v0.2.0 Prototype Plan](docs/PROTOTYPE_PLAN.md).
