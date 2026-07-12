# Memorycore v0.2.0 Prototype Plan

## Sole goal

Two different LLM clients use one shared, durable memory database. A memory
written by one client is retrievable, reviewable, correctable, and preserved
for the other client after a restart.

## Non-negotiable foundation

The SQLite memory structure is a core part of Memorycore. The project cannot
defer its canonical schema, provenance, lifecycle, audit history, migrations,
recovery, or deterministic retrieval and still claim to provide shared memory.
The ten SQLite implementation steps are release-blocking requirements for the
prototype, not a later optimization track.

## Target deployment

Each local client starts its own stdio MCP process with a server-assigned
identity and role. Both processes point at the same SQLite database:

```text
Mistral Vibe MCP process ─┐
                          ├── shared SQLite + FTS5 database
Hermes MCP process ───────┘
```

Remote HTTP authentication, embeddings, vector search, graphs, PostgreSQL,
multi-device synchronization, and provider-specific stores are explicitly out
of scope until this prototype passes its cross-client test.

## Build sequence

1. **Shared MCP foundation** — server-assigned client identity and roles,
   project allowlists, active-only retrieval, lifecycle validation, and safe
   migration. This is PR #8.
2. **Audit history** — append-only, transactional write history for every
   mutation and permission denial.
3. **Correction and supersession** — atomic replacement operations that retain
   the original memory and link the complete history.
4. **Duplicate safeguards** — deterministic exact and probable duplicate
   checks within a project before a write becomes active.
5. **Recovery** — SQLite backup/restore plus inspectable JSONL export/import.
6. **Cross-client proof** — Mistral Vibe as writer and Hermes as approver use
   separate MCP processes and the same database through a restart.

The detailed local storage and retrieval decision is documented in
[SQLite Memory Design](SQLITE_MEMORY_DESIGN.md). Its ten-part checklist is the
required implementation order for the SQLite-backed prototype.

## Completion gate

Tag `v0.2.0-prototype` only when the cross-client proof shows that:

- identities and roles come from the server process, not tool arguments;
- writers cannot self-approve or access unapproved projects;
- normal retrieval returns active records only;
- every mutation has durable audit history;
- corrections and supersession are atomic and historical records remain
  inspectable;
- duplicate safeguards prevent silently competing facts;
- backup/export restores IDs, relationships, audit history, and search; and
- data remains available after a process restart.
