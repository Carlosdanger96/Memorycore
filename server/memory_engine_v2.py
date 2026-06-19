"""Memory Engine v2 for Memorycore.

Implements the new memory architecture with:
- Memory types (Episodic, Semantic, Procedural, Decision, Correction, Source, Audit)
- Graph memory for structural relationships
- Consolidation engine for transforming raw logs to memory cards
- Enhanced status system (active, stale, superseded, contradicted, archived)
- Minimal API (record_episode, add_card, retrieve_context, supersede, audit)

Architecture:
    Agent Layer (Hermes, Codex, Vibe, Agent Radio)
        ↓
    MCP API Layer
        ↓
    Memory Engine v2 (this module)
        ↓
    Storage Layer (CozoDB, SQLite)
"""

import json
import logging
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime
import uuid

from server.memory_types import (
    MemoryCard, MemoryType, MemoryStatus, MemoryScope,
    EpisodeRecord, GraphNode, GraphNodeType, GraphEdgeType,
    SupersessionRecord, ContextResult,
    get_memory_type_from_string, get_memory_status_from_string, get_memory_scope_from_string
)
from server.graph_memory import GraphMemory, GraphTraversalResult, create_graph_memory
from server.consolidator import Consolidator, create_consolidator

logger = logging.getLogger(__name__)


@dataclass
class MemoryEngineConfig:
    """Configuration for Memory Engine v2."""
    
    # Storage configuration
    storage_backend: Any = None
    use_graph_memory: bool = True
    use_consolidation: bool = True
    
    # Consolidation settings
    auto_consolidate: bool = True
    conflict_threshold: float = 0.85
    min_confidence: float = 0.6
    
    # Retrieval settings
    max_graph_hops: int = 3
    default_limit: int = 50
    
    # Audit settings
    audit_enabled: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "use_graph_memory": self.use_graph_memory,
            "use_consolidation": self.use_consolidation,
            "auto_consolidate": self.auto_consolidate,
            "conflict_threshold": self.conflict_threshold,
            "min_confidence": self.min_confidence,
            "max_graph_hops": self.max_graph_hops,
            "default_limit": self.default_limit,
            "audit_enabled": self.audit_enabled,
        }


