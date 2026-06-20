# Storage Boundaries and Responsibilities

This document defines the clear separation of concerns between different storage backends in Memorycore.

## Overview

Memorycore uses a **multi-backend architecture** where different storage systems have distinct responsibilities. This separation ensures:

- **Clear ownership**: Each backend has a well-defined purpose
- **Optimized performance**: Each storage system is used for what it does best
- **Maintainability**: Changes to one backend don't affect others
- **Testability**: Each backend can be tested in isolation

## Storage Backend Responsibilities

### 🗃️ SQLite/Postgres: Durable Record Storage

**Primary Responsibility**: Persistent, normalized storage of memory records and metadata.

**Stores**:
- Memory cards (consolidated knowledge)
- Episode records (raw task logs)
- Audit records (operation history)
- Policy/access metadata (permissions, rules)
- Project and user metadata

**Characteristics**:
- ✅ ACID compliant
- ✅ Transactional
- ✅ Queryable with SQL
- ✅ Durable and reliable
- ✅ Well-established, production-ready

**Operations**:
- CRUD operations on memory cards
- Recording and retrieving episodes
- Audit logging
- Metadata management
- Full-text search (basic)

**Python Interface**:
```python
from memorycore.storage import Storage

storage = Storage(db_path="memorycore.db")

# Memory card operations
storage.add_memory_card(card)
storage.get_memory_card(card_id)
storage.update_memory_card(card)
storage.search_memory_cards(filters)

# Episode operations
storage.record_episode(episode)
storage.get_episodes(project_id)

# Audit operations
storage.log_audit_entry(entry)
storage.get_audit_log(project_id)
```

### 🧠 CozoDB: Graph + Vector Storage

**Primary Responsibility**: Structural relationships and semantic similarity.

**Stores**:
- Graph nodes (entities: tasks, projects, files, etc.)
- Graph edges (relationships between entities)
- Vector embeddings (768-dim float32 for semantic search)
- Full-text search indexes
- HNSW vector indexes

**Characteristics**:
- ✅ Native graph operations
- ✅ Vector similarity search
- ✅ Full-text search
- ✅ Rule-based derived data
- 🧪 Experimental (as of v2)

**Operations**:
- Graph traversal (find related memories)
- Vector similarity search
- Hybrid search (vector + text)
- Nearest neighbor queries
- Graph pattern matching

**Python Interface**:
```python
# Note: CozoDB integration is currently experimental
# and accessed through the search and graph_memory modules

from memorycore.search import VectorSearch, HybridSearch
from memorycore.graph_memory import GraphMemory

# Vector search
vector_search = VectorSearch(cozo_db)
results = vector_search.search(query_embedding, limit=10)

# Graph operations
graph_memory = GraphMemory(cozo_db)
graph_memory.add_node(node)
graph_memory.add_edge(edge)
traversal = graph_memory.traverse(start_node, depth=2)
```

## Storage Adapter Interfaces

To make the storage boundaries explicit and testable, Memorycore provides abstract interfaces:

### MemoryStore Interface

```python
class MemoryStore:
    """Interface for durable memory card storage."""
    
    def add_card(self, card: MemoryCard) -> MemoryCard:
        """Add a new memory card."""
        pass
    
    def get_card(self, memory_id: str) -> Optional[MemoryCard]:
        """Get a memory card by ID."""
        pass
    
    def update_card(self, card: MemoryCard) -> MemoryCard:
        """Update an existing memory card."""
        pass
    
    def search_cards(
        self, 
        project_id: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
        status: Optional[MemoryStatus] = None,
        tags: Optional[List[str]] = None,
        query: Optional[str] = None,
        limit: int = 100
    ) -> List[MemoryCard]:
        """Search memory cards with filters."""
        pass
    
    def delete_card(self, memory_id: str) -> bool:
        """Mark a memory card as deleted (soft delete)."""
        pass
```

### GraphStore Interface

