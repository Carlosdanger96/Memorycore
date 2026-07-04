# Memorycore

Memorycore is a local-first external memory layer for general LLM use. Version 0.1 uses one durable SQLite database, one `MemoryService`, and one MCP access layer.

```text
LLM or agent
    ↓
MCP server
    ↓
MemoryService
    ↓
SQLite + FTS5
```

## Status

This repository now contains the canonical v0.1 implementation. It is not a stable release until GitHub Actions and Windows MCP validation pass. The previous experimental implementation remains preserved on the `archive/pre-v0.1-experimental` branch.

## Requirements and downloads

Required:

- Python 3.11 or newer: https://www.python.org/downloads/
- Git: https://git-scm.com/downloads

Installed with Memorycore:

- MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk

Optional:

- SQLite command-line tools: https://www.sqlite.org/download.html
- uv: https://docs.astral.sh/uv/getting-started/installation/

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

## Run the MCP server

```powershell
memorycore --db .\data\memorycore.db serve
```

Or set the database path once:

```powershell
$env:MEMORYCORE_DB = "$PWD\data\memorycore.db"
memorycore-mcp
```

The stdio MCP server exposes:

- `memory_add`
- `memory_get`
- `memory_search`
- `memory_retrieve_context`
- `memory_update`
- `memory_archive`
- `memory_health`

## Python usage

```python
from memorycore import MemoryService

service = MemoryService("data/memorycore.db")
memory = service.add_memory(project_id="example", memory_type="decision",
    content="SQLite is the canonical v0.1 store.", tags=["storage"])
context = service.retrieve_context(query="canonical store", project_id="example")
print(context["context_text"])
service.close()
```

## Test

```powershell
python -m compileall src tests
pytest
```

The test suite covers SQLite CRUD, FTS5 search, project scoping, update/archive behavior, restart persistence, and the MCP adapter.

## v0.1.0 release gate

The `v0.1.0` tag should be created only after GitHub Actions passes, restart persistence is verified, an actual Windows MCP client can access the same memory, and setup instructions are confirmed.

## Deferred work

Vectors, embeddings, CozoDB, graph traversal, PostgreSQL, automatic consolidation, learned memory, multi-device sync, and advanced policy controls remain deferred. See [Design Decisions](docs/DESIGN_DECISIONS.md) and [Future Roadmap](docs/FUTURE_ROADMAP.md).
