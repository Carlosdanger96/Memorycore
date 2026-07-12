# SQLite Memory Design

## Core product invariant

This design is required for Memorycore to function. A shared-memory product
without durable records, source attribution, controlled corrections, audit
history, recovery, and deterministic retrieval will eventually give connected
LLMs incompatible or untrustworthy memory. The schema and operating rules below
are therefore release-blocking core functionality.

## Decision

SQLite remains the local Memorycore backend for the prototype. It is owned by
one central Memorycore service process on one host; LLM clients use MCP and do
not open or modify the database file directly. PostgreSQL is the later storage
adapter for multi-machine service deployment.

## Storage model

The `memories` table contains the current canonical record and its provenance.
The following supporting tables complete the shared-memory model:

| Table | Responsibility |
| --- | --- |
| `memories` | Current memory content, status, provenance, timestamps, and confidence. |
| `memory_links` | `supersedes`, `corrects`, and `contradicts` relationships. |
| `memory_events` | Immutable audit events for every mutation and denied action. |
| `memory_tags` | Searchable, normalized tags. |
| `schema_migrations` | Applied migration version, checksum, and timestamp. |
| `memory_fts` | FTS5 index for content, summary, and tag text. |

`metadata` stays JSON for non-critical optional information. Any field used for
filtering, joins, authorization, or retrieval ranking belongs in a real column
or normalized table.

## Integrity and lifecycle

- Enable foreign keys on every SQLite connection.
- Use foreign keys from links and events to memories.
- Create correction and supersession as a single transaction: create the
  replacement, create the link, transition the original, append audit events,
  then commit.
- Use controlled lifecycle transitions only; normal retrieval returns active
  memories only.
- Keep audit history append-only. A correction preserves the original record.

## Retrieval

1. Scope every query to a project.
2. Filter to `active` unless a caller explicitly requests history.
3. Check exact normalized content first.
4. Query FTS5 across content, summary, and tags.
5. Rank decisions, corrections, and preferences above generic notes.
6. Use confidence and recency only as tie-breakers.
7. Return a small bounded context set.

Memorycore returns an inspectable `retrieval` list beside context output. Each
entry records the memory ID, deterministic score, and reasons such as an exact
content match, matching terms or tags, memory type, and confidence. No hidden
embedding or LLM ranking is used in the prototype.

FTS5 remains an ordinary synchronized index for the prototype. Do not switch to
external-content or embedding search until this deterministic path is measured
and proven insufficient.

## Operations and recovery

- Use WAL, a bounded busy timeout, and short write transactions.
- Keep the live SQLite database on the same host as Memorycore; do not put it
  on synced or network filesystems.
- Run schema migrations through a version/checksum migration table.
- Back up using SQLite's online backup API or `VACUUM INTO`; never copy an open
  database file by itself.
- Use partial indexes for active-memory retrieval and add indexes only after
  inspecting actual query plans.

## Ten-part implementation checklist

1. Add `migrations/002_audit_and_links.sql`.
2. Add `schema_migrations` plus a transactional migration runner.
3. Add append-only `memory_events` and transaction helpers.
4. Add `memory_links` and atomic `memory_supersede` / `memory_correct`.
5. Add `memory_tags` and active-memory partial indexes.
6. Add exact normalized duplicate detection before an active write.
7. Add online backup, restore, JSONL export, and JSONL import.
8. Add deterministic retrieval ranking and query-plan tests.
9. Run a Mistral Vibe ↔ Hermes central-service workflow against one database.
10. Add PostgreSQL parity and remote OAuth only after the local prototype
    passes all prior steps.
