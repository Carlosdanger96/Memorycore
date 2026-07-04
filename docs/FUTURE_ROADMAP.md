# Memorycore Future Roadmap

The first version remains intentionally small: SQLite, `MemoryService`, FTS5, CLI initialization and health checks, persistence, and tests.

Later phases may add:

1. MCP and other external access layers after the storage API is stable.
2. Write-candidate approval, provenance, corrections, supersession, audit, duplicate detection, and contradiction handling.
3. Embeddings, semantic retrieval, hybrid ranking, reranking, caching, and retrieval benchmarks.
4. Entity graphs, graph traversal, temporal links, and an optional CozoDB adapter.
5. PostgreSQL, synchronization, remote deployment, import/export, Obsidian, browser, and messaging integrations.
6. User and agent identities, scopes, policy controls, and approval interfaces.
7. Mojo components, learned-memory engines, background consolidation, and other experiments.

Future features must remain optional unless they are proven necessary, preserve inspectability and exportability, and include tests.
