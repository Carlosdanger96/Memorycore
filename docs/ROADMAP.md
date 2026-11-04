# Memorycore completion roadmap

Memorycore is complete when independent LLM clients can safely share one
durable memory service through a restart and recovery. The current build target
is the central service in [Central Service Architecture](CENTRAL_SERVICE_ARCHITECTURE.md):
clients use MCP; only Memorycore opens its database. This roadmap combines the
release gates in the README, [Prototype Plan](PROTOTYPE_PLAN.md), and
[SQLite Memory Design](SQLITE_MEMORY_DESIGN.md). Omni Memory integration follows
this work and is outside these gates.

## Local core

- [x] SQLite schema, migrations, provenance, lifecycle, links, and FTS5.
- [x] Project-scoped retrieval and bounded, inspectable ranking.
- [x] Transactional correction and supersession with retained history.
- [x] Online SQLite backup and complete JSONL export/import of records, events,
  and links, verified by a restart and restore test.
- [x] SQLite exact and high-overlap duplicate safeguards before activation,
  including concurrent writes and reviewer-visible candidate IDs.
- [x] Durable policy-denial and HTTP 401/403 audit without headers, tokens,
  or request content; included in JSONL recovery.
- [ ] Clean-install and migration tests on Windows and supported Python versions.

## Shared service

- [x] MCP stdio and authenticated loopback HTTP transports with server-derived
  client identity, roles, project allowlists, and pending approval.
- [ ] One central service instance owns the production database; operational
  health, restart, and recovery behavior are verified.
- [ ] PostgreSQL schema, migration, transaction, retrieval, audit, and recovery
  parity pass against a real PostgreSQL instance.
- [ ] Remote HTTPS access uses verified OAuth-derived identity and roles.
- [ ] Mistral Vibe and Hermes each use the real service to write, review,
  correct, retrieve, and inspect the same records after a restart.
- [ ] ChatGPT and other requested clients are connected and verified against
  that same service without provider-specific stores.

## Release evidence

- [ ] CI passes on Python 3.11, 3.12, and 3.13.
- [ ] A clean Windows checkout passes setup, doctor, tests, backup and restore.
- [ ] Recovery rehearsal preserves IDs, relationships, audit order, project
  boundaries, and search results.
- [ ] Release documentation matches the deployed service and its security
  boundaries; tag only after every applicable gate above passes.

As of 2026-11-03, the checkout has 29 passing local tests. The separately
installed copy has additional uncommitted capabilities and passed 51 tests
with 3 skipped. Neither result establishes the unchecked release gates.
