# Memorycore

**Status: Active prototype / v2 foundation**

Memorycore is a **portable external memory layer for any LLM, agent, CLI, or tool-connected system**. Its purpose is to give different models and tools access to the same structured memory store through a controlled interface, instead of relying only on chat history, hidden app memory, or one model's local context.

## What is Memorycore?

Memorycore provides a durable, shareable memory infrastructure that enables:

- **Cross-agent memory**: Multiple agents can access and contribute to the same memory store
- **Structured memory**: Organized by types (episodic, semantic, procedural, decision, etc.)
- **Graph relationships**: Structural connections between memories, tasks, and entities
- **Vector search**: Semantic similarity search using HNSW indexes
- **Full-text search**: Traditional text-based retrieval
- **Audit trail**: Comprehensive logging of all memory operations
- **Consolidation**: Transforming raw task logs into durable memory cards

## What is NOT Memorycore?

Memorycore is **not**:
- A model training framework
- An autonomous agent orchestration system
- A replacement for chat history or context windows
- A proprietary memory system tied to specific agents
- A database management system (it uses existing databases)

## Quickstart

### Installation

```bash
# Install the package in development mode
pip install -e ".[dev,test]"

# Or install with specific extras
pip install -e ".[postgres,cozo]"
```

### Running the MCP Server

```bash
# Run the MCP server (v2)
python -m memorycore.mcp_server_v2 --db-path memorycore.cozo --schema-path cozodb/schema.cozo

# Or use the entry point (after installation)
memorycore-mcp --db-path memorycore.cozo --schema-path cozodb/schema.cozo
```

### Storing One Memory

```python
from memorycore.memory_engine_v2 import create_memory_engine_v2
from memorycore.memory_types import MemoryCard, MemoryType, MemoryStatus

# Create the engine
engine = create_memory_engine_v2()

# Add a memory card
card = MemoryCard(
    memory_id="test-memory-001",
    project_id="my-project",
    content="The database schema uses CozoDB for vector search capabilities.",
    memory_type=MemoryType.SEMANTIC,
    status=MemoryStatus.ACTIVE,
    confidence=0.95,
    trust_score=0.9,
    tags=["database", "cozodb", "vector-search"],
    summary="Database uses CozoDB for vector search"
)

engine.add_card(card)
```

### Retrieving Context

```python
# Retrieve context for a specific query
context = engine.retrieve_context(
    project_id="my-project",
    query="database schema",
    memory_types=[MemoryType.SEMANTIC, MemoryType.PROCEDURAL],
    limit=10
)

print(f"Found {len(context.results)} relevant memories")
for result in context.results:
    print(f"- {result.memory_id}: {result.summary}")
```

## Storage Backends Supported Today

| Backend | Status | Purpose |
|---------|--------|---------|
| **SQLite** | ✅ Stable | Memory cards, episodes, audit records, metadata |
| **Postgres** | ✅ Stable | Production-ready relational storage |
| **CozoDB** | 🧪 Experimental | Graph nodes/edges, vector index, structural retrieval |

## MCP Tools Available

Memorycore v2 exposes **14 MCP tools** organized into categories:

### Memory Operations
- `memory.record_episode` - Record raw task logs
- `memory.add_card` - Add consolidated memory cards
- `memory.retrieve_context` - Get comprehensive context (graph + vector + text)
- `memory.supersede` - Create supersession relationships
- `memory.audit` - Get audit logs
- `memory.search` - Search memory cards
- `memory.consolidate_episode` - Consolidate specific episode
- `memory.consolidate_project` - Consolidate all episodes for project

### Graph Operations
- `graph.add_node` - Add graph nodes
- `graph.add_edge` - Add graph edges
- `graph.traverse` - Traverse the graph
- `graph.get_summary` - Get graph summary

### System Operations
- `system.health_check` - Check system health
- `system.get_config` - Get configuration

## Architecture Overview

```
LLM / Agent / Tool Client
        ↓
    MCP Interface
        ↓
    Memory Engine v2
        ↓
┌─────────────────────────┐
│   Storage Layer          │
│  ┌─────────────────────┐│
│  │ SQLite/Postgres     ││ ← Memory cards, episodes, audit
│  └─────────────────────┘│
│  ┌─────────────────────┐│
│  │ CozoDB             ││ ← Graph, vectors, structural retrieval
│  └─────────────────────┘│
└─────────────────────────┘
```

## Current Status

### ✅ Stable Today
- Memory card types and data structures
- Episode records and audit logging
- SQLite/Postgres-oriented storage
- MCP v2 tool surface (14 tools)
- Basic memory operations (add, search, retrieve)

### 🧪 Experimental
- CozoDB graph/vector schema
- Automatic consolidation
- HNSW retrieval
- Cross-agent policy enforcement
- Hybrid search (vector + FTS)

## Project Structure

```
memorycore/
├── __init__.py           # Package exports
├── memory_types.py       # Memory data structures
├── memory_engine.py      # Legacy memory engine
├── memory_engine_v2.py   # New memory engine
├── graph_memory.py       # Graph memory layer
├── consolidator.py       # Consolidation engine
├── storage.py            # Storage backends
├── search.py             # Search functionality
├── embedding.py          # Embedding generation
├── audit.py              # Audit logging
├── audit_jsonl.py        # JSONL audit logging
├── policy.py             # Policy enforcement
├── ranking.py            # Result ranking
├── controller.py         # Legacy controller
├── mcp_server.py         # Legacy MCP server
├── mcp_server_v2.py      # New MCP server
└── cmd/                  # Command-line tools
    └── memory-mcp-server/
        └── main.py       # Legacy CLI entry point

cozodb/
└── schema.cozo           # CozoDB schema

docs/
├── ARCHITECTURE_V2.md    # Architecture documentation
└── memory-schema.md      # Memory schema documentation

tests/
├── test_imports.py       # Import tests
├── test_cozo_schema.py   # Cozo schema tests
└── ...                  # Other tests

.github/
└── workflows/
    └── tests.yml         # CI configuration
```

## Design Principles

1. **No Silent Deletion**: Memory is never deleted, only marked with status
2. **Graph + Vector**: Both structural and semantic retrieval are supported
3. **Memory Types**: Explicit typing enables different retrieval strategies
4. **Consolidation**: Raw logs are evidence, not memory - consolidation transforms evidence into durable memory
5. **Minimal API First**: Start small with core operations, expand based on real usage
6. **Open and Inspectable**: All memory should be queryable, all operations auditable
7. **Local-First**: Default to local storage, with optional cloud sync
8. **Cross-Agent**: Designed for multiple agents, not tied to any specific framework

## Known Limitations

- CozoDB integration is experimental and requires separate installation
- Vector search requires numpy and embedding models
- Some features are only available in v2 (memory_engine_v2.py)
- Legacy v1 code (memory_engine.py, mcp_server.py) is maintained for compatibility
- Performance optimization for large memory stores is ongoing

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest -q`
5. Submit a pull request

## License

MIT License - see LICENSE file for details.
