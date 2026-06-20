"""Memorycore - A portable external memory layer for any LLM, agent, CLI, or tool-connected system.

This package provides:
- Memory card types and data structures
- Memory engine for storing and retrieving memories
- Graph memory for structural relationships
- Consolidation engine for transforming episodes into durable memory
- MCP server interface for agent integration
- Storage backends (SQLite, Postgres, CozoDB)
"""

from .memory_types import (
    MemoryCard,
    MemoryType,
    MemoryStatus,
    MemoryScope,
    EpisodeRecord,
    GraphNode,
    GraphNodeType,
    GraphEdgeType,
    SupersessionRecord,
    ContextResult,
)

__version__ = "0.2.0"
__all__ = [
    "MemoryCard",
    "MemoryType",
    "MemoryStatus",
    "MemoryScope",
    "EpisodeRecord",
    "GraphNode",
    "GraphNodeType",
    "GraphEdgeType",
    "SupersessionRecord",
    "ContextResult",
]
