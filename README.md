# memory.exe-core

An MCP-accessible external memory core that lets multiple LLMs read and write source-grounded, project-scoped, auditable memories through a shared backend.

## What it is
`memory.exe-core` is infrastructure, not a chatbot app. It provides shared memory APIs over MCP so different models and tools can use the same governed memory system.

## Problem
LLM memory is fragmented across sessions, tools, and vendors. Teams lose continuity, provenance, and auditability.

## Solution
A shared memory service with:
- project-scoped retrieval
- source tracking on records
- ACL/policy enforcement
- append-only audit logging

## MVP Scope (Phase 1)
The first release is intentionally narrow and defensible:
1. Run an MCP server.
2. Store memory records in durable storage.
3. Support memory search.
4. Accept memory write candidates.
5. Return project-scoped context packs.
6. Log every read/write action.
7. Enforce policy checks.

Out of scope for MVP: glyph memory, distributed agents, full Obsidian automation, and compression workers.

## MVP Tool Surface
- `memory.search`
- `memory.write_candidate`
- `memory.get_project_context`
- `memory.open_raw`
- `memory.audit`

## Architecture
MCP Gateway → Policy Layer → Memory Engine → Storage → Workers

See:
- `docs/architecture.md`
- `docs/memory-schema.md`
- `docs/mcp-tools.md`
- `docs/security-model.md`
- `docs/roadmap.md`

## Repository Layout
```text
memory.exe-core/
  docs/
  server/
  db/
  workers/
  clients/examples/
  obsidian/
  tests/
  examples/
```

## Quickstart (Local)
1. Configure runtime values in `examples/sample-config.yaml`.
2. Initialize schema from `db/schema.sql` (placeholder today).
3. Implement/start the MCP server entrypoint in `server/cmd/memory-mcp-server/`.
4. Validate tool contracts against `docs/mcp-tools.md`.

## Roadmap
- Phase 1: local MCP server + schema + search + write candidates + audit
- Phase 2: Postgres storage hardening
- Phase 3: retrieval quality and policy enforcement expansion
- Phase 4: Obsidian sync
- Phase 5: compression workers
- Phase 6: cloud deployment

## Initial Issue Backlog
1. Define memory object schema
2. Implement basic MCP server
3. Add `memory.search`
4. Add `memory.write_candidate`
5. Add local SQLite/Postgres storage
6. Add append-only audit log
7. Add project-scoped retrieval
8. Add ACL/policy checks
9. Create sample memory dataset
10. Write architecture docs
