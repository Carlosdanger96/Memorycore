# Memorycore

Memorycore is a local-first external memory layer for general LLM use. Version 0.1 focuses on one durable SQLite database and one `MemoryService`.

```text
Application, script, or future integration
    ↓
MemoryService
    ↓
SQLite + FTS5
```

MCP is deferred to a later integration phase. The current MCP adapter remains in the repository as optional work, but it is not required to install, initialize, test, or use the storage core.

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
)
context = service.retrieve_context(
    query="canonical store",
    project_id="example",
)
print(context["context_text"])
service.close()
```

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

## Deferred work

MCP integration, vectors, embeddings, CozoDB, graph traversal, PostgreSQL, automatic consolidation, learned memory, multi-device sync, and advanced policy controls remain deferred. See [Design Decisions](docs/DESIGN_DECISIONS.md) and [Future Roadmap](docs/FUTURE_ROADMAP.md).