```python
class GraphStore:
    """Interface for graph-based memory storage."""
    
    def add_node(self, node: GraphNode) -> GraphNode:
        """Add a node to the graph."""
        pass
    
    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Get a node by ID."""
        pass
    
    def add_edge(self, edge: GraphEdge) -> GraphEdge:
        """Add an edge between nodes."""
        pass
    
    def get_edges(
        self, 
        from_node_id: Optional[str] = None,
        to_node_id: Optional[str] = None,
        edge_type: Optional[GraphEdgeType] = None
    ) -> List[GraphEdge]:
        """Get edges with optional filters."""
        pass
    
    def traverse(
        self, 
        start_node_id: str, 
        depth: int = 1,
        edge_types: Optional[List[GraphEdgeType]] = None
    ) -> GraphTraversalResult:
        """Traverse the graph from a starting node."""
        pass
```

### VectorStore Interface

```python
class VectorStore:
    """Interface for vector-based similarity search."""
    
    def upsert_embedding(
        self, 
        memory_id: str, 
        embedding: List[float],
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Upsert a vector embedding for a memory."""
        pass
    
    def search(
        self, 
        query_embedding: List[float],
        limit: int = 10,
        min_score: Optional[float] = None,
        filter_project_id: Optional[str] = None,
        filter_tags: Optional[List[str]] = None
    ) -> List[VectorSearchResult]:
        """Search for similar embeddings."""
        pass
    
    def delete_embedding(self, memory_id: str) -> bool:
        """Remove a vector embedding."""
        pass
```

## Implementation Status

| Interface | SQLite | Postgres | CozoDB | Status |
|-----------|--------|----------|--------|--------|
| MemoryStore | ✅ | ✅ | ❌ | Stable |
| GraphStore | ❌ | ❌ | ✅ | Experimental |
| VectorStore | ❌ | ❌ | ✅ | Experimental |

## Migration Path

The current implementation uses direct database access in the storage modules. The plan is to:

1. **Phase 1 (Current)**: Direct database access with clear separation
2. **Phase 2**: Introduce adapter interfaces as shown above
3. **Phase 3**: Implement multiple backends for each interface
4. **Phase 4**: Add backend selection and failover logic

## Testing Strategy

Each storage backend should be tested independently:

```python
# Test MemoryStore implementations
def test_memory_store_crud():
    store = SQLiteMemoryStore(":memory:")
    # Test CRUD operations
    
# Test GraphStore implementations  
def test_graph_store_traversal():
    store = CozoGraphStore(":memory:")
    # Test graph operations
    
# Test VectorStore implementations
def test_vector_store_search():
    store = CozoVectorStore(":memory:")
    # Test vector operations
```

## Integration Points

The Memory Engine v2 coordinates between different storage backends:

```python
class MemoryEngineV2:
    def __init__(
        self,
        memory_store: MemoryStore,
        graph_store: Optional[GraphStore] = None,
        vector_store: Optional[VectorStore] = None,
        audit_logger: Optional[AuditLogger] = None
    ):
        self.memory_store = memory_store
        self.graph_store = graph_store
        self.vector_store = vector_store
        self.audit_logger = audit_logger
    
    def retrieve_context(self, query: str, project_id: str) -> ContextResult:
        # Use memory_store for basic filtering
        candidates = self.memory_store.search_cards(
            project_id=project_id, 
            query=query
        )
        
        # Use vector_store for semantic similarity (if available)
        if self.vector_store:
            vector_results = self.vector_store.search(query_embedding, limit=10)
            candidates.extend(vector_results)
        
        # Use graph_store for structural relationships (if available)
        if self.graph_store:
            graph_results = self.graph_store.traverse(start_node, depth=2)
            # Combine results
        
        return ContextResult(results=candidates, graph=graph_results)
```

## Future Enhancements

- **Unified Query Interface**: Single query language that can target any backend
- **Caching Layer**: In-memory caching for frequently accessed data
- **Sync Layer**: Cross-backend synchronization for hybrid setups
- **Monitoring**: Performance metrics and health checks for each backend
