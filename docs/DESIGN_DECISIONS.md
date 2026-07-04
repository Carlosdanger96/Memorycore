# Memorycore Design Decisions

## v0.1 canonical architecture

Memorycore v0.1 is built around three components:

```text
LLM or agent
    ↓
MCP Server
    ↓
MemoryService
    ↓
SQLite + FTS5
```

`main` represents this canonical architecture. The current unfinished v1/v2 work is preserved in the `archive/pre-v0.1-experimental` branch.

## Decision: SQLite is the canonical v0.1 store

SQLite is the default durable store because it is local, portable, inspectable, easy to back up, and available through Python's built-in `sqlite3` module.

A separate SQLite server is not required. The SQLite command-line tools remain optional for manual inspection and troubleshooting.

PostgreSQL, CozoDB, vector databases, and other storage systems may be added later as optional adapters. They are not required for v0.1.

## Decision: MemoryService owns memory behavior

`MemoryService` is the only layer that controls normal memory operations. It will:

- add memories;
- retrieve a memory by ID;
- search and filter memories;
- rank search results;
- update memories;
- archive memories;
- return compact context for an LLM;
- report storage health.

Database code should not be placed in the MCP server. The SQLite adapter performs persistence, while `MemoryService` applies validation and behavior.

## Decision: MCP is an access layer

The MCP server exposes `MemoryService` to external LLMs and agents. It should translate MCP requests into service calls and return structured responses.

The initial MCP surface is limited to:

- `memory_add`
- `memory_get`
- `memory_search`
- `memory_retrieve_context`
- `memory_update`
- `memory_archive`
- `memory_health`

Additional tools should be added only after the complete persistence and restart flow works.

## Decision: FTS5 before embeddings

SQLite FTS5 is the initial retrieval system. It provides useful local full-text search without an embedding model or vector database.

Initial retrieval flow:

```text
query
→ project filter
→ active-memory filter
→ FTS5 search
→ simple ranking
→ top memories
```

Embeddings, semantic search, hybrid retrieval, reciprocal rank fusion, and model-based reranking are deferred.

## Decision: main becomes the first working version

Memorycore does not yet have a stable release worth preserving as the default implementation. The working SQLite + `MemoryService` + MCP system will therefore replace the current implementation on `main` after it passes its tests.

The first usable release will be tagged `v0.1.0`.

## v0.1 release requirements

The `v0.1.0` tag will mean:

- SQLite stores memory durably;
- memory survives a process restart;
- `MemoryService` can add, get, search, filter, rank, update, and archive memories;
- MCP exposes the supported service operations;
- project-scoped retrieval works;
- the test suite proves the complete flow;
- the README contains working setup instructions and official dependency links;
- backup and restore instructions exist;
- graph, vector, CozoDB, PostgreSQL, and learned-memory systems are not required.

## Deferred features

The following work is preserved for later phases rather than included in the v0.1 core:

- write-candidate approval workflow;
- detailed audit and policy systems;
- source and evidence graphs;
- corrections and supersession chains;
- automatic consolidation;
- contradiction and duplicate detection;
- vector embeddings and semantic search;
- graph traversal and CozoDB;
- PostgreSQL;
- multi-device synchronization;
- Obsidian and messaging integrations;
- Mojo components;
- learned-memory models.

See `docs/FUTURE_ROADMAP.md` for the longer roadmap.
