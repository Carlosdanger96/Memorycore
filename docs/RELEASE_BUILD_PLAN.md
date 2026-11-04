# Memorycore release build plan

Complete the standalone shared service before changing Omni Memory. All probes
use disposable databases and credentials; installed services and the canonical
Omni vault remain outside the test fixtures.

## 1. Clean install and migrations

- [x] Preserve records, provenance, links, audit order, and search when a legacy
  SQLite schema is upgraded; reject unknown migration checksums.
- [x] Apply PostgreSQL schema migrations with stable checksums and test restart
  and upgrade against a disposable server.
- [x] Run setup, doctor, and tests from a clean Windows checkout on every
  supported Python version available locally or in CI.

## 2. Central service ownership and recovery

- [x] Give the central service a readiness probe and a single-owner startup
  check for its database target.
- [x] Exercise authenticated MCP through restart, online backup, and restore;
  compare records and search after recovery.
- [x] Document startup, shutdown, backup, rollback, and expected failures.

## 3. PostgreSQL parity

- [x] Test schema, migration, lifecycle, retrieval, duplicate handling, audit,
  concurrency, export, and restore against a real disposable PostgreSQL server.
- [x] Make the parity suite mandatory in CI and retain failure diagnostics.

## 4. Remote HTTPS identity

- [x] Add an OAuth/JWT verifier that derives client identity and role from a
  configured issuer and verified token claims, with fail-closed audience,
  expiry, issuer, and scope checks.
- [x] Keep token material outside the repository and deny startup when the
  external endpoint is not protected by HTTPS.
- [x] Test valid and forged/expired/wrong-audience tokens through HTTP MCP.

## 5. Real clients

- [ ] Configure Mistral Vibe and Hermes for the same central endpoint with
  separate identities; prove write, review, correction, retrieval, and history
  through both real clients after restart.
- [ ] Connect ChatGPT and each additional requested client to that endpoint;
  verify tool discovery and a scoped read, without provider-specific stores.

## 6. Release evidence

- [ ] Pass CI on Python 3.11, 3.12, and 3.13 and a clean Windows checkout.
- [x] Rehearse loss and restore of a disposable database, comparing IDs, links,
  audit order, project boundaries, and search results.
- [ ] Match deployment docs to the tested build; only then mark the roadmap
  complete and tag a release.

External client sign-in, public HTTPS hosting, and ChatGPT connector selection
require the owner's environment. These gates remain open until observed there.

Local evidence on 2026-11-03: a clean Windows checkout passed setup, doctor,
and 49 tests on Python 3.11, 3.12, and 3.13 with disposable PostgreSQL. The
later checkout includes a restarted authenticated HTTP workflow and a
standalone recovery rehearsal. An isolated Vibe instance reached MCP tool
discovery, then rejected the configured Mistral API key before a model call.
