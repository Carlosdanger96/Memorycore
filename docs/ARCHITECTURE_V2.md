# Memorycore v2 Architecture

## Vision

Memorycore should be the **shared memory operating layer for agents**, not just a note store. It should enable cross-agent memory infrastructure that is open, inspectable, local-first, and usable by multiple agents (Hermes, Codex, Vibe CLI, Agent Radio, research agents, browser/Signal workflows).

## Core Principle

**Memorycore stores agent experience, not just knowledge.**

Every durable memory should answer one of these:
- What did the agent do?
- What worked?
- What failed?
- What correction was made?
- What should the agent do differently next time?
- What source or log proves this?

This makes Memorycore more than RAG. It becomes the system that lets agents improve across sessions.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    AGENT LAYER                                   │
│  Hermes / Codex / Vibe CLI / Agent Radio / Research Agents     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    MCP API LAYER                                │
│  memory.record_episode()  memory.add_card()  memory.retrieve() │
│  memory.supersede()      memory.audit()    memory.search()    │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    MEMORY ENGINE                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ Episode     │  │ Memory      │  │ Retrieval               │ │
│  │ Store       │  │ Card        │  │ Engine                 │ │
│  │             │  │ Consolidator│  │ (Vector + Graph)        │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    STORAGE LAYER                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ Graph       │  │ Vector      │  │ Audit                   │ │
│  │ Store       │  │ Index       │  │ Log                     │ │
│  │ (Nodes+Edges)│  │ (HNSW)      │  │ (Append-only)          │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## Memory Types

Memorycore separates memory into distinct types instead of dumping everything into one table.

### Memory Type Definitions

| Type | What it stores | Example | Retrieval Use Case |
|------|----------------|---------|-------------------|
| **Episodic** | What happened in a task | "Hermes edited config.yaml and hit a loop" | Task history, debugging |
| **Semantic** | Stable facts | "User uses Windows for Hermes" | Context building |
| **Procedural** | How to do something | "Back up DB before schema patch" | Task execution |
| **Decision** | Why a choice was made | "GLM-5.1 preferred as default main model" | Decision rationale |
| **Correction** | User overrides | "Do not use filler openings" | Behavior modification |
| **Source** | Evidence/provenance | "Paper, article, log, command output" | Citation, verification |
| **Audit** | Raw append-only record | "Tool call, file write, checksum" | Forensics, compliance |

### Memory Type Schema

```python
@dataclass
class MemoryCard:
    id: str
    scope: str                    # project, global, user, agent
    project: str                 # project identifier
    type: MemoryType             # episodic, semantic, procedural, decision, correction, source, audit
    summary: str                # brief summary
    content: str                # full content
    evidence_ids: List[str]     # links to raw evidence
    confidence: float           # 0.0 to 1.0
    status: MemoryStatus        # active, stale, superseded, contradicted, archived
    created_at: str
    updated_at: str
    stale_after: Optional[str]   # expiration timestamp
    allowed_agents: List[str]    # which agents can access
    tags: List[str]
    metadata: Dict[str, Any]
```

---

## Graph Memory

### Why Graph?

Vector search answers: "What text is semantically similar?"
Graph memory answers: "What task caused this decision? Which file was changed? What error happened? What fix worked?"

### Node Types

```python
class GraphNodeType:
    TASK = "task"
    PROJECT = "project"
    FILE = "file"
    COMMAND = "command"
    TOOL_CALL = "tool_call"
    ERROR = "error"
    FIX = "fix"
    DECISION = "decision"
    SOURCE = "source"
    MODEL_PROFILE = "model_profile"
    USER_CORRECTION = "user_correction"
    MEMORY_CARD = "memory_card"
```

### Edge Types

```python
class GraphEdgeType:
    # Task relationships
    TASK_USED = "used"           # Task -> ToolCall
    TASK_PRODUCED = "produced"   # Task -> Error, Task -> Fix
    TASK_PART_OF = "part_of"     # Task -> Project
    
    # Tool/Command relationships
    TOOL_TOUCHED = "touched"     # ToolCall -> File
    TOOL_PRODUCED = "produced"   # ToolCall -> Error, ToolCall -> Output
    
    # Error/Fix relationships
    ERROR_FIXED_BY = "fixed_by"  # Error -> Fix
    ERROR_CAUSED_BY = "caused_by" # Error -> ToolCall, Error -> Command
    
    # Decision relationships
    DECISION_SUPPORTED_BY = "supported_by"  # Decision -> Source
    DECISION_SCOPED_TO = "scoped_to"      # Decision -> Project, Decision -> Task
    
    # Memory Card relationships
    MEMORY_DERIVED_FROM = "derived_from"  # MemoryCard -> Task, MemoryCard -> Source
    MEMORY_SUPERSEDES = "supersedes"      # MemoryCard -> MemoryCard
    MEMORY_CONTRADICTS = "contradicts"    # MemoryCard -> MemoryCard
    
    # User Correction relationships
    CORRECTION_SUPERSEDES = "supersedes"   # UserCorrection -> MemoryCard
    
    # Model Profile relationships
    MODEL_FAILED_ON = "failed_on"        # ModelProfile -> Task
    MODEL_SUCCEEDED_ON = "succeeded_on"   # ModelProfile -> Task
```