class MemoryEngineV2:
    """Memory Engine v2 - The shared memory operating layer for agents.
    
    This engine implements the new Memorycore architecture with:
    1. Memory types for different kinds of memory
    2. Graph memory for structural relationships
    3. Consolidation for transforming raw logs to durable memory
    4. Enhanced retrieval combining vector, graph, and text search
    5. Comprehensive audit logging
    
    Key principle: Memorycore stores agent experience, not just knowledge.
    Every durable memory should answer one of:
    - What did the agent do?
    - What worked?
    - What failed?
    - What correction was made?
    - What should the agent do differently next time?
    - What source or log proves this?
    """
    
    def __init__(self, config: MemoryEngineConfig = None):
        """Initialize Memory Engine v2.
        
        Args:
            config: MemoryEngineConfig with settings
        """
        self.config = config or MemoryEngineConfig()
        
        # Initialize components
        self.graph_memory: Optional[GraphMemory] = None
        self.consolidator: Optional[Consolidator] = None
        self.memory_store: Any = None
        self.audit_logger: Any = None
        
        # Initialize based on config
        if self.config.use_graph_memory:
            self.graph_memory = create_graph_memory(self.config.storage_backend)
        
        if self.config.use_consolidation and self.graph_memory:
            self.consolidator = create_consolidator(
                graph_memory=self.graph_memory,
                memory_store=self.memory_store,
                conflict_threshold=self.config.conflict_threshold,
                min_confidence=self.config.min_confidence,
            )
        
        logger.info(f"Memory Engine v2 initialized: {self.config.to_dict()}")
    
    def set_memory_store(self, memory_store: Any) -> None:
        """Set the memory store for persistence.
        
        Args:
            memory_store: Memory store implementation
        """
        self.memory_store = memory_store
        
        # Update consolidator if it exists
        if self.consolidator:
            self.consolidator.memory_store = memory_store
    
    def set_audit_logger(self, audit_logger: Any) -> None:
        """Set the audit logger.
        
        Args:
            audit_logger: Audit logger implementation
        """
        self.audit_logger = audit_logger
    
    # ========================================================================
    # CORE API - Minimal Interface
    # ========================================================================
    
    def record_episode(
        self,
        project_id: str,
        task_id: str,
        raw_log: Dict[str, Any],
        agent_id: str,
        metadata: Dict[str, Any] = None
    ) -> EpisodeRecord:
        """Record a raw episode for later consolidation.
        
        Episodes are raw task logs that serve as evidence.
        They can be consolidated into memory cards later.
        
        Args:
            project_id: Project identifier
            task_id: Task identifier
            raw_log: Raw log content (can be dict or string)
            agent_id: Agent that performed the task
            metadata: Additional metadata
            
        Returns:
            EpisodeRecord with generated ID
        """
        # Convert raw_log to string if it's a dict
        if isinstance(raw_log, dict):
            raw_content = json.dumps(raw_log, default=str)
        else:
            raw_content = str(raw_log)
        
        # Create episode record
        episode = EpisodeRecord(
            project_id=project_id,
            task_id=task_id,
            agent_id=agent_id,
            raw_content=raw_content,
            metadata=metadata or {},
        )
        
        # Store episode
        if self.memory_store:
            self.memory_store.create_episode(episode)
        
        # Log the recording
        if self.audit_logger:
            self.audit_logger.log_memory_write(
                memory_id=episode.episode_id,
                user_id=agent_id,
                project_id=project_id,
                details={
                    "operation": "record_episode",
                    "task_id": task_id,
                    "content_length": len(raw_content),
                },
            )
        
        logger.info(f"Recorded episode: {episode.episode_id} for task {task_id}")
        
        # Auto-consolidate if enabled
        if self.config.auto_consolidate and self.consolidator:
            self.consolidator.consolidate_episode(episode)
        
        return episode
    
    def add_card(
        self,
        card: MemoryCard
    ) -> MemoryCard:
        """Add a new memory card (consolidated from episodes).
        
        Memory cards are the durable memory that agents use.
        They should be created by the consolidator from raw episodes.
        
        Args:
            card: MemoryCard to add
            
        Returns:
            The created MemoryCard (with generated ID if not provided)
        """
        if not card.id:
            card.id = f"mc_{uuid.uuid4().hex[:12]}"
        
        if not card.created_at:
            card.created_at = datetime.utcnow().isoformat()
        if not card.updated_at:
            card.updated_at = datetime.utcnow().isoformat()
        
        # Store the card
        if self.memory_store:
            self.memory_store.create_memory_card(card)
        
        # Link to graph if available
        if self.graph_memory and card.project:
            # Create or find project node
            project_node = self.graph_memory._find_node(
                GraphNodeType.PROJECT, {"name": card.project}
            )
            if not project_node:
                project_node = GraphNode(
                    node_type=GraphNodeType.PROJECT,
                    name=card.project,
                    project_id=card.project,
                )
                project_node = self.graph_memory.add_node(project_node)
            
            # Link memory card to project node
            self.graph_memory.link_memory_to_node(card.id, project_node.node_id)
            
            # Create memory card node
            card_node = GraphNode(
                node_type=GraphNodeType.MEMORY_CARD,
                name=card.id,
                project_id=card.project,
                properties={
                    "memory_id": card.id,
                    "type": card.type,
                    "summary": card.summary,
                }
            )
            card_node = self.graph_memory.add_node(card_node)
            
            # Link to project
            edge = GraphEdge(
                from_node_id=project_node.node_id,
                to_node_id=card_node.node_id,
                edge_type=GraphEdgeType.MEMORY_DERIVED_FROM,
                description=f"Memory card {card.id} derived from project",
            )
            self.graph_memory.add_edge(edge)
        
        # Log the addition
        if self.audit_logger:
            self.audit_logger.log_memory_write(
                memory_id=card.id,
                user_id=card.created_by or "system",
                project_id=card.project,
                details={
                    "operation": "add_card",
                    "type": card.type,
                    "status": card.status,
                },
            )
        
        logger.info(f"Added memory card: {card.id} (type: {card.type}, project: {card.project})")
        return card
    
    def retrieve_context(
        self,
        project_id: str,
        task_id: Optional[str] = None,
        query: Optional[str] = None,
        memory_types: Optional[List[str]] = None,
        limit: int = None
    ) -> ContextResult:
        """Retrieve comprehensive context for a project or task.
        
        This is the primary method for getting memory context.
        It combines graph traversal, vector search, and text search.
        
        Args:
            project_id: Project identifier
            task_id: Optional task identifier for more specific context
            query: Optional search query
            memory_types: Optional list of memory types to filter by
            limit: Maximum number of results (default from config)
            
        Returns:
            ContextResult with relevant memories and graph summary
        """
        limit = limit or self.config.default_limit
        
        # Initialize result
        result = ContextResult(
            project_id=project_id,
            task_id=task_id,
            query=query,
        )
        
        # Step 1: Graph traversal (if task_id provided)
        memory_ids_from_graph: Set[str] = set()
        graph_summary: Dict[str, Any] = {}
        
        if task_id and self.graph_memory:
            traversal = self.graph_memory.get_context_for_task(
                task_id=task_id,
                project_id=project_id,
                max_hops=self.config.max_graph_hops
            )
            memory_ids_from_graph.update(traversal.memory_ids)
            graph_summary = self.graph_memory.build_graph_summary(traversal.nodes)
        
        # Step 2: Get memories from graph
        memories_from_graph = []
        if memory_ids_from_graph and self.memory_store:
            memories_from_graph = self.memory_store.get_memory_cards_by_ids(
                list(memory_ids_from_graph)
            )
        
        # Step 3: Text search (if query provided)
        memories_from_text = []
        if query and self.memory_store:
            memories_from_text = self.memory_store.search_memory_cards(
                query=query,
                project_id=project_id,
                memory_types=memory_types,
                limit=limit * 2,  # Get more for fusion
            )
        
        # Step 4: Combine and deduplicate
        all_memories = list(set(
            memories_from_graph + memories_from_text
        ))
        
        # Step 5: Filter by status and type
        filtered_memories = []
        for mem in all_memories:
            # Filter by status (exclude archived)
            if mem.status == MemoryStatus.ARCHIVED:
                continue
            
            # Filter by type if specified
            if memory_types and mem.type not in memory_types:
                continue
            
            filtered_memories.append(mem)
        
        # Step 6: Rank memories (simple ranking for now)
        ranked_memories = self._rank_memories(
            filtered_memories,
            query=query,
            graph_memory_ids=memory_ids_from_graph,
        )
        
        # Step 7: Apply limit
        result.memories = ranked_memories[:limit]
        result.total = len(filtered_memories)
        result.graph_summary = graph_summary
        
        # Log the retrieval
        if self.audit_logger:
            self.audit_logger.log_search(
                user_id="system",
                project_id=project_id,
                query=query or f"retrieve_context(task={task_id})",
                results_count=len(result.memories),
            )
        
        logger.info(f"Retrieved {len(result.memories)} memories for project {project_id}")
        return result
    
    def supersede(
        self,
        old_memory_id: str,
        new_memory_id: str,
        reason: str,
        created_by: str
    ) -> SupersessionRecord:
        """Create supersession relationship between memories.
        
        This marks the old memory as superseded while keeping it for history.
        Memorycore should NEVER silently delete memory.
        
        Args:
            old_memory_id: Memory being superseded
            new_memory_id: New memory that supersedes
            reason: Reason for supersession
            created_by: Who created this relationship
            
        Returns:
            SupersessionRecord
        """
        # Create supersession record
        record = SupersessionRecord(
            old_memory_id=old_memory_id,
            new_memory_id=new_memory_id,
            reason=reason,
            created_by=created_by,
        )
        
        # Update old memory status
        if self.memory_store:
            old_card = self.memory_store.get_memory_card(old_memory_id)
            if old_card:
                old_card.status = MemoryStatus.SUPERSEDED
                old_card.stale_after = datetime.utcnow().isoformat()
                old_card.updated_at = datetime.utcnow().isoformat()
                self.memory_store.update_memory_card(old_card)
        
        # Create graph relationship
        if self.graph_memory:
            # Get or create nodes for both memories
            old_node = self.graph_memory._find_node(
                GraphNodeType.MEMORY_CARD, {"memory_id": old_memory_id}
            )
            if not old_node:
                old_node = GraphNode(
                    node_type=GraphNodeType.MEMORY_CARD,
                    name=old_memory_id,
                    properties={"memory_id": old_memory_id},
                )
                old_node = self.graph_memory.add_node(old_node)
            
            new_node = self.graph_memory._find_node(
                GraphNodeType.MEMORY_CARD, {"memory_id": new_memory_id}
            )
            if not new_node:
                new_node = GraphNode(
                    node_type=GraphNodeType.MEMORY_CARD,
                    name=new_memory_id,
                    properties={"memory_id": new_memory_id},
                )
                new_node = self.graph_memory.add_node(new_node)
            
            # Create supersession edge
            edge = GraphEdge(
                from_node_id=new_node.node_id,
                to_node_id=old_node.node_id,
                edge_type=GraphEdgeType.MEMORY_SUPERSEDES,
                description=f"Supersedes: {reason}",
                created_by=created_by,
            )
            self.graph_memory.add_edge(edge)
        
        # Log the supersession
        if self.audit_logger:
            self.audit_logger.log(
                action="supersede",
                entity_type="memory",
                entity_id=record.chain_id,
                user_id=created_by,
                project_id=self._get_project_for_memory(old_memory_id),
                details={
                    "old_memory_id": old_memory_id,
                    "new_memory_id": new_memory_id,
                    "reason": reason,
                },
            )
        
        logger.info(f"Created supersession: {new_memory_id} supersedes {old_memory_id}")
        return record
    
    def audit(
        self,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get audit log entries.
        
        Args:
            project_id: Filter by project ID
            user_id: Filter by user ID
            action: Filter by action type
            limit: Maximum results
            
        Returns:
            Tuple of (audit entries, total count)
        """
        if not self.audit_logger:
            return [], 0
        
        entries, total = self.audit_logger.get_logs_with_total(
            project_id=project_id,
            user_id=user_id,
            action=action,
            limit=limit,
        )
        
        # Convert to dicts
        result = [e.to_dict() for e in entries]
        
        logger.debug(f"Retrieved {len(result)} audit entries")
        return result, total
    
    # ========================================================================
    # EXTENDED API - Additional Operations
    # ========================================================================
    
    def get_memory_card(self, memory_id: str) -> Optional[MemoryCard]:
        """Get a memory card by ID.
        
        Args:
            memory_id: Memory card ID
            
        Returns:
            MemoryCard or None if not found
        """
        if self.memory_store:
            return self.memory_store.get_memory_card(memory_id)
        return None
    
    def update_memory_card(
        self,
        memory_id: str,
        updates: Dict[str, Any],
        user_id: str = ""
    ) -> Optional[MemoryCard]:
        """Update a memory card.
        
        Args:
            memory_id: Memory card ID
            updates: Dictionary of fields to update
            user_id: User performing the update
            
        Returns:
            Updated MemoryCard or None if not found
        """
        if not self.memory_store:
            return None
        
        card = self.memory_store.get_memory_card(memory_id)
        if not card:
            return None
        
        # Apply updates
        for key, value in updates.items():
            if hasattr(card, key):
                setattr(card, key, value)
        
        card.updated_at = datetime.utcnow().isoformat()
        
        # Update in store
        self.memory_store.update_memory_card(card)
        
        # Log the update
        if self.audit_logger:
            self.audit_logger.log_memory_update(
                memory_id=memory_id,
                user_id=user_id,
                project_id=card.project,
                changes=updates,
            )
        
        logger.info(f"Updated memory card: {memory_id}")
        return card
    
    def search_memory_cards(
        self,
        query: Optional[str] = None,
        project_id: Optional[str] = None,
        memory_types: Optional[List[str]] = None,
        status: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[MemoryCard]:
        """Search memory cards with filters.
        
        Args:
            query: Full-text search query
            project_id: Filter by project ID
            memory_types: Filter by memory types
            status: Filter by status
            tags: Filter by tags
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            List of matching MemoryCard
        """
        if not self.memory_store:
            return []
        
        return self.memory_store.search_memory_cards(
            query=query,
            project_id=project_id,
            memory_types=memory_types,
            status=status,
            tags=tags,
            limit=limit,
            offset=offset,
        )
    
    def get_episode(self, episode_id: str) -> Optional[EpisodeRecord]:
        """Get an episode by ID.
        
        Args:
            episode_id: Episode ID
            
        Returns:
            EpisodeRecord or None if not found
        """
        if self.memory_store:
            return self.memory_store.get_episode(episode_id)
        return None
    
    def consolidate_episode(self, episode_id: str) -> Any:
        """Consolidate a specific episode into memory cards.
        
        Args:
            episode_id: Episode ID
            
        Returns:
            ConsolidationResult
        """
        if not self.consolidator or not self.memory_store:
            raise ValueError("Consolidator or memory store not configured")
        
        episode = self.memory_store.get_episode(episode_id)
        if not episode:
            raise ValueError(f"Episode not found: {episode_id}")
        
        return self.consolidator.consolidate_episode(episode)
    
    def consolidate_project(self, project_id: str) -> List[Any]:
        """Consolidate all unconsolidated episodes for a project.
        
        Args:
            project_id: Project ID
            
        Returns:
            List of ConsolidationResult
        """
        if not self.consolidator:
            raise ValueError("Consolidator not configured")
        
        return self.consolidator.consolidate_project(project_id)
    
    def get_graph_summary(self, project_id: str) -> Dict[str, Any]:
        """Get a summary of the graph for a project.
        
        Args:
            project_id: Project ID
            
        Returns:
            Dictionary with graph statistics
        """
        if not self.graph_memory:
            return {}
        
        summary = self.graph_memory.get_summary(project_id)
        return summary.to_dict()
    
    def traverse_graph(
        self,
        start_node_id: str,
        max_hops: int = 3,
        edge_types: Optional[List[str]] = None
    ) -> GraphTraversalResult:
        """Traverse the graph from a start node.
        
        Args:
            start_node_id: Node ID to start from
            max_hops: Maximum number of hops
            edge_types: Optional list of edge types to follow
            
        Returns:
            GraphTraversalResult
        """
        if not self.graph_memory:
            return GraphTraversalResult(nodes=[], edges=[], memory_ids=[], depth=0)
        
        return self.graph_memory.traverse(
            start_node_ids=[start_node_id],
            max_hops=max_hops,
            edge_types=edge_types,
            direction="both"
        )
    
    # ========================================================================
    # INTERNAL METHODS
    # ========================================================================
    
    def _rank_memories(
        self,
        memories: List[MemoryCard],
        query: Optional[str] = None,
        graph_memory_ids: Optional[Set[str]] = None
    ) -> List[MemoryCard]:
        """Rank memories by relevance.
        
        Simple ranking implementation. For production, use:
        - Vector similarity for semantic ranking
        - Graph centrality for structural importance
        - Confidence scores
        - Recency
        
        Args:
            memories: List of MemoryCard to rank
            query: Optional search query
            graph_memory_ids: Optional set of memory IDs from graph traversal
            
        Returns:
            Ranked list of MemoryCard
        """
        if not memories:
            return []
        
        # Assign scores
        scored_memories = []
        for mem in memories:
            score = 0.0
            
            # Base score from confidence
            score += mem.confidence * 10
            
            # Boost for active status
            if mem.status == MemoryStatus.ACTIVE:
                score += 5
            elif mem.status == MemoryStatus.STALE:
                score += 3
            elif mem.status == MemoryStatus.SUPERSEDED:
                score += 1
            
            # Boost for being in graph traversal
            if graph_memory_ids and mem.id in graph_memory_ids:
                score += 8
            
            # Boost for recency (newer is better)
            if mem.created_at:
                try:
                    age_days = (datetime.utcnow() - datetime.fromisoformat(mem.created_at)).days
                    score += max(0, 10 - age_days)  # 10 points for today, decreasing over time
                except:
                    pass
            
            # Boost for query match (simple text match)
            if query:
                query_lower = query.lower()
                content_lower = mem.content.lower()
                summary_lower = mem.summary.lower()
                
                if query_lower in content_lower or query_lower in summary_lower:
                    score += 5
                
                # Count matching words
                query_words = set(query_lower.split())
                content_words = set(content_lower.split())
                matching_words = len(query_words & content_words)
                score += matching_words * 2
            
            scored_memories.append((score, mem))
        
        # Sort by score (descending)
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        
        return [mem for score, mem in scored_memories]
    
    def _get_project_for_memory(self, memory_id: str) -> Optional[str]:
        """Get the project ID for a memory.
        
        Args:
            memory_id: Memory card ID
            
        Returns:
            Project ID or None
        """
        if self.memory_store:
            card = self.memory_store.get_memory_card(memory_id)
            if card:
                return card.project
        return None
    
    def health_check(self) -> Dict[str, Any]:
        """Perform a health check on the memory engine.
        
        Returns:
            Dictionary with health status
        """
        status = {
            "status": "healthy",
            "version": "2.0",
            "components": {},
        }
        
        # Check graph memory
        if self.graph_memory:
            status["components"]["graph_memory"] = "healthy"
            status["components"]["graph_nodes"] = len(self.graph_memory._nodes)
            status["components"]["graph_edges"] = len(self.graph_memory._edges)
        else:
            status["components"]["graph_memory"] = "disabled"
        
        # Check consolidator
        if self.consolidator:
            status["components"]["consolidator"] = "healthy"
        else:
            status["components"]["consolidator"] = "disabled"
        
        # Check memory store
        if self.memory_store:
            status["components"]["memory_store"] = "healthy"
        else:
            status["components"]["memory_store"] = "not_configured"
        
        # Check audit logger
        if self.audit_logger:
            status["components"]["audit_logger"] = "healthy"
        else:
            status["components"]["audit_logger"] = "not_configured"
        
        return status
    
    def close(self) -> None:
        """Close the memory engine and clean up resources."""
        if self.graph_memory:
            self.graph_memory.clear()
        
        logger.info("Memory Engine v2 closed")


# Factory function
def create_memory_engine_v2(
    config: MemoryEngineConfig = None,
    memory_store: Any = None,
    audit_logger: Any = None
) -> MemoryEngineV2:
    """Create a Memory Engine v2 instance.
    
    Args:
        config: Optional MemoryEngineConfig
        memory_store: Optional memory store
        audit_logger: Optional audit logger
        
    Returns:
        MemoryEngineV2 instance
    """
    engine = MemoryEngineV2(config=config)
    
    if memory_store:
        engine.set_memory_store(memory_store)
    
    if audit_logger:
        engine.set_audit_logger(audit_logger)
    
    return engine
