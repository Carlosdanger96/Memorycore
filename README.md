# Memorycore

Memorycore is a local-first, provider-neutral omni-memory system. It gives multiple LLMs, agents, applications, and workflows access to the same durable and inspectable memory without making any one model, provider, chat interface, or agent framework the center of the system.

Version 0.1 deliberately starts with one reliable storage core:

```text
ChatGPT / Mistral Vibe / Hermes / Codex / Gemini / local models / apps
                                  ↓
                         adapters and clients
                                  ↓
                           MemoryService
                                  ↓
                         SQLite + FTS5
```

The omni-memory is the product. Provider integrations are replaceable access layers around it.

## What omni-memory means

Memorycore is intended to:

- preserve one canonical memory source that many authorized clients can share;
- remain independent of model and provider APIs;
- store facts, decisions, preferences, procedures, corrections, notes, and future memory types;
- organize access by project today and by user, workspace, session, scope, and permissions in later phases;
- retain provenance so the system can record where a memory came from without isolating it by provider;
- expose the same memory through Python, CLI, MCP, HTTP, browser, messaging, and other adapters as those layers mature;
- remain local-first, inspectable, exportable, and auditable.

Memorycore is not an LLM router, chat application, model client, agent framework, or collection of separate provider-specific memory databases.

## Current v0.1 implementation

```text
Application, script, or future integration
    ↓
MemoryService
    ↓
SQLite + FTS5
```

MCP is deferred to a later integration phase. The current MCP adapter remains optional and is not required to install, initialize, test, or use the storage core.

## Status

The repository contains the canonical v0.1 storage implementation. It is not a stable release until GitHub Actions and Windows storage validation pass. The previous experimental implementation remains preserved on the `archive/pre-v0.1-experimental` branch.

## Requirements and downloads

Required:

- Python 3.11 or newer: https://www.python.org/downloads/
- Git: https://git-scm.com/downloads

Optional:

- SQLite command-line tools: https://www.sqlite.org/download.html
- uv: https://docs.astral.sh/uv/getting-started/installation/
- MCP Python SDK for later integration work: https://github.com/modelcontextprotocol/python-sdk

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

The base installation has no runtime dependency beyond Python's standard library.

## Python usage

```python
from memorycore import MemoryService

service = MemoryService("data/memorycore.db")
memory = service.add_memory(
    project_id="example",
    memory_type="decision",
    content="SQLite is the canonical v0.1 store.",
    tags=["storage"],
    created_by="mistral-vibe",
    metadata={
        "source_provider": "mistral",
        "source_client": "vibe",
        "source_session": "optional-session-id",
    },
)
context = service.retrieve_context(
    query="canonical store",
    project_id="example",
)
print(context["context_text"])
service.close()
```

Provider and client names are provenance metadata. They do not create separate memory silos.

## Storage operations

The storage core currently supports:

- create and initialize a SQLite database;
- add a memory;
- retrieve a memory by ID;
- project-scoped FTS5 search;
- recent-memory retrieval;
- update content, summary, tags, metadata, and status;
- archive memories without deleting them;
- health checks;
- persistence after process restart.

## Test

```powershell
python -m compileall src tests
pytest --ignore=tests/test_mcp.py
```

The storage test suite covers SQLite CRUD, FTS5 search, project scoping, update/archive behavior, CLI initialization, health checks, and restart persistence.

## Optional MCP work

MCP is not part of the v0.1 storage release gate. When integration work resumes, install the optional dependency with:

```powershell
pip install -e ".[mcp]"
```

The existing optional adapter is not considered validated until a real MCP client test is completed.

## v0.1.0 storage release gate

The `v0.1.0` tag should be created only after:

1. GitHub Actions passes on Python 3.11, 3.12, and 3.13.
2. Database initialization and `doctor` pass on Windows.
3. Add, retrieve, search, update, archive, close, reopen, and retrieve are verified on Windows.
4. Backup and restore instructions are added and tested.
5. Setup instructions are confirmed from a clean checkout.

## Architecture guardrails

All changes must preserve these rules:

1. Memorycore remains provider-neutral.
2. The canonical memory store remains readable and inspectable.
3. Integrations call the core; they do not redefine the core.
4. Provider identity is provenance metadata, not the primary memory namespace.
5. New engines and dependencies remain optional until demonstrated necessary.
6. Stable behavior, experimental behavior, and future ideas must be clearly separated.
7. Durable memories are archived, corrected, or superseded rather than silently destroyed.

See [Omni-Memory Scope](docs/OMNI_MEMORY_SCOPE.md), [Design Decisions](docs/DESIGN_DECISIONS.md), and [Future Roadmap](docs/FUTURE_ROADMAP.md).