### Example Graph Query

```python
# retrieve_context(project="agent-radio", task="database schema fix")
# Should return:
# - prior DB backup path
# - schema.sql relationship to radio.db
# - write_log table requirement
# - safe_write verification procedure
# - previous success/failure records
# - warnings about not touching unrelated files

def retrieve_context(project: str, task: str = None, query: str = None) -> ContextResult:
    # 1. Find the task node
    task_node = graph.find_node("task", {"name": task, "project": project})
    
    # 2. Traverse graph for related memories
    # Get all nodes reachable within 3 hops
    related_nodes = graph.traverse(
        start_nodes=[task_node],
        max_hops=3,
        edge_types=["used", "produced", "touched", "fixed_by", "supported_by", "derived_from"]
    )
    
    # 3. Get memory cards linked to these nodes
    memory_cards = memory_store.get_cards_linked_to_nodes(related_nodes)
    
    # 4. Filter by status (exclude archived, consider stale/superseded)
    active_cards = [c for c in memory_cards if c.status in ["active", "stale", "superseded"]]
    
    # 5. Rank by relevance to query
    ranked_results = ranker.rank_cards(active_cards, query)
    
    return ContextResult(
        task=task,
        project=project,
        memories=ranked_results,
        graph_summary=build_graph_summary(related_nodes)
    )
```

---

## Memory Status System

**Memorycore should NEVER silently delete memory.** Deletion is dangerous because old decisions explain current behavior.

### Status Values

```python
class MemoryStatus:
    ACTIVE = "active"           # Current, valid memory
    STALE = "stale"             # May be outdated but still relevant
    SUPERSEDED = "superseded"   # Replaced by newer memory
    CONTRADICTED = "contradicted" # Conflicts with other memory
    ARCHIVED = "archived"       # No longer relevant, kept for history
```

### Example: Model Preference Change

```python
# Old memory
old_card = MemoryCard(
    id="m_abc123",
    type=MemoryType.DECISION,
    summary="Use Kimi K2.7 Code as Hermes main agent",
    status=MemoryStatus.ACTIVE,
    scope="kimi-setup"
)

# New memory
new_card = MemoryCard(
    id="m_def456",
    type=MemoryType.DECISION,
    summary="For current Ollama Cloud Hermes planning, prefer GLM-5.1 or DeepSeek V4 Pro",
    status=MemoryStatus.ACTIVE,
    scope="ollama-cloud"
)

# Create supersession relationship
memory_engine.supersede(
    old_memory_id="m_abc123",
    new_memory_id="m_def456",
    reason="Model preference updated for Ollama Cloud setup",
    scope="ollama-cloud"
)

# Old memory is now superseded but NOT deleted
old_card.status = MemoryStatus.SUPERSEDED
old_card.stale_after = "2024-01-01T00:00:00Z"
```

---

## Consolidation Engine

Raw logs are not memory. They are evidence. Memorycore needs a consolidator that transforms raw task logs into durable memory cards.

### Consolidation Pipeline

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│   Raw Task Log       │────▶│  Extract Events      │────▶│ Identify Facts/      │
│   - Tool calls       │     │  - Important actions │     │ Procedures          │
│   - File changes     │     │  - Errors            │     │ - Reusable knowledge │
│   - Command output   │     │  - Warnings          │     │ - Decisions          │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
                                                              ↓
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  Detect Conflicts     │────▶│ Create Memory Cards  │────▶│ Link to Evidence     │
│  - Contradictions     │     │  - One per fact      │     │ - Source references │
│  - Stale information  │     │  - Type classification│    │ - Graph links       │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
                                                              ↓
                                                        ┌─────────────────────┐
                                                        │ Mark Stale/Superseded│
                                                        │ memories             │
                                                        └─────────────────────┘
