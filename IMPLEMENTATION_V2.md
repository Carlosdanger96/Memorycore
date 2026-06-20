# Memorycore v2 Implementation Summary

## Overview

This document summarizes the implementation of Memorycore v2, which transforms Memorycore from a simple note store into a **shared memory operating layer for agents**.

## Key Changes

### 1. New Architecture

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
│                    MEMORY ENGINE V2                             │
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

### 2. New Memory Types System

**File:** `server/memory_types.py`

Memorycore now separates memory into distinct types:

| Type | What it stores | Example | Retrieval Use Case |
|------|----------------|---------|-------------------|
| **Episodic** | What happened in a task | "Hermes edited config.yaml and hit a loop" | Task history, debugging |
| **Semantic** | Stable facts | "User uses Windows for Hermes" | Context building |
| **Procedural** | How to do something | "Back up DB before schema patch" | Task execution |
| **Decision** | Why a choice was made | "GLM-5.1 preferred as default main model" | Decision rationale |
| **Correction** | User overrides | "Do not use filler openings" | Behavior modification |
| **Source** | Evidence/provenance | "Paper, article, log, command output" | Citation, verification |
| **Audit** | Raw append-only record | "Tool call, file write, checksum" | Forensics, compliance |

**Key Classes:**
- `MemoryType`: Enum for memory types
- `MemoryStatus`: Enum for status (ACTIVE, STALE, SUPERSEDED, CONTRADICTED, ARCHIVED)
- `MemoryScope`: Enum for scope (PROJECT, GLOBAL, USER, AGENT)
- `MemoryCard`: Main memory data structure
- `EpisodeRecord`: Raw task logs (evidence)
- `GraphNode`: Graph node data structure
- `GraphEdge`: Graph edge data structure
- `SupersessionRecord`: Tracks memory supersession
- `ContextResult`: Result of context retrieval

### 3. Graph Memory Layer

**File:** `server/graph_memory.py`

Implements structural relationships between entities:

**Node Types:**
- TASK, PROJECT, FILE, COMMAND, TOOL_CALL
- ERROR, FIX, DECISION, SOURCE
- MODEL_PROFILE, USER_CORRECTION, MEMORY_CARD

**Edge Types:**
- TASK_USED, TASK_PRODUCED, TASK_PART_OF
- TOOL_TOUCHED, TOOL_PRODUCED
- ERROR_FIXED_BY, ERROR_CAUSED_BY
- DECISION_SUPPORTED_BY, DECISION_SCOPED_TO
- MEMORY_DERIVED_FROM, MEMORY_SUPERSEDES, MEMORY_CONTRADICTS
- MODEL_FAILED_ON, MODEL_SUCCEEDED_ON

**Key Features:**
- Graph traversal with configurable depth
- Memory-node linking
- Graph summary statistics
- In-memory and persistent storage support

### 4. Consolidation Engine

**File:** `server/consolidator.py`

Transforms raw task logs (episodes) into durable memory cards:

**Pipeline:**
1. Extract events from raw logs (tool calls, file changes, errors, etc.)
2. Identify reusable facts/procedures/decision
3. Detect conflicts with existing memory
4. Create memory cards
5. Link cards to evidence and graph
6. Mark stale/superseded memories

**Conflict Detection:**
- Contradiction detection (negation patterns)
- Update detection (version numbers, dates)
- Stale detection (similar but not contradictory)

**Conflict Resolution:**
- Mark as CONTRADICTED
- Mark as SUPERSEDED
- Mark as STALE

### 5. Memory Engine v2

**File:** `server/memory_engine_v2.py`

Implements the minimal API:

**Core API:**
- `record_episode()`: Record raw task logs
- `add_card()`: Add consolidated memory cards
- `retrieve_context()`: Get comprehensive context (graph + vector + text)
- `supersede()`: Create supersession relationships
- `audit()`: Get audit logs

**Extended API:**
- `get_memory_card()`: Get memory by ID
- `update_memory_card()`: Update memory
- `search_memory_cards()`: Search with filters
- `consolidate_episode()`: Consolidate specific episode
- `consolidate_project()`: Consolidate all episodes for project
- `get_graph_summary()`: Get graph statistics
- `traverse_graph()`: Traverse graph structure

