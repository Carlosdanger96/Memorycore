# Memorycore Future Roadmap

Memorycore v0.1 is intentionally limited to three working components:

1. SQLite stores durable memory.
2. `MemoryService` writes, reads, filters, updates, and ranks memory.
3. An MCP server exposes `MemoryService` to LLMs and agents.

The immediate goal is a persistent, local-first memory system that can add a memory, retrieve it, restart, and retrieve the same memory again through MCP.

The features below are deliberately deferred. They are not rejected; they should be added only after the core storage, retrieval, and MCP path is reliable and tested.

## Phase 1: Working core

- Canonical memory model
- SQLite database and migrations
- SQLite FTS5 search
- `MemoryService`
- MCP tools for add, get, search, retrieve, update, archive, and health
- Project-scoped retrieval
- Restart-persistence tests
- Installation, doctor, backup, and restore instructions

## Phase 2: Memory management

- Write-candidate approval workflow
- Human or trusted-agent approval and rejection
- Source and evidence links
- Corrections and supersession chains
- Duplicate detection
- Contradiction detection
- Confidence and trust scoring
- Memory expiration and stale-memory handling
- Retrieval and write audit logs

## Phase 3: Retrieval improvements

- Vector embeddings
- Semantic retrieval
- Hybrid FTS and vector ranking
- Reciprocal rank fusion
- Reranking models
- Retrieval caching
- Retrieval evaluation datasets and benchmarks

## Phase 4: Graph memory

- Entities and relationships
- Persistent graph indexes
- Graph traversal
- Temporal relationships
- Cross-project links
- CozoDB adapter or another graph backend

## Phase 5: Storage and synchronization

- PostgreSQL adapter
- Multiple storage adapters
- Multi-device synchronization
- Remote server deployment
- JSONL and Markdown import/export
- Obsidian integration
- Browser and messaging integrations

## Phase 6: Access and governance

- User and agent identities
- Project-level permissions
- Read and write scopes
- Policy engine
- Detailed audit controls
- Human approval interfaces

## Phase 7: Performance and experimental systems

- Mojo ranking or indexing components
- Batch ingestion
- Background consolidation
- Learned-memory models
- MeMo-style semantic memory
- Lisp or MojoLisp control layers
- Nano-LLM memory workers
- Agent-specific adapters
- Swarm and blackboard coordination experiments
- Glyph compression experiments

## Rule for adding future features

A feature should move into the active core only when:

- the existing SQLite + `MemoryService` + MCP path remains working;
- the feature has a clear interface and test coverage;
- it does not become a required dependency for normal local use unless there is a strong reason;
- it preserves inspectability, exportability, and auditability;
- documentation distinguishes stable behavior from experimental behavior.
