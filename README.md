# Memorycore

Memorycore is a shared memory system for multiple LLMs.

Its one purpose is to let different LLMs store, retrieve, and share the same persistent memories through a common memory layer. Instead of every LLM maintaining a separate and isolated memory system, Memorycore provides one provider-neutral source of memory that can be used by ChatGPT, Mistral, Hermes, Gemini, Claude, Codex, local models, and other LLM systems.

Everything in this repository—the database, `MemoryService`, search, MCP adapter, APIs, permissions, provenance, and future synchronization work—exists only to support that goal.

Memorycore is not primarily a note-taking application, database experiment, agent framework, or general knowledge-management platform. It is a shared memory layer for multiple LLMs.

## Current architecture

Version 0.1 establishes the durable storage foundation required for shared LLM memory:

```text
Multiple LLMs and integrations
            ↓
     Shared memory interface
            ↓
        MemoryService
            ↓
       SQLite + FTS5
```

The current release focuses on one durable SQLite database and one `MemoryService`. MCP and direct LLM integrations remain an integration phase, but they are part of the central project goal rather than a separate purpose.

## Status

The repository contains the canonical v0.1 storage implementation. It is not a stable release until GitHub Actions and Windows storage validation pass. The previous experimental implementation remains preserved on the `archive/pre-v0.1-experimental` branch.

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
pytest --ignore=tests/test_mcp.py
```

The storage test suite covers SQLite CRUD, FTS5 search, project scoping, update/archive behavior, CLI initialization, health checks, and restart persistence.

## Shared LLM integration

MCP is the planned first common interface for connecting multiple LLMs to Memorycore. Install the optional dependency with:

```powershell
pip install -e ".[mcp]"
```

The existing adapter is not considered validated until a real MCP client test is completed. Future supported integrations must preserve the same shared memories rather than creating provider-specific memory silos.

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

See [Design Decisions](docs/DESIGN_DECISIONS.md) and [Future Roadmap](docs/FUTURE_ROADMAP.md).