```

### Consolidation Triggers

The consolidator can run:
- After each task (immediate consolidation)
- Nightly (batch consolidation)
- Before major project sessions (pre-session review)
- After user correction (immediate update)

### Example Consolidation

```python
class Consolidator:
    def consolidate_task(self, task_id: str, raw_log: TaskLog) -> List[MemoryCard]:
        # Step 1: Extract events
        events = self._extract_events(raw_log)
        
        # Step 2: Identify memory-worthy information
        facts = self._extract_facts(events)
        procedures = self._extract_procedures(events)
        decisions = self._extract_decisions(events)
        corrections = self._extract_corrections(events)
        
        # Step 3: Detect conflicts with existing memory
        conflicts = self._detect_conflicts([facts, procedures, decisions, corrections])
        
        # Step 4: Create memory cards
        cards = []
        for fact in facts:
            card = MemoryCard(
                id=f"mc_{uuid.uuid4().hex[:12]}",
                type=MemoryType.SEMANTIC,
                summary=fact.summary,
                content=fact.content,
                evidence_ids=[raw_log.log_id],
                confidence=fact.confidence,
                status=MemoryStatus.ACTIVE,
                project=raw_log.project_id,
                scope="project"
            )
            cards.append(card)
        
        # Step 5: Link cards to evidence and graph
        self._link_cards_to_evidence(cards, raw_log)
        self._link_cards_to_graph(cards, events)
        
        # Step 6: Handle conflicts
        self._resolve_conflicts(conflicts, cards)
        
        return cards
```

---

## Minimal API

### Phase 1: Core API (Start Here)

```python
class MemoryEngine:
    # Record raw episodes (task logs, agent sessions)
    def record_episode(
        self,
        project_id: str,
        task_id: str,
        raw_log: Dict[str, Any],
        agent_id: str,
        metadata: Dict[str, Any] = None
    ) -> EpisodeRecord:
        """Record a raw episode for later consolidation."""
        
    # Add a consolidated memory card
    def add_card(
        self,
        card: MemoryCard
    ) -> MemoryCard:
        """Add a new memory card (consolidated from episodes)."""
        
    # Retrieve context for a project/task
    def retrieve_context(
        self,
        project_id: str,
        task_id: str = None,
        query: str = None,
        memory_types: List[MemoryType] = None,
        limit: int = 50
    ) -> ContextResult:
        """Retrieve relevant memories with graph traversal."""
        
    # Mark memory as superseded
    def supersede(
        self,
        old_memory_id: str,
        new_memory_id: str,
        reason: str,
        created_by: str
    ) -> SupersessionRecord:
        """Create supersession relationship between memories."""
        
    # Get audit log
    def audit(
        self,
        project_id: str = None,
        user_id: str = None,
        action: str = None,
        limit: int = 100
    ) -> List[AuditRecord]:
        """Get audit log entries."""
```

### Phase 2: Advanced API (Add Later)

```python
class MemoryEngine:
    # Extract memory cards from a task
    def extract_from_task(
        self,
        task_id: str
    ) -> List[MemoryCard]:
        """Automatically extract memory cards from a task."""
        
    # Find conflicts between memories
    def find_conflicts(
        self,
        project_id: str = None
    ) -> List[Conflict]:
        """Find conflicting memories that need resolution."""
        
    # Score relevance of memories to a query
    def score_relevance(
        self,
        query: str,
        memory_ids: List[str]
    ) -> Dict[str, float]:
        """Score memories by relevance to a query."""
        
    # Compact project memory (archive old, resolve conflicts)
    def compact_project(
        self,
        project_id: str
    ) -> CompactionResult:
        """Compact and optimize project memory."""
        
    # Export project brief (summary of all memories)
    def export_project_brief(
        self,
        project_id: str
    ) -> ProjectBrief:
        """Export a comprehensive brief of project memory."""
```

---

## Storage Schema

### CozoDB Schema (Primary)

```cozo
-- Memory Cards Table
memories: {
    memory_id: str,
    project_id: str,
    scope: str,  -- project, global, user, agent
    memory_type: str,  -- episodic, semantic, procedural, decision, correction, source, audit
    summary: str,
    content: str,
    evidence_ids: [str],
    confidence: f64,
    status: str,  -- active, stale, superseded, contradicted, archived
    created_at: str,
    updated_at: str,
    stale_after: ?str,
    allowed_agents: [str],
    tags: [str],
    metadata: {}
}

-- Graph Nodes Table
 graph_nodes: {
    node_id: str,
    node_type: str,  -- task, project, file, command, tool_call, error, fix, decision, source, model_profile, user_correction, memory_card
    name: str,
    project_id: str,
    properties: {},
    created_at: str
}

