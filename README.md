# Memorycore

Memorycore is a local-first external memory layer for general LLM use. It gives different models, agents, CLIs, and applications access to the same durable memory without tying the memory to one provider or one chat interface.

## Current status

Memorycore is being simplified into its first working version. The canonical v0.1 architecture is:

```text
LLM or agent
    ↓
MCP Server
    ↓
MemoryService
    ↓
SQLite + FTS5
```

The current repository still contains unfinished v1/v2 experimental code. That code is not yet the supported runtime. The preserved experimental snapshot is available in the `archive/pre-v0.1-experimental` branch.

`main` is now the target for the working SQLite + `MemoryService` + MCP implementation.

## The actual core

### SQLite

SQLite stores memory durably. It is the canonical local store for v0.1.

Memorycore will use Python's built-in `sqlite3` module, so a separate SQLite server is not required.

### MemoryService

`MemoryService` owns normal memory behavior:

- add a memory;
- retrieve a memory by ID;
- search and filter memories;
- rank search results;
- return compact context for an LLM;
- update a memory;
- archive a memory;
- report storage health.

### MCP server

The MCP server exposes `MemoryService` to LLMs and agents. It should contain no direct SQL or independent memory logic.

Initial MCP tools:

- `memory_add`
- `memory_get`
- `memory_search`
- `memory_retrieve_context`
- `memory_update`
- `memory_archive`
- `memory_health`

## v0.1 completion standard

The first usable release will be tagged `v0.1.0` when all of the following work:

1. SQLite stores memory.
2. Memory survives a process restart.
3. `MemoryService` can add, get, search, filter, rank, update, and archive memory.
4. MCP exposes those operations.
5. Project-scoped retrieval works.
6. The test suite proves the full persistence and MCP flow.
7. Installation, backup, restore, and troubleshooting instructions are accurate.

Required proof flow:

```text
create database
→ start Memorycore
→ add memory through the service or MCP
→ retrieve memory
→ stop Memorycore
→ restart Memorycore
→ retrieve the same memory again
```

## Requirements and downloads

### Required

- Python 3.11 or newer  
  https://www.python.org/downloads/

- Git  
  https://git-scm.com/downloads

### Installed with Memorycore

- Model Context Protocol Python SDK  
  https://github.com/modelcontextprotocol/python-sdk

The MCP SDK should be installed through the project's Python dependencies rather than downloaded manually.

### Optional

- SQLite command-line tools  
  https://www.sqlite.org/download.html

  Python already includes SQLite access through `sqlite3`. The command-line tools are only needed for manual database inspection or repair.

- uv package manager  
  https://docs.astral.sh/uv/getting-started/installation/

  `uv` is optional. Standard Python virtual environments and `pip` remain supported.

## Verify local requirements

```bash
python --version
git --version
python -c "import sqlite3; print(sqlite3.sqlite_version)"
```

## Planned project structure

```text
Memorycore/
├── pyproject.toml
├── src/
│   └── memorycore/
│       ├── __init__.py
│       ├── models.py
│       ├── database.py
│       ├── memory_service.py
│       ├── retrieval.py
│       ├── mcp_server.py
│       └── cli.py
├── migrations/
│   └── 001_initial.sql
├── tests/
│   ├── test_database.py
│   ├── test_memory_service.py
│   ├── test_retrieval.py
│   ├── test_persistence.py
│   └── test_mcp.py
└── docs/
    ├── DESIGN_DECISIONS.md
    └── FUTURE_ROADMAP.md
```

This structure describes the implementation target. Some files do not exist yet.

## Initial memory model

```text
Memory
├── id
├── project_id
├── memory_type
├── content
├── summary
├── tags
├── status
├── created_by
├── metadata
├── created_at
└── updated_at
```

Initial memory types:

- `fact`
- `decision`
- `preference`
- `procedure`
- `correction`
- `note`

Initial statuses:

- `active`
- `archived`
- `superseded`

## Initial retrieval

```text
query
→ restrict to project_id
→ restrict to active memories
→ search SQLite FTS5
→ rank results
→ return the best memories
```

No embedding model or vector database is required for v0.1.

## Deferred work

The following ideas remain part of Memorycore's longer-term direction, but they are not part of the first working core:

- write-candidate approval;
- detailed audit and permissions;
- source and evidence graphs;
- automatic consolidation;
- contradiction and duplicate detection;
- embeddings and semantic retrieval;
- graph traversal and CozoDB;
- PostgreSQL;
- multi-device synchronization;
- Obsidian, browser, and messaging integrations;
- Mojo components;
- learned-memory models.

See [Design Decisions](docs/DESIGN_DECISIONS.md) and the [Future Roadmap](docs/FUTURE_ROADMAP.md).

## Development workflow

The active implementation can be built and tested on a temporary feature branch, then merged into `main` after the complete persistence and MCP tests pass.

The resulting working implementation becomes the canonical version on `main`; it is not intended to remain as a permanent alternate branch.