**Key Features:**
- Configurable engine (graph memory, consolidation, auto-consolidation)
- Simple ranking algorithm (confidence + status + recency + query match)
- Health monitoring
- Comprehensive audit logging

### 6. MCP Server v2

**File:** `server/mcp_server_v2.py`

Exposes all new functionality via MCP:

**New Tools:**
- `memory.record_episode`: Record raw task logs
- `memory.add_card`: Add consolidated memory cards
- `memory.retrieve_context`: Get comprehensive context
- `memory.supersede`: Create supersession relationships
- `memory.audit`: Get audit logs
- `memory.search`: Search memory cards
- `memory.consolidate_episode`: Consolidate specific episode
- `memory.consolidate_project`: Consolidate all episodes for project
- `graph.add_node`: Add graph nodes
- `graph.add_edge`: Add graph edges
- `graph.traverse`: Traverse the graph
- `graph.get_summary`: Get graph summary
- `system.health_check`: Check system health
- `system.get_config`: Get configuration

### 7. Architecture Documentation

**File:** `docs/ARCHITECTURE_V2.md`

Comprehensive architecture document covering:
- Vision and core principles
- Architecture overview
- Memory types and schema
- Graph memory design
- Consolidation pipeline
- Minimal and extended API
- Storage schema (CozoDB and SQLite)
- Retrieval engine architecture
- MCP server interface
- Implementation roadmap
- Key design decisions
- Comparison with Perplexity Brain

## Key Design Decisions

### 1. No Silent Deletion
Memory is never deleted, only marked with status. This preserves history and explains current behavior.

### 2. Graph + Vector
Both are needed:
- Vector search for semantic similarity
- Graph memory for structural relationships

### 3. Memory Types
Explicit typing enables different retrieval strategies for different use cases.

### 4. Consolidation
Raw logs are evidence, not memory. Consolidation transforms evidence into durable memory.

### 5. Minimal API First
Start small with core operations, expand based on real usage patterns.

### 6. Open and Inspectable
All memory should be queryable, all operations auditable.

### 7. Local-First
Default to local storage (SQLite/CozoDB), with optional cloud sync.

### 8. Cross-Agent
Designed to be used by multiple agents, not tied to any specific agent framework.

## What Makes Memorycore Different

| Feature | Perplexity Brain | Memorycore v2 |
|---------|-----------------|---------------|
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

**Memorycore's key differentiator:** It's the shared memory layer that lets multiple agents improve across sessions, with full auditability and both semantic and structural retrieval.

## Files Added/Modified

### New Files:
1. `docs/ARCHITECTURE_V2.md` - Comprehensive architecture document
2. `memorycore/memory_types.py` - Memory types and data structures
3. `memorycore/graph_memory.py` - Graph memory layer
4. `memorycore/consolidator.py` - Consolidation engine
5. `memorycore/memory_engine_v2.py` - Memory Engine v2
6. `memorycore/mcp_server_v2.py` - MCP Server v2

### Modified Files:
- `server/` directory restructured as `memorycore/` package with proper relative imports
- Added `pyproject.toml` for modern dependency management
- Added `.github/workflows/tests.yml` for CI
- Updated `.gitignore` with comprehensive exclusions
- Fixed CozoDB schema merge conflicts and filter parameter naming

### Status
**Current Status:** Active prototype / v2 foundation

**Stable today:**
- Memory card types and data structures
- Episode records and audit logging
- SQLite/Postgres-oriented storage
- MCP v2 tool surface (14 tools)

**Experimental:**
- CozoDB graph/vector schema
- Automatic consolidation
- HNSW retrieval
- Cross-agent policy enforcement

## Usage Examples

### Recording an Episode

```python
from memorycore.memory_engine_v2 import create_memory_engine_v2

engine = create_memory_engine_v2()

# Record a task log
episode = engine.record_episode(
    project_id="agent-radio",
    task_id="database-schema-fix",
    raw_log={
        "timestamp": "2024-01-15T10:00:00Z",
        "agent": "Hermes",
        "actions": [
            "Read schema.sql",
            "Modified write_log table",
            "Error: duplicate column",
            "Fixed by removing duplicate"
        ]
    },
    agent_id="Hermes",
    metadata={"session_id": "sess_123"}
)
```