-- Graph Edges Table
graph_edges: {
    edge_id: str,
    from_node_id: str,
    to_node_id: str,
    edge_type: str,  -- used, produced, touched, fixed_by, supported_by, derived_from, supersedes, contradicts, etc.
    strength: f64,
    description: str,
    created_at: str,
    created_by: str
}

-- Episodes Table (raw logs)
episodes: {
    episode_id: str,
    project_id: str,
    task_id: str,
    agent_id: str,
    raw_content: str,
    metadata: {},
    created_at: str,
    consolidated: bool
}

-- Supersession Chains
supersession_chains: {
    chain_id: str,
    old_memory_id: str,
    new_memory_id: str,
    reason: str,
    created_at: str,
    created_by: str,
    is_active: bool
}

-- Contradiction Chains
contradiction_chains: {
    chain_id: str,
    memory_a_id: str,
    memory_b_id: str,
    resolution: str,  -- unresolved, resolved, dismissed
    resolution_notes: str,
    created_at: str,
    created_by: str,
    resolved_at: ?str,
    resolved_by: ?str
}

-- Audit Log (append-only)
audit_log: {
    audit_id: str,
    timestamp: str,
    action: str,  -- read, write, delete, update, consolidate, supersede, contradict
    entity_type: str,  -- memory, episode, graph_node, graph_edge, project
    entity_id: str,
    project_id: ?str,
    user_id: str,
    details: {},
    ip_address: ?str,
    user_agent: ?str
}

-- Full-text search index
ft_index_memories: {
    memory_id: str,
    content: str,
    summary: str,
    tags: [str]
}

-- Vector index (768-dim float32)
vector_index_memories: {
    memory_id: str,
    vector: [f32]
}
```

### SQLite Schema (Fallback)

See `db/schema.sql` for SQLite implementation with similar structure.

---

## Retrieval Engine

### Hybrid Search Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    RETRIEVAL ENGINE                              │
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐ │
│  │ Vector      │    │ Graph        │    │ Text/FTS            │ │
│  │ Search      │    │ Traversal    │    │ Search              │ │
│  │ (Semantic)  │    │ (Structural) │    │ (Keyword)           │ │
│  └─────────────┘    └─────────────┘    └─────────────────────┘ │
│           ↓                  ↓                    ↓              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                    RANKING & FUSION                         │ │
│  │  - RRF (Reciprocal Rank Fusion)                           │ │
│  │  - Weighted combination                                  │ │
│  │  - Status filtering (exclude archived)                   │ │
│  │  - Scope filtering (project, agent, etc.)                 │ │
│  └─────────────────────────────────────────────────────────┘ │
│                              ↓                                   │
│                    ┌─────────────────┐                          │
│                    │  Final Results   │                          │
│                    │  (Ranked, Filtered)│                         │
│                    └─────────────────┘                          │
└─────────────────────────────────────────────────────────────┘
```

### Retrieval Process

```python
def retrieve_context(
    self,
    project_id: str,
    task_id: str = None,
    query: str = None,
    memory_types: List[MemoryType] = None,
    limit: int = 50
) -> ContextResult:
    # Step 1: Graph traversal (if task_id provided)
    if task_id:
        task_node = self.graph.get_node(task_id)
        related_nodes = self.graph.traverse(
            start_nodes=[task_node],
            max_hops=3
        )
        graph_memory_ids = self.graph.get_linked_memories(related_nodes)
    else:
        graph_memory_ids = []
    
    # Step 2: Vector search (if query provided)
    if query:
        query_embedding = self.embedding_manager.generate(query)
        vector_results = self.vector_search.search(
            query_embedding,
            project_id=project_id,
            limit=limit * 2  # Get more for fusion
        )
        vector_memory_ids = [r.memory_id for r in vector_results.results]
    else:
        vector_memory_ids = []
    
    # Step 3: Text search (if query provided)
    if query:
        text_results = self.text_search.search(
            query,
            project_id=project_id,
            limit=limit * 2
        )
        text_memory_ids = [r.memory_id for r in text_results.results]
    else:
        text_memory_ids = []
    
    # Step 4: Combine and deduplicate
    all_memory_ids = list(set(
        graph_memory_ids + 
        vector_memory_ids + 
        text_memory_ids
    ))
    
    # Step 5: Get full memory records
    memories = self.memory_store.get_memories(all_memory_ids)
    
    # Step 6: Filter by status and type
    filtered_memories = [
        m for m in memories
        if m.status in [MemoryStatus.ACTIVE, MemoryStatus.STALE, MemoryStatus.SUPERSEDED]
        and (memory_types is None or m.type in memory_types)
    ]
    
    # Step 7: Rank using RRF or weighted fusion
    ranked_memories = self.ranker.rank(
        filtered_memories,
        query=query,
        graph_scores={m.memory_id: score for m, score in zip(filtered_memories, graph_scores)},
        vector_scores={m.memory_id: score for m, score in zip(filtered_memories, vector_scores)},
        text_scores={m.memory_id: score for m, score in zip(filtered_memories, text_scores)}
    )
    
    # Step 8: Return top results
    return ContextResult(
        project_id=project_id,
        task_id=task_id,
        query=query,
        memories=ranked_memories[:limit],
        total=len(filtered_memories),
        graph_summary=self.graph.build_summary(related_nodes)
    )
```

