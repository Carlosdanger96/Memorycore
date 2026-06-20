"""Memory Types for Memorycore v2.

Defines the memory type system that separates memory into distinct categories
instead of dumping everything into one table.

Memory Types:
- Episodic: What happened in a task
- Semantic: Stable facts
- Procedural: How to do something
- Decision: Why a choice was made
- Correction: User overrides
- Source: Evidence/provenance
- Audit: Raw append-only record

Each type should be retrieved differently:
- Coding task: needs procedures and audit history
- Research task: needs source memory and decision history
- Profile change: needs model-decision memory
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import uuid


class MemoryType(str, Enum):
    """Memory type enumeration."""
    
    # What happened in a task
    EPISODIC = "episodic"
    
    # Stable facts
    SEMANTIC = "semantic"
    
    # How to do something
    PROCEDURAL = "procedural"
    
    # Why a choice was made
    DECISION = "decision"
    
    # User overrides
    CORRECTION = "correction"
    
    # Evidence/provenance
    SOURCE = "source"
    
    # Raw append-only record
    AUDIT = "audit"


class MemoryScope(str, Enum):
    """Memory scope enumeration."""
    
    # Memory is specific to a project
    PROJECT = "project"
    
    # Memory is global across all projects
    GLOBAL = "global"
    
    # Memory is specific to a user
    USER = "user"
    
    # Memory is specific to an agent
    AGENT = "agent"


class MemoryStatus(str, Enum):
    """Memory status enumeration.
    
    Memorycore should NEVER silently delete memory.
    Old decisions explain current behavior, so we mark them instead.
    """
    
    # Current, valid memory
    ACTIVE = "active"
    
    # May be outdated but still relevant
    STALE = "stale"
    
    # Replaced by newer memory
    SUPERSEDED = "superseded"
    
    # Conflicts with other memory
    CONTRADICTED = "contradicted"
    
    # No longer relevant, kept for history
    ARCHIVED = "archived"


@dataclass
class MemoryCard:
    """Memory card data structure.
    
    Represents a consolidated memory that answers one of:
    - What did the agent do?
    - What worked?
    - What failed?
    - What correction was made?
    - What should the agent do differently next time?
    - What source or log proves this?
    
    Attributes:
        id: Unique memory card identifier
        scope: Memory scope (project, global, user, agent)
        project: Project identifier
        type: Memory type (episodic, semantic, procedural, decision, correction, source, audit)
        summary: Brief summary of the memory
        content: Full content of the memory
        evidence_ids: Links to raw evidence (episodes, logs, etc.)
        confidence: Confidence score (0.0 to 1.0)
        status: Memory status (active, stale, superseded, contradicted, archived)
        created_at: Creation timestamp
        updated_at: Last update timestamp
        stale_after: Optional expiration timestamp
        allowed_agents: List of agent IDs that can access this memory
        tags: Tags for categorization
        metadata: Additional metadata
    """
    
    id: str = field(default_factory=lambda: f"mc_{uuid.uuid4().hex[:12]}")
    scope: str = MemoryScope.PROJECT
    project: str = ""
    type: str = MemoryType.SEMANTIC
    summary: str = ""
    content: str = ""
    evidence_ids: List[str] = field(default_factory=list)
    confidence: float = 0.0
    status: str = MemoryStatus.ACTIVE
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    stale_after: Optional[str] = None
    allowed_agents: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "id": self.id,
            "scope": self.scope,
            "project": self.project,
            "type": self.type,
            "summary": self.summary,
            "content": self.content,
            "evidence_ids": self.evidence_ids,
            "confidence": self.confidence,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "stale_after": self.stale_after,
            "allowed_agents": self.allowed_agents,
            "tags": self.tags,
            "metadata": self.metadata,
        }
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryCard":
        """Create MemoryCard from dictionary."""
        return cls(
            id=data.get("id", f"mc_{uuid.uuid4().hex[:12]}"),
            scope=data.get("scope", MemoryScope.PROJECT),
            project=data.get("project", ""),
            type=data.get("type", MemoryType.SEMANTIC),
            summary=data.get("summary", ""),
            content=data.get("content", ""),
            evidence_ids=data.get("evidence_ids", []),
            confidence=data.get("confidence", 0.0),
            status=data.get("status", MemoryStatus.ACTIVE),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat()),
            stale_after=data.get("stale_after"),
            allowed_agents=data.get("allowed_agents", []),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )
    
    def is_active(self) -> bool:
        """Check if memory is active (not archived)."""
        return self.status in [MemoryStatus.ACTIVE, MemoryStatus.STALE, MemoryStatus.SUPERSEDED, MemoryStatus.CONTRADICTED]
    
    def is_superseded(self) -> bool:
        """Check if memory has been superseded."""
        return self.status == MemoryStatus.SUPERSEDED
    
    def is_archived(self) -> bool:
        """Check if memory has been archived."""
        return self.status == MemoryStatus.ARCHIVED
    
    def is_expired(self) -> bool:
        """Check if memory has expired (stale_after passed)."""
        if not self.stale_after:
            return False
        return datetime.fromisoformat(self.stale_after) < datetime.utcnow()


# Graph Node Types
class GraphNodeType(str, Enum):
    """Graph node type enumeration."""
    
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


# Graph Edge Types
class GraphEdgeType(str, Enum):
    """Graph edge type enumeration."""
    
    # Task relationships
    TASK_USED = "used"              # Task -> ToolCall
    TASK_PRODUCED = "produced"      # Task -> Error, Task -> Fix
    TASK_PART_OF = "part_of"        # Task -> Project
    
    # Tool/Command relationships
    TOOL_TOUCHED = "touched"        # ToolCall -> File
    TOOL_PRODUCED = "produced"      # ToolCall -> Error, ToolCall -> Output
    
    # Error/Fix relationships
    ERROR_FIXED_BY = "fixed_by"     # Error -> Fix
    ERROR_CAUSED_BY = "caused_by"   # Error -> ToolCall, Error -> Command
    
    # Decision relationships
    DECISION_SUPPORTED_BY = "supported_by"   # Decision -> Source
    DECISION_SCOPED_TO = "scoped_to"       # Decision -> Project, Decision -> Task
    
    # Memory Card relationships
    MEMORY_DERIVED_FROM = "derived_from"   # MemoryCard -> Task, MemoryCard -> Source
    MEMORY_SUPERSEDES = "supersedes"       # MemoryCard -> MemoryCard
    MEMORY_CONTRADICTS = "contradicts"     # MemoryCard -> MemoryCard
    
    # User Correction relationships
    CORRECTION_SUPERSEDES = "supersedes"   # UserCorrection -> MemoryCard
    
    # Model Profile relationships
    MODEL_FAILED_ON = "failed_on"        # ModelProfile -> Task
    MODEL_SUCCEEDED_ON = "succeeded_on"   # ModelProfile -> Task


@dataclass
class GraphNode:
    """Graph node data structure.
    
    Represents an entity in the memory graph.
    
    Attributes:
        node_id: Unique node identifier
        node_type: Node type (task, project, file, etc.)
        name: Human-readable name
        project_id: Project identifier
        properties: Additional properties specific to node type
        created_at: Creation timestamp
    """
    
    node_id: str = field(default_factory=lambda: f"node_{uuid.uuid4().hex[:12]}")
    node_type: str = GraphNodeType.TASK
    name: str = ""
    project_id: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "name": self.name,
            "project_id": self.project_id,
            "properties": self.properties,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphNode":
        """Create GraphNode from dictionary."""
        return cls(
            node_id=data.get("node_id", f"node_{uuid.uuid4().hex[:12]}"),
            node_type=data.get("node_type", GraphNodeType.TASK),
            name=data.get("name", ""),
            project_id=data.get("project_id", ""),
            properties=data.get("properties", {}),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
        )


@dataclass
class GraphEdge:
    """Graph edge data structure.
    
    Represents a relationship between two nodes in the memory graph.
    
    Attributes:
        edge_id: Unique edge identifier
        from_node_id: Source node ID
        to_node_id: Target node ID
        edge_type: Edge type (used, produced, fixed_by, etc.)
        strength: Relationship strength (0.0 to 1.0)
        description: Human-readable description
        created_at: Creation timestamp
        created_by: Who created this edge
    """
    
    edge_id: str = field(default_factory=lambda: f"edge_{uuid.uuid4().hex[:12]}")
    from_node_id: str = ""
    to_node_id: str = ""
    edge_type: str = GraphEdgeType.TASK_USED
    strength: float = 1.0
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_by: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "edge_id": self.edge_id,
            "from_node_id": self.from_node_id,
            "to_node_id": self.to_node_id,
            "edge_type": self.edge_type,
            "strength": self.strength,
            "description": self.description,
            "created_at": self.created_at,
            "created_by": self.created_by,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphEdge":
        """Create GraphEdge from dictionary."""
        return cls(
            edge_id=data.get("edge_id", f"edge_{uuid.uuid4().hex[:12]}"),
            from_node_id=data.get("from_node_id", ""),
            to_node_id=data.get("to_node_id", ""),
            edge_type=data.get("edge_type", GraphEdgeType.TASK_USED),
            strength=data.get("strength", 1.0),
            description=data.get("description", ""),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            created_by=data.get("created_by", ""),
        )


@dataclass
class EpisodeRecord:
    """Episode record for raw task logs.
    
    Represents raw evidence that can be consolidated into memory cards.
    
    Attributes:
        episode_id: Unique episode identifier
        project_id: Project identifier
        task_id: Task identifier
        agent_id: Agent that performed the task
        raw_content: Raw log content
        metadata: Additional metadata
        created_at: Creation timestamp
        consolidated: Whether this episode has been consolidated
    """
    
    episode_id: str = field(default_factory=lambda: f"ep_{uuid.uuid4().hex[:12]}")
    project_id: str = ""
    task_id: str = ""
    agent_id: str = ""
    raw_content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    consolidated: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "episode_id": self.episode_id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "raw_content": self.raw_content,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "consolidated": self.consolidated,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EpisodeRecord":
        """Create EpisodeRecord from dictionary."""
        return cls(
            episode_id=data.get("episode_id", f"ep_{uuid.uuid4().hex[:12]}"),
            project_id=data.get("project_id", ""),
            task_id=data.get("task_id", ""),
            agent_id=data.get("agent_id", ""),
            raw_content=data.get("raw_content", ""),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            consolidated=data.get("consolidated", False),
        )


@dataclass
class SupersessionRecord:
    """Supersession relationship between memories.
    
    Tracks when one memory replaces another.
    
    Attributes:
        chain_id: Unique chain identifier
        old_memory_id: Memory being superseded
        new_memory_id: New memory that supersedes
        reason: Reason for supersession
        created_at: Creation timestamp
        created_by: Who created this relationship
        is_active: Whether this relationship is active
        scope: Scope of supersession (optional)
    """
    
    chain_id: str = field(default_factory=lambda: f"sc_{uuid.uuid4().hex[:12]}")
    old_memory_id: str = ""
    new_memory_id: str = ""
    reason: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_by: str = ""
    is_active: bool = True
    scope: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "chain_id": self.chain_id,
            "old_memory_id": self.old_memory_id,
            "new_memory_id": self.new_memory_id,
            "reason": self.reason,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "is_active": self.is_active,
        }
        if self.scope:
            result["scope"] = self.scope
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SupersessionRecord":
        """Create SupersessionRecord from dictionary."""
        return cls(
            chain_id=data.get("chain_id", f"sc_{uuid.uuid4().hex[:12]}"),
            old_memory_id=data.get("old_memory_id", ""),
            new_memory_id=data.get("new_memory_id", ""),
            reason=data.get("reason", ""),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            created_by=data.get("created_by", ""),
            is_active=data.get("is_active", True),
            scope=data.get("scope"),
        )


@dataclass
class ContextResult:
    """Context retrieval result.
    
    Result of a context retrieval operation.
    
    Attributes:
        project_id: Project identifier
        task_id: Task identifier (if applicable)
        query: Original query (if applicable)
        memories: List of relevant memory cards
        total: Total number of matching memories
        graph_summary: Summary of graph traversal
    """
    
    project_id: str = ""
    task_id: Optional[str] = None
    query: Optional[str] = None
    memories: List[MemoryCard] = field(default_factory=list)
    total: int = 0
    graph_summary: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "project_id": self.project_id,
            "task_id": self.task_id,
            "query": self.query,
            "memories": [m.to_dict() for m in self.memories],
            "total": self.total,
            "graph_summary": self.graph_summary,
        }


def get_memory_type_from_string(type_str: str) -> MemoryType:
    """Convert string to MemoryType enum."""
    type_map = {
        "episodic": MemoryType.EPISODIC,
        "semantic": MemoryType.SEMANTIC,
        "procedural": MemoryType.PROCEDURAL,
        "decision": MemoryType.DECISION,
        "correction": MemoryType.CORRECTION,
        "source": MemoryType.SOURCE,
        "audit": MemoryType.AUDIT,
    }
    return type_map.get(type_str.lower(), MemoryType.SEMANTIC)


def get_memory_status_from_string(status_str: str) -> MemoryStatus:
    """Convert string to MemoryStatus enum."""
    status_map = {
        "active": MemoryStatus.ACTIVE,
        "stale": MemoryStatus.STALE,
        "superseded": MemoryStatus.SUPERSEDED,
        "contradicted": MemoryStatus.CONTRADICTED,
        "archived": MemoryStatus.ARCHIVED,
    }
    return status_map.get(status_str.lower(), MemoryStatus.ACTIVE)


def get_memory_scope_from_string(scope_str: str) -> MemoryScope:
    """Convert string to MemoryScope enum."""
    scope_map = {
        "project": MemoryScope.PROJECT,
        "global": MemoryScope.GLOBAL,
        "user": MemoryScope.USER,
        "agent": MemoryScope.AGENT,
    }
    return scope_map.get(scope_str.lower(), MemoryScope.PROJECT)
