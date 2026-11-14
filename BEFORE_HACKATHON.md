# Pre-Hackathon Memorycore Baseline

Baseline tag: `hackathon-baseline-2026-07-19`

Baseline commit: `cd42c5e`

Baseline verification on 2026-07-19:

```text
23 passed in 2.73s
```

## Pre-existing capabilities

- Canonical SQLite memory storage with FTS5 retrieval.
- `MemoryService` validation and persistence boundary.
- Memory provenance fields and immutable memory audit events.
- Pending, active, rejected, archived, superseded, and contradicted lifecycle states.
- Atomic correction and supersession with links to preserved original records.
- Reader, writer, approver, and administrator roles.
- Project allowlists and approval-gated MCP writes.
- Bearer-authenticated Streamable HTTP MCP transport, bound to loopback by default.
- SQLite backup and JSONL import/export.
- Optional PostgreSQL adapter.
- Twelve existing Memorycore MCP tools.
- Mistral Vibe and Hermes cross-client integration tests.

## Explicitly absent at baseline

- Behavior-to-code scanning.
- Agent trajectory capture.
- Experience correction extraction and retrieval.
- GPT-5.6 memory auditing.
- Audit finding review records.
- Obsidian Harness projection.
- Omni REST endpoints and MCP tools.
- One-command failed-run-to-corrected-run demonstration.

This file documents existing work only. It does not claim any Omni Memory
Harness component as pre-hackathon functionality.
