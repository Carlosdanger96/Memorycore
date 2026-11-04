# Memorycore completion roadmap

Memorycore is complete when independent LLM clients can safely share one
durable memory service through a restart and recovery. The current build target
is the central service in [Central Service Architecture](CENTRAL_SERVICE_ARCHITECTURE.md):
clients use MCP; only Memorycore opens its database. This roadmap combines the
release gates in the README, [Prototype Plan](PROTOTYPE_PLAN.md), and
[SQLite Memory Design](SQLITE_MEMORY_DESIGN.md). The standalone database is
authoritative for standalone Memorycore records. Omni Memory's Markdown vault
remains authoritative for Omni notes; its SQLite search data is rebuildable.
The boundary is specified in [Design Decisions](DESIGN_DECISIONS.md). Omni
integration follows completion of the Memorycore gates below.

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
- [x] Clean-install and migration tests on Windows and supported Python versions.

## Shared service

- [x] MCP stdio and authenticated loopback HTTP transports with server-derived
  client identity, roles, project allowlists, and pending approval.
- [ ] One central service instance owns the production database; operational
  health, restart, and recovery behavior are verified.
- [x] PostgreSQL schema, migration, transaction, retrieval, audit, and recovery
  parity pass against a real PostgreSQL instance.
- [ ] Remote HTTPS access uses verified OAuth-derived identity and roles.
- [ ] Mistral Vibe and Hermes each use the real service to write, review,
  correct, retrieve, and inspect the same records after a restart.
- [ ] ChatGPT and other requested clients are connected and verified against
  that same service without provider-specific stores.

## Release evidence

- [ ] CI passes on Python 3.11, 3.12, and 3.13.
- [ ] A clean Windows checkout passes setup, doctor, tests, backup and restore.
- [x] Recovery rehearsal preserves IDs, relationships, audit order, project
  boundaries, and search results.
- [ ] Release documentation matches the deployed service and its security
  boundaries; tag only after every applicable gate above passes.

## Gate before Omni integration

After the Memorycore gates above pass, verify the existing Omni adapter against
the integration contract before changing client wiring:

- [ ] One scoped retrieval interface returns canonical path/ID, source,
  revision/hash, status, and explicit current or historical results.
- [ ] Conflicting sources and stale imports cannot override a later reviewed
  user correction; unresolved changes stay in review.
- [ ] Every agent write route proposes a change to the existing review path;
  approval compares the candidate and destination revisions before writing.
- [ ] A disposable reviewed note is retrieved through both Hermes and
  OpenClaw's real client paths after a restart.
- [ ] Delete and rebuild a disposable SQLite index from Markdown and other
  authoritative records; verify identity, provenance, status, relationships,
  and current search results. Identify missing metadata before migration.
- [ ] Measure optional CPU semantic search against lexical search on fixed
  queries, including recall, abstention, latency, and memory use.

The separately installed copy has additional uncommitted capabilities. A test
count alone does not establish the unchecked release gates above.
