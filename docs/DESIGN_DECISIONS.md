# Memorycore Design Decisions

## Canonical v0.1 architecture

```text
MCP server
→ MemoryService
→ SQLite + FTS5
```

SQLite is the source of truth. `MemoryService` owns validation and memory behavior. MCP only exposes service operations and contains no SQL.

## Retrieval

FTS5 is implemented before vectors or embeddings. Retrieval is project-scoped, excludes archived memories, and ranks matching records using SQLite BM25 followed by recency.

## Main branch

Memorycore had no prior stable release, so the working v0.1 implementation becomes the canonical code on `main`. The former experimental code is preserved in `archive/pre-v0.1-experimental`.

## Release meaning

`v0.1.0` means persistence, restart recovery, service CRUD/search/archive behavior, MCP access, tests, and documentation have all been verified.