---

## MCP Server Interface

### Tool Definitions

```python
# Core memory operations
memory.record_episode(project_id, task_id, raw_log, agent_id, metadata)
memory.add_card(card_dict)
memory.retrieve_context(project_id, task_id=None, query=None, limit=50)
memory.supersede(old_memory_id, new_memory_id, reason, created_by)
memory.audit(project_id=None, user_id=None, action=None, limit=100)

# Graph operations
memory.add_node(node_type, name, project_id, properties)
memory.add_edge(from_node_id, to_node_id, edge_type, strength, description)
memory.traverse(start_node_id, max_hops=3, edge_types=None)

# Search operations
memory.search(query, project_id=None, memory_types=None, limit=100)
memory.vector_search(query_embedding, project_id=None, limit=100)
memory.hybrid_search(query, project_id=None, vector_weight=0.5, text_weight=0.5, limit=100)

# Consolidation
memory.consolidate_task(task_id)
memory.consolidate_project(project_id)

# Advanced (Phase 2)
memory.extract_from_task(task_id)
memory.find_conflicts(project_id=None)
memory.score_relevance(query, memory_ids)
memory.compact_project(project_id)
memory.export_project_brief(project_id)
```

---

## Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
- [ ] Define memory types enum and schema
- [ ] Implement memory card data structure
- [ ] Create graph node/edge data structures
- [ ] Implement basic graph storage (CozoDB)
- [ ] Implement minimal API (record_episode, add_card, retrieve_context, supersede, audit)
- [ ] Update MCP server with new types

### Phase 2: Retrieval (Week 3-4)
- [ ] Implement vector search integration
- [ ] Implement graph traversal
- [ ] Implement hybrid retrieval (vector + graph + text)
- [ ] Implement RRF ranking
- [ ] Add status filtering to all queries

### Phase 3: Consolidation (Week 5-6)
- [ ] Implement event extraction from raw logs
- [ ] Implement memory card creation
- [ ] Implement conflict detection
- [ ] Implement linking to evidence
- [ ] Implement stale/superseded marking

### Phase 4: Advanced Features (Week 7-8)
- [ ] Implement extract_from_task
- [ ] Implement find_conflicts
- [ ] Implement score_relevance
- [ ] Implement compact_project
- [ ] Implement export_project_brief

---

## Key Design Decisions

1. **No Silent Deletion**: Memory is never deleted, only marked with status. This preserves history and explains current behavior.

2. **Graph + Vector**: Both are needed. Vector for semantic similarity, graph for structural relationships.

3. **Memory Types**: Explicit typing enables different retrieval strategies for different use cases.

4. **Consolidation**: Raw logs are evidence, not memory. Consolidation transforms evidence into durable memory.

5. **Minimal API First**: Start small with core operations, expand based on real usage patterns.

6. **Open and Inspectable**: All memory should be queryable, all operations auditable.

7. **Local-First**: Default to local storage (SQLite/CozoDB), with optional cloud sync.

8. **Cross-Agent**: Designed to be used by multiple agents, not tied to any specific agent framework.

---

## Comparison with Perplexity Brain

| Feature | Perplexity Brain | Memorycore |
|---------|-----------------|------------|
| Purpose | Perplexity Computer memory | Cross-agent memory infrastructure |
| Scope | Single product | Any local or cloud agent |
| Memory Types | Likely unified | Explicit types (episodic, semantic, procedural, etc.) |
| Graph | Unknown | Yes (nodes + edges for structural relationships) |
| Vector | Likely yes | Yes (HNSW for semantic search) |
| Consolidation | "Overnight" review | Configurable (per-task, nightly, pre-session) |
| Audit | Unknown | Yes (append-only, comprehensive) |
| API | Unknown | Minimal, well-defined |
| Storage | Unknown | SQLite + CozoDB (local-first) |
| Access | Perplexity only | Open, any agent |

Memorycore's key differentiator: **It's the shared memory layer that lets multiple agents improve across sessions, with full auditability and both semantic and structural retrieval.**
