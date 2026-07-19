# Omni Memory Harness Hackathon Changes

## Implementation checklist

- [x] Record the pre-hackathon baseline and existing test result.
- [x] Add typed behavior, trajectory, correction, and audit models.
- [x] Add migration 3 without replacing existing memory storage.
- [x] Add a read-only Python/TypeScript/config/test repository scanner.
- [x] Capture source revision and stale prior scans.
- [x] Add append-only ordered trajectory events with request idempotency.
- [x] Add deterministic error signatures and secret redaction.
- [x] Add structured correction extraction, approval, ranking, and context packs.
- [x] Add deterministic and optional GPT-5.6 correction providers.
- [x] Add deterministic and optional GPT-5.6 memory audit providers.
- [x] Preserve original memories and approval history during revisions.
- [x] Add role-scoped Omni MCP tools.
- [x] Add bearer-authenticated, loopback-only REST endpoints and OpenAPI output.
- [x] Add idempotent Obsidian projection and dashboard.
- [x] Add the complete offline synthetic demo.
- [x] Add Linux/macOS and Windows one-command entrypoints.
- [x] Add unit, integration, protocol, restart, and full-demo tests.
- [x] Add hackathon evidence export.
- [x] Add testing and three-minute demo documentation.

## New implementation areas

| Area | Files | Result |
| --- | --- | --- |
| Domain and persistence | `omni_models.py`, `database.py` | Typed records plus SQLite migration 3 |
| Behavior registry | `behavior/scanner.py` | Safe AST/syntax scanning and revision evidence |
| Experience layer | `omni_service.py`, `experience/providers.py` | Trajectories, error signatures, correction extraction and ranking |
| Audit layer | `audit/providers.py` | Deterministic and GPT-5.6 structured-output providers |
| Interfaces | `mcp_server.py`, `api/omni_routes.py` | Shared service-backed MCP and REST contracts |
| Projection | `projections/obsidian.py` | Stable Obsidian Markdown and dashboard |
| Demonstration | `demo/synthetic-agent`, `demo/runner.py`, `scripts/demo.*` | Complete isolated vertical slice |
| Evidence | `scripts/export_evidence.py`, documentation | Reproducible audit package |

## Verification recorded during implementation

- Baseline: 23 tests passed.
- Current suite before publication: 35 tests passed.
- Offline end-to-end demo: passed; 14 generated Markdown files.
- REST authentication: missing bearer token rejected; valid reader token accepted.
- MCP contract: Omni tools registered and role policy tested.
- Original memory preservation: tested before and after approved revision.
- Projection idempotency: second generation performs zero writes.
- Optional live GPT-5.6 request: reached OpenAI but the selected Default project returned HTTP 403 because that project lacks access to `gpt-5.6`.

Commit identifiers will be supplied by the actual Git history. This document
does not fabricate commit hashes or a Codex feedback session ID.
