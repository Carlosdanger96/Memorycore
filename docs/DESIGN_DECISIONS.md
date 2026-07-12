# Memorycore Design Decisions

## Canonical v0.1 architecture

```text
Application, script, or future integration
→ MemoryService
→ SQLite + FTS5
```

SQLite is the source of truth. `MemoryService` owns validation and memory behavior.

MCP is the shared access interface for the v0.2 prototype. It remains an
optional install dependency, but the prototype test suite validates the real
stdio protocol as well as the storage core.

## Retrieval

FTS5 is implemented before vectors or embeddings. Retrieval is project-scoped,
returns active memories by default, and ranks matching records using SQLite
BM25 followed by recency. Historical statuses require an explicit request.

## Main branch

Memorycore had no prior stable release, so the working v0.1 storage implementation becomes the canonical code on `main`. The former experimental code is preserved in `archive/pre-v0.1-experimental`.

## Release meaning

`v0.1.0` means SQLite initialization, persistence, restart recovery, service CRUD/search/archive behavior, CLI health checks, tests, Windows validation, backup/restore documentation, and clean-install instructions have been verified.

MCP validation is part of the v0.2 prototype release gate. Each client process
gets its identity and role from server configuration; MCP tool arguments cannot
override those values.
