# Memorycore Future Roadmap

Memorycore is an omni-memory system. The first version remains intentionally small—SQLite, `MemoryService`, FTS5, CLI initialization and health checks, persistence, and tests—but each phase should move toward one shared memory substrate usable by many LLMs and applications.

## Phase 0: stable storage foundation

- Verify SQLite initialization, persistence, restart recovery, CRUD, search, update, and archive behavior.
- Pass CI on supported Python versions and operating systems.
- Add safe backup and restore procedures.
- Confirm setup from a clean Windows checkout.
- Keep the core free of provider SDKs and model-specific application logic.

## Phase 1: trustworthy shared memory

- Add explicit provenance fields and source references.
- Add candidate-write and approval states.
- Add corrections and linked supersession.
- Add audit history and duplicate detection.
- Add contradiction recording and resolution without silently overwriting evidence.
- Add import and export of readable canonical records.

## Phase 2: omni-memory scopes and access

- Add user, workspace, project, session, topic, visibility, and permission scopes.
- Add user and client identities without making provider identity the primary namespace.
- Stabilize the provider-neutral service API.
- Add optional MCP and HTTP adapters.
- Add thin integrations for Hermes, Codex, Mistral Vibe, browser workflows, messaging workflows, and other clients.

All adapters must read and write the same canonical memory model. They must not create separate provider-specific cores.

## Phase 3: stronger retrieval

- Add embeddings and semantic retrieval as optional indexes.
- Add hybrid lexical and semantic ranking.
- Add reranking, caching, and retrieval benchmarks.
- Add context budgeting and explainable retrieval results.
- Preserve FTS and readable records as dependable fallbacks.

## Phase 4: relationships and consolidation

- Add entity and relationship links.
- Add temporal links and graph traversal.
- Evaluate an optional CozoDB or other graph adapter only after the SQLite core is stable.
- Add evidence-preserving consolidation and duplicate merging.
- Keep automatic consolidation reversible and auditable.

## Phase 5: deployment and synchronization

- Add PostgreSQL or another remote backend through a stable storage interface.
- Add multi-device synchronization and conflict handling.
- Add remote deployment and backup policies.
- Add Obsidian, browser, Signal, and messaging integrations as optional adapters.

## Experimental work

Mojo components, learned-memory engines, model-based consolidation, graph engines, and other research may live in clearly marked experimental branches or directories.

Experimental work may graduate only when it:

1. solves a demonstrated problem;
2. has a small working implementation;
3. includes tests and evaluation;
4. documents failure cases;
5. preserves inspectability, provenance, exportability, and auditability;
6. does not replace readable canonical memory with an opaque derived representation;
7. remains optional unless proven necessary.