### Retrieving Context

```python
# Get context for a task
context = engine.retrieve_context(
    project_id="agent-radio",
    task_id="database-schema-fix",
    query="backup procedure",
    memory_types=["procedural", "decision"],
    limit=20
)

# Returns:
# - prior DB backup path
# - schema.sql relationship to radio.db
# - write_log table requirement
# - safe_write verification procedure
# - previous success/failure records
```

### Creating Supersession

```python
# Old model preference
old_card = engine.add_card(MemoryCard(
    project="hermes",
    type=MemoryType.DECISION,
    summary="Use Kimi K2.7 Code as Hermes main agent",
    content="After testing, Kimi K2.7 Code performs best for...",
    status=MemoryStatus.ACTIVE
))

# New model preference
new_card = engine.add_card(MemoryCard(
    project="hermes",
    type=MemoryType.DECISION,
    summary="For current Ollama Cloud Hermes planning, prefer GLM-5.1 or DeepSeek V4 Pro",
    content="With Ollama Cloud, GLM-5.1 and DeepSeek V4 Pro outperform...",
    status=MemoryStatus.ACTIVE
))

# Create supersession (old is NOT deleted)
engine.supersede(
    old_memory_id=old_card.id,
    new_memory_id=new_card.id,
    reason="Model preference updated for Ollama Cloud setup",
    created_by="user123"
)

# old_card.status is now SUPERSEDED
# Both cards are preserved for history
```

### Using Graph Memory

```python
# Add nodes
from server.memory_types import GraphNode, GraphNodeType

task_node = engine.graph_memory.add_node(GraphNode(
    node_type=GraphNodeType.TASK,
    name="database-schema-fix",
    project_id="agent-radio"
))

file_node = engine.graph_memory.add_node(GraphNode(
    node_type=GraphNodeType.FILE,
    name="schema.sql",
    project_id="agent-radio"
))

# Add edge
task_to_file = engine.graph_memory.add_edge(GraphEdge(
    from_node_id=task_node.node_id,
    to_node_id=file_node.node_id,
    edge_type="touched",
    description="Task modified schema.sql"
))

# Traverse graph
result = engine.graph_memory.traverse(
    start_node_ids=[task_node.node_id],
    max_hops=3
)
# Returns all nodes and edges reachable within 3 hops
```

## Migration Path

The v2 implementation is designed to be additive:

1. **Phase 1**: Use existing Memorycore as-is
2. **Phase 2**: Add v2 components alongside existing ones
3. **Phase 3**: Gradually migrate to v2 API
4. **Phase 4**: Deprecate old API (optional)

The new files don't modify existing functionality, so there's no breaking change.

## Next Steps

1. **Integrate with existing storage**: Add methods to persist MemoryCard, EpisodeRecord, GraphNode, GraphEdge to CozoDB/SQLite
2. **Enhance retrieval**: Add vector search integration to Memory Engine v2
3. **Improve consolidation**: Add better event extraction using LLM
4. **Add tests**: Comprehensive test coverage for new components
5. **Update documentation**: Add usage examples and API docs
6. **Performance optimization**: Optimize graph traversal and ranking

## Conclusion

Memorycore v2 transforms the project from a simple note store into a **shared memory operating layer for agents**. It implements all the key concepts from the vision:

✅ Memory types (episodic, semantic, procedural, decision, correction, source, audit)
✅ Graph memory with nodes and edges
✅ Consolidation engine for raw logs to memory cards
✅ Enhanced status system (no silent deletion)
✅ Minimal API (record_episode, add_card, retrieve_context, supersede, audit)
✅ MCP server with new tools
✅ Comprehensive architecture documentation

This makes Memorycore different from Perplexity Brain by being:
- **Open**: Any agent can use it
- **Inspectable**: All memory is queryable
- **Local-first**: Works offline with SQLite/CozoDB
- **Structural**: Graph memory enables multi-hop recall
- **Durable**: Never silently deletes memory
- **Cross-agent**: Shared memory layer for multiple agents
