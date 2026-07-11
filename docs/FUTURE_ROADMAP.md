# Memorycore Future Roadmap

The first version remains intentionally small: SQLite, `MemoryService`, FTS5, CLI initialization and health checks, persistence, and tests.

For a detailed project roadmap with specific milestones, timelines, and priority matrix, see [ROADMAP.md](./ROADMAP.md).

## High-Level Vision

Later phases may add:

1. **Integration Layer**: MCP and other external access layers after the storage API is stable.
2. **Memory Quality**: Write-candidate approval, provenance, corrections, supersession, audit, duplicate detection, and contradiction handling.
3. **Semantic Retrieval**: Embeddings, semantic retrieval, hybrid ranking, reranking, caching, and retrieval benchmarks.
4. **Graph Capabilities**: Entity graphs, graph traversal, temporal links, and an optional CozoDB adapter.
5. **Multi-Backend**: PostgreSQL, synchronization, remote deployment, import/export, Obsidian, browser, and messaging integrations.
6. **Access Control**: User and agent identities, scopes, policy controls, and approval interfaces.
7. **Advanced Features**: Mojo components, learned-memory engines, background consolidation, and other experiments.

## Core Principles

Future features must remain:
- **Optional**: Unless proven necessary
- **Inspectable**: Preserve transparency and debuggability
- **Exportable**: Data portability and migration support
- **Tested**: Comprehensive test coverage required

## See Also

- [ROADMAP.md](./ROADMAP.md) - Detailed project roadmap with milestones and timelines
- [DESIGN_DECISIONS.md](./DESIGN_DECISIONS.md) - Architectural decisions and rationale
