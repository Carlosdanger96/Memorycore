# Omni Memory Harness Hackathon Changes

## Implementation checklist

- [x] Record the pre-hackathon baseline and existing test result.
- [x] Add typed behavior, trajectory, correction, and audit models.
- [x] Add migration 3 without replacing existing memory storage.
- [x] Add migration 4 for immutable correction lifecycle and outcome events.
- [x] Add a read-only Python/TypeScript/config/test repository scanner.
- [x] Capture source revision and stale prior scans.
- [x] Add append-only ordered trajectory events with request idempotency.
- [x] Add deterministic error signatures and secret redaction.
- [x] Add structured correction extraction, approval, ranking, and context packs.
- [x] Add evidence-backed correction application/outcome accounting with idempotent counters.
- [x] Add deterministic and optional GPT-5.6 correction providers.
- [x] Add deterministic and optional GPT-5.6 memory audit providers.
- [x] Minimize, bound, and recursively redact live-provider payloads.
- [x] Preserve original memories and approval history during revisions.
- [x] Add role-scoped Omni MCP tools.
- [x] Add bearer-authenticated, loopback-only REST endpoints and OpenAPI output.
- [x] Add idempotent Obsidian projection and dashboard.
- [x] Project immutable correction history, successful reuse links, and reuse metrics.
- [x] Add the complete offline synthetic demo.
- [x] Add Linux/macOS and Windows one-command entrypoints.
- [x] Add unit, integration, protocol, restart, and full-demo tests.
- [x] Add hackathon evidence export.
- [x] Add Linux/Windows CI definitions for tests, demo, security, and migrations.
- [x] Add testing and three-minute demo documentation.

## New implementation areas

| Area | Files | Result |
| --- | --- | --- |
| Domain and persistence | `omni_models.py`, `database.py`, migration 4 | Typed records plus immutable correction events |
| Behavior registry | `behavior/scanner.py` | Safe AST/syntax scanning, Git ignore rules, symlink confinement, and revision evidence |
| Experience layer | `omni_service.py`, `experience/providers.py` | Trajectories, signatures, correction extraction, reuse outcomes, and ranking |
| Audit layer | `audit/providers.py`, `omni_security.py` | Deterministic/live providers with bounded redacted payloads |
| Interfaces | `mcp_server.py`, `api/omni_routes.py` | Shared MCP/REST contracts, including correction outcomes |
| Projection | `projections/obsidian.py` | Stable Markdown, lifecycle evidence, and measured reuse dashboard |
| Demonstration | `demo/synthetic-agent`, `demo/runner.py`, `scripts/demo.*` | Complete isolated vertical slice |
| Evidence and CI | `scripts/export_evidence.py`, `.github/workflows/omni-harness.yml`, documentation | Reproducible audit package and cross-platform gates |

## Verification recorded during implementation

- Baseline: 23 tests passed.
- Current suite before publication: 40 tests passed.
- Focused Omni suite: 17 tests passed.
- Offline end-to-end demo: passed; 14 generated Markdown files.
- Correction reuse: one evidence-backed use, one success, and idempotent outcome persistence.
- REST authentication: missing bearer token rejected; valid reader token accepted.
- MCP contract: Omni tools registered and role policy tested.
- Original memory preservation: tested before and after approved revision.
- Projection idempotency: second generation performs zero writes.
- Evidence export: passed with test and demo exit codes 0.
- Linux one-command entrypoint: passed with focused tests and startup commands.
- Windows workflow and PowerShell entrypoint: implemented; actual hosted Windows run remains pending.
- Optional live GPT-5.6 request: reached OpenAI but the selected Default project returned HTTP 403 because that project lacks access to `gpt-5.6`.

Commit identifiers will be supplied by the actual Git history. This document
does not fabricate commit hashes or a Codex feedback session ID.
