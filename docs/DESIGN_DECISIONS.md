# Memorycore Design Decisions

## Canonical v0.1 architecture

```text
Standalone application or script
→ MemoryService
→ SQLite + FTS5
```

For standalone Memorycore records, SQLite is the source of truth in the local
prototype; PostgreSQL is the planned shared-service backend. `MemoryService`
owns validation and memory behavior for those records. This decision does not
make a database copy of Omni notes authoritative.

## Omni Memory integration boundary

The installed Omni Memory system has a separate, established authority:
`C:/Users/cool-/Documents/Carlosdanger/omni-memory/` Markdown notes. When
Memorycore later serves Omni Memory, those files remain authoritative. Its
SQLite FTS/vector data is a disposable index over the notes, not a second set
of independently editable memories. Hermes and OpenClaw use one scoped access
interface. An agent's proposed change enters the existing review path; only
an approved, hash/revision-checked writer changes canonical Markdown.

```text
Hermes / OpenClaw → shared scoped access → canonical Markdown
                                      ↘ rebuildable SQLite search index
Agent proposal → review and revision check → canonical Markdown
```

Do not import Omni notes as ordinary writable `MemoryService` records or expose
an Omni write route that bypasses review. Keep stable note identity, source,
revision, status, and supersession links in Markdown or another explicitly
authoritative record before relying on them in a rebuilt index. A rebuild must
prove that current results, historical links, and provenance survive loss of
the index. Missing authoritative metadata is a migration gap, not a reason to
promote cached SQLite values to truth.

This is the target integration contract. The standalone Memorycore service and
the installed Omni adapter are not yet one verified production service.

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
