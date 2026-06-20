"""Graph Memory Layer for Memorycore v2.

Implements the graph-based memory system that enables structural retrieval.

Graph memory answers questions like:
- What task caused this decision?
- Which file was changed?
- What error happened?
- What fix worked?
- What later correction superseded it?
- Which source supports this?

This provides multi-hop recall instead of flat search.
"""

import json
import logging
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime
import uuid

from .memory_types import (
    GraphNode, GraphEdge, GraphNodeType, GraphEdgeType,
    MemoryCard, MemoryType, MemoryStatus
)

logger = logging.getLogger(__name__)


@dataclass
class GraphTraversalResult:
    """Result of a graph traversal."""
    
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    memory_ids: List[str]  # Memory cards linked to nodes
    depth: int  # Maximum depth reached
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "memory_ids": self.memory_ids,
            "depth": self.depth,
        }


@dataclass
class GraphSummary:
    """Summary of graph structure for a project or task."""
    
    project_id: str
    node_count: int
    edge_count: int
    node_types: Dict[str, int]
    edge_types: Dict[str, int]
    connected_components: int
    memory_cards_linked: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "node_types": self.node_types,
            "edge_types": self.edge_types,
            "connected_components": self.connected_components,
            "memory_cards_linked": self.memory_cards_linked,
        }


class GraphMemory:
    """Graph-based memory layer.
    
    Provides structural relationships between entities (tasks, files, errors, etc.)
    and enables multi-hop retrieval for context understanding.
    
    Supports both in-memory and database-backed storage.
    """
    
    def __init__(self, storage_backend: Any = None):
        """Initialize graph memory.
        
        Args:
            storage_backend: Optional storage backend (CozoDB, SQLite, etc.)
                           If None, uses in-memory storage.
        """
        self.storage = storage_backend
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: Dict[str, GraphEdge] = {}
        self._node_to_memories: Dict[str, List[str]] = {}  # node_id -> memory_ids
        self._memory_to_nodes: Dict[str, List[str]] = {}  # memory_id -> node_ids
        
    def add_node(self, node: GraphNode) -> GraphNode:
        """Add a node to the graph.
        
        Args:
            node: GraphNode to add
            
        Returns:
            The added node (with generated ID if not provided)
        """
        if not node.node_id:
            node.node_id = f"node_{uuid.uuid4().hex[:12]}"
        
        # Store in memory
        self._nodes[node.node_id] = node
        
        # Initialize memory links
        if node.node_id not in self._node_to_memories:
            self._node_to_memories[node.node_id] = []
        
        # Persist if storage backend available
        if self.storage:
            self._persist_node(node)
        
        logger.debug(f"Added graph node: {node.node_id} ({node.node_type})")
        return node
    
    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Get a node by ID.
        
        Args:
            node_id: Node ID
            
        Returns:
            GraphNode or None if not found
        """
        # Try in-memory first
        if node_id in self._nodes:
            return self._nodes[node_id]
        
        # Try storage backend
        if self.storage:
            node = self._load_node(node_id)
            if node:
                self._nodes[node_id] = node
                return node
        
        return None
    
    def update_node(self, node_id: str, updates: Dict[str, Any]) -> Optional[GraphNode]:
        """Update a node.
        
        Args:
            node_id: Node ID
            updates: Dictionary of fields to update
            
        Returns:
            Updated GraphNode or None if not found
        """
        node = self.get_node(node_id)
        if not node:
            return None
        
        for key, value in updates.items():
            if hasattr(node, key):
                setattr(node, key, value)
        
        node.updated_at = datetime.utcnow().isoformat()
        
        # Persist if storage backend available
        if self.storage:
            self._persist_node(node)
        
        logger.debug(f"Updated graph node: {node_id}")
        return node
    
    def delete_node(self, node_id: str) -> bool:
        """Delete a node from the graph.
        
        Args:
            node_id: Node ID
            
        Returns:
            True if deleted, False if not found
        """
        if node_id not in self._nodes:
            if self.storage:
                node = self._load_node(node_id)
                if not node:
                    return False
            else:
                return False
        
        # Remove from in-memory
        if node_id in self._nodes:
            del self._nodes[node_id]
        
        # Remove associated edges
        edges_to_remove = [
            eid for eid, edge in self._edges.items()
            if edge.from_node_id == node_id or edge.to_node_id == node_id
        ]
        for eid in edges_to_remove:
            del self._edges[eid]
        
        # Remove memory links
        if node_id in self._node_to_memories:
            for memory_id in self._node_to_memories[node_id]:
                if memory_id in self._memory_to_nodes:
                    self._memory_to_nodes[memory_id].remove(node_id)
            del self._node_to_memories[node_id]
        
        # Persist deletion if storage backend available
        if self.storage:
            self._delete_node_storage(node_id)
        
        logger.debug(f"Deleted graph node: {node_id}")
        return True
    
    def add_edge(self, edge: GraphEdge) -> GraphEdge:
        """Add an edge to the graph.
        
        Args:
            edge: GraphEdge to add
            
        Returns:
            The added edge (with generated ID if not provided)
        """
        if not edge.edge_id:
            edge.edge_id = f"edge_{uuid.uuid4().hex[:12]}"
        
        # Validate nodes exist
        if edge.from_node_id not in self._nodes:
            if self.storage:
                from_node = self._load_node(edge.from_node_id)
                if from_node:
                    self._nodes[edge.from_node_id] = from_node
                else:
                    raise ValueError(f"From node not found: {edge.from_node_id}")
            else:
                raise ValueError(f"From node not found: {edge.from_node_id}")
        
        if edge.to_node_id not in self._nodes:
            if self.storage:
                to_node = self._load_node(edge.to_node_id)
                if to_node:
                    self._nodes[edge.to_node_id] = to_node
                else:
                    raise ValueError(f"To node not found: {edge.to_node_id}")
            else:
                raise ValueError(f"To node not found: {edge.to_node_id}")
        
        # Store in memory
        self._edges[edge.edge_id] = edge
        
        # Persist if storage backend available
        if self.storage:
            self._persist_edge(edge)
        
        logger.debug(f"Added graph edge: {edge.edge_id} ({edge.edge_type}) from {edge.from_node_id} to {edge.to_node_id}")
        return edge
    
    def get_edge(self, edge_id: str) -> Optional[GraphEdge]:
        """Get an edge by ID.
        
        Args:
            edge_id: Edge ID
            
        Returns:
            GraphEdge or None if not found
        """
        # Try in-memory first
        if edge_id in self._edges:
            return self._edges[edge_id]
        
        # Try storage backend
        if self.storage:
            edge = self._load_edge(edge_id)
            if edge:
                self._edges[edge_id] = edge
                return edge
        
        return None
    
    def get_edges_by_node(self, node_id: str, direction: str = "both") -> List[GraphEdge]:
        """Get edges connected to a node.
        
        Args:
            node_id: Node ID
            direction: "in", "out", or "both"
            
        Returns:
            List of edges connected to the node
        """
        edges = []
        
        for edge in self._edges.values():
            if direction == "out" and edge.from_node_id == node_id:
                edges.append(edge)
            elif direction == "in" and edge.to_node_id == node_id:
                edges.append(edge)
            elif direction == "both" and (edge.from_node_id == node_id or edge.to_node_id == node_id):
                edges.append(edge)
        
        # Load from storage if needed
        if self.storage:
            stored_edges = self._load_edges_by_node(node_id, direction)
            for edge in stored_edges:
                if edge.edge_id not in self._edges:
                    self._edges[edge.edge_id] = edge
                    edges.append(edge)
        
        return edges
    
    def link_memory_to_node(self, memory_id: str, node_id: str) -> bool:
        """Link a memory card to a graph node.
        
        Args:
            memory_id: Memory card ID
            node_id: Graph node ID
            
        Returns:
            True if linked, False if node not found
        """
        if node_id not in self._nodes:
            if self.storage:
                node = self._load_node(node_id)
                if not node:
                    return False
                self._nodes[node_id] = node
            else:
                return False
        
        # Add to node -> memories mapping
        if node_id not in self._node_to_memories:
            self._node_to_memories[node_id] = []
        if memory_id not in self._node_to_memories[node_id]:
            self._node_to_memories[node_id].append(memory_id)
        
        # Add to memory -> nodes mapping
        if memory_id not in self._memory_to_nodes:
            self._memory_to_nodes[memory_id] = []
        if node_id not in self._memory_to_nodes[memory_id]:
            self._memory_to_nodes[memory_id].append(node_id)
        
        # Persist if storage backend available
        if self.storage:
            self._persist_memory_link(memory_id, node_id)
        
        logger.debug(f"Linked memory {memory_id} to node {node_id}")
        return True
    
    def get_memories_for_node(self, node_id: str) -> List[str]:
        """Get memory IDs linked to a node.
        
        Args:
            node_id: Node ID
            
        Returns:
            List of memory IDs
        """
        return self._node_to_memories.get(node_id, [])
    
    def get_nodes_for_memory(self, memory_id: str) -> List[str]:
        """Get node IDs linked to a memory.
        
        Args:
            memory_id: Memory ID
            
        Returns:
            List of node IDs
        """
        return self._memory_to_nodes.get(memory_id, [])
    
    def traverse(
        self,
        start_node_ids: List[str],
        max_hops: int = 3,
        edge_types: Optional[List[str]] = None,
        direction: str = "out"
    ) -> GraphTraversalResult:
        """Traverse the graph from start nodes.
        
        Args:
            start_node_ids: List of node IDs to start from
            max_hops: Maximum number of hops to traverse
            edge_types: Optional list of edge types to follow (None = all)
            direction: "in", "out", or "both"
            
        Returns:
            GraphTraversalResult with nodes, edges, and memory IDs
        """
        visited_nodes: Set[str] = set()
        visited_edges: Set[str] = set()
        result_nodes: List[GraphNode] = []
        result_edges: List[GraphEdge] = []
        result_memory_ids: Set[str] = set()
        
        # Initialize with start nodes
        current_nodes = set(start_node_ids)
        visited_nodes.update(current_nodes)
        
        for hop in range(max_hops + 1):
            next_nodes: Set[str] = set()
            
            for node_id in current_nodes:
                # Add node to results
                node = self.get_node(node_id)
                if node:
                    result_nodes.append(node)
                    # Add linked memories
                    result_memory_ids.update(self._node_to_memories.get(node_id, []))
                
                # Get edges from this node
                edges = self.get_edges_by_node(node_id, direction)
                
                for edge in edges:
                    if edge.edge_id not in visited_edges:
                        # Filter by edge type if specified
                        if edge_types is None or edge.edge_type in edge_types:
                            visited_edges.add(edge.edge_id)
                            result_edges.append(edge)
                            
                            # Add target node for next hop
                            if direction in ["out", "both"]:
                                next_nodes.add(edge.to_node_id)
                            if direction in ["in", "both"]:
                                next_nodes.add(edge.from_node_id)
            
            # Prepare for next hop
            new_nodes = next_nodes - visited_nodes
            visited_nodes.update(new_nodes)
            current_nodes = new_nodes
            
            if not current_nodes:
                break
        
        return GraphTraversalResult(
            nodes=result_nodes,
            edges=result_edges,
            memory_ids=list(result_memory_ids),
            depth=min(hop, max_hops)
        )
    
    def get_context_for_task(
        self,
        task_id: str,
        project_id: str,
        max_hops: int = 3
    ) -> GraphTraversalResult:
        """Get context for a specific task by traversing the graph.
        
        This is the primary method for retrieving structural context.
        
        Args:
            task_id: Task ID
            project_id: Project ID
            max_hops: Maximum number of hops to traverse
            
        Returns:
            GraphTraversalResult with relevant nodes, edges, and memories
        """
        # Find the task node
        task_node = self._find_node(GraphNodeType.TASK, {"name": task_id, "project_id": project_id})
        
        if not task_node:
            # Try to find by ID
            task_node = self.get_node(task_id)
        
        if not task_node:
            logger.warning(f"Task node not found: {task_id}")
            return GraphTraversalResult(nodes=[], edges=[], memory_ids=[], depth=0)
        
        # Traverse from the task node
        result = self.traverse(
            start_node_ids=[task_node.node_id],
            max_hops=max_hops,
            edge_types=[
                GraphEdgeType.TASK_USED,
                GraphEdgeType.TASK_PRODUCED,
                GraphEdgeType.TASK_PART_OF,
                GraphEdgeType.TOOL_TOUCHED,
                GraphEdgeType.TOOL_PRODUCED,
                GraphEdgeType.ERROR_FIXED_BY,
                GraphEdgeType.ERROR_CAUSED_BY,
                GraphEdgeType.DECISION_SUPPORTED_BY,
                GraphEdgeType.DECISION_SCOPED_TO,
                GraphEdgeType.MEMORY_DERIVED_FROM,
                GraphEdgeType.MEMORY_SUPERSEDES,
                GraphEdgeType.MEMORY_CONTRADICTS,
            ],
            direction="both"
        )
        
        return result
    
    def _find_node(self, node_type: str, properties: Dict[str, Any]) -> Optional[GraphNode]:
        """Find a node by type and properties.
        
        Args:
            node_type: Node type to match
            properties: Properties to match
            
        Returns:
            GraphNode or None if not found
        """
        for node in self._nodes.values():
            if node.node_type == node_type:
                match = True
                for key, value in properties.items():
                    if node.properties.get(key) != value:
                        match = False
                        break
                if match:
                    return node
        
        if self.storage:
            return self._find_node_storage(node_type, properties)
        
        return None
    
    def get_summary(self, project_id: str) -> GraphSummary:
        """Get a summary of the graph for a project.
        
        Args:
            project_id: Project ID
            
        Returns:
            GraphSummary with statistics
        """
        node_types: Dict[str, int] = {}
        edge_types: Dict[str, int] = {}
        node_count = 0
        edge_count = 0
        memory_count = 0
        
        for node in self._nodes.values():
            if node.project_id == project_id:
                node_count += 1
                node_types[node.node_type] = node_types.get(node.node_type, 0) + 1
                memory_count += len(self._node_to_memories.get(node.node_id, []))
        
        for edge in self._edges.values():
            # Check if edge is related to project
            from_node = self.get_node(edge.from_node_id)
            to_node = self.get_node(edge.to_node_id)
            if from_node and from_node.project_id == project_id:
                edge_count += 1
                edge_types[edge.edge_type] = edge_types.get(edge.edge_type, 0) + 1
            elif to_node and to_node.project_id == project_id:
                edge_count += 1
                edge_types[edge.edge_type] = edge_types.get(edge.edge_type, 0) + 1
        
        # Count connected components (simplified)
        visited = set()
        components = 0
        for node_id in self._nodes:
            node = self._nodes[node_id]
            if node.project_id == project_id and node_id not in visited:
                components += 1
                # Simple BFS to mark component
                stack = [node_id]
                while stack:
                    current = stack.pop()
                    if current in visited:
                        continue
                    visited.add(current)
                    edges = self.get_edges_by_node(current, "both")
                    for edge in edges:
                        if edge.from_node_id == current:
                            stack.append(edge.to_node_id)
                        else:
                            stack.append(edge.from_node_id)
        
        return GraphSummary(
            project_id=project_id,
            node_count=node_count,
            edge_count=edge_count,
            node_types=node_types,
            edge_types=edge_types,
            connected_components=components,
            memory_cards_linked=memory_count
        )
    
    def build_graph_summary(self, nodes: List[GraphNode]) -> Dict[str, Any]:
        """Build a summary of graph structure from a list of nodes.
        
        Args:
            nodes: List of nodes from traversal
            
        Returns:
            Dictionary with summary information
        """
        node_types: Dict[str, int] = {}
        edge_types: Dict[str, int] = {}
        
        for node in nodes:
            node_types[node.node_type] = node_types.get(node.node_type, 0) + 1
        
        # Get edges between these nodes
        node_ids = {n.node_id for n in nodes}
        for edge in self._edges.values():
            if edge.from_node_id in node_ids and edge.to_node_id in node_ids:
                edge_types[edge.edge_type] = edge_types.get(edge.edge_type, 0) + 1
        
        return {
            "node_count": len(nodes),
            "edge_count": sum(edge_types.values()),
            "node_types": node_types,
            "edge_types": edge_types,
        }
    
    # Storage backend methods (to be implemented by subclasses or adapters)
    
    def _persist_node(self, node: GraphNode) -> None:
        """Persist a node to storage backend."""
        if self.storage:
            self.storage.create_graph_node(node)
    
    def _load_node(self, node_id: str) -> Optional[GraphNode]:
        """Load a node from storage backend."""
        if self.storage:
            return self.storage.get_graph_node(node_id)
        return None
    
    def _delete_node_storage(self, node_id: str) -> None:
        """Delete a node from storage backend."""
        if self.storage:
            self.storage.delete_graph_node(node_id)
    
    def _persist_edge(self, edge: GraphEdge) -> None:
        """Persist an edge to storage backend."""
        if self.storage:
            self.storage.create_graph_edge(edge)
    
    def _load_edge(self, edge_id: str) -> Optional[GraphEdge]:
        """Load an edge from storage backend."""
        if self.storage:
            return self.storage.get_graph_edge(edge_id)
        return None
    
    def _load_edges_by_node(self, node_id: str, direction: str) -> List[GraphEdge]:
        """Load edges by node from storage backend."""
        if self.storage:
            return self.storage.get_graph_edges_by_node(node_id, direction)
        return []
    
    def _find_node_storage(self, node_type: str, properties: Dict[str, Any]) -> Optional[GraphNode]:
        """Find a node in storage backend."""
        if self.storage:
            return self.storage.find_graph_node(node_type, properties)
        return None
    
    def _persist_memory_link(self, memory_id: str, node_id: str) -> None:
        """Persist memory-node link to storage backend."""
        if self.storage:
            self.storage.create_memory_node_link(memory_id, node_id)
    
    def load_from_storage(self, project_id: Optional[str] = None) -> None:
        """Load all graph data from storage backend."""
        if self.storage:
            nodes = self.storage.get_all_graph_nodes(project_id)
            for node in nodes:
                self._nodes[node.node_id] = node
            
            edges = self.storage.get_all_graph_edges(project_id)
            for edge in edges:
                self._edges[edge.edge_id] = edge
            
            # Load memory links
            links = self.storage.get_all_memory_node_links(project_id)
            for memory_id, node_id in links:
                if node_id not in self._node_to_memories:
                    self._node_to_memories[node_id] = []
                if memory_id not in self._node_to_memories[node_id]:
                    self._node_to_memories[node_id].append(memory_id)
                
                if memory_id not in self._memory_to_nodes:
                    self._memory_to_nodes[memory_id] = []
                if node_id not in self._memory_to_nodes[memory_id]:
                    self._memory_to_nodes[memory_id].append(node_id)
        
        logger.info(f"Loaded {len(self._nodes)} nodes and {len(self._edges)} edges from storage")
    
    def clear(self) -> None:
        """Clear all in-memory graph data."""
        self._nodes.clear()
        self._edges.clear()
        self._node_to_memories.clear()
        self._memory_to_nodes.clear()
        logger.info("Cleared graph memory")


class InMemoryGraphStorage:
    """In-memory storage backend for graph memory.
    
    Used when no persistent storage is configured.
    """
    
    def __init__(self):
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: Dict[str, GraphEdge] = {}
        self.memory_node_links: Dict[str, List[str]] = {}  # memory_id -> [node_ids]
        self.node_memory_links: Dict[str, List[str]] = {}  # node_id -> [memory_ids]
    
    def create_graph_node(self, node: GraphNode) -> GraphNode:
        self.nodes[node.node_id] = node
        return node
    
    def get_graph_node(self, node_id: str) -> Optional[GraphNode]:
        return self.nodes.get(node_id)
    
    def delete_graph_node(self, node_id: str) -> bool:
        if node_id in self.nodes:
            del self.nodes[node_id]
            return True
        return False
    
    def create_graph_edge(self, edge: GraphEdge) -> GraphEdge:
        self.edges[edge.edge_id] = edge
        return edge
    
    def get_graph_edge(self, edge_id: str) -> Optional[GraphEdge]:
        return self.edges.get(edge_id)
    
    def get_graph_edges_by_node(self, node_id: str, direction: str) -> List[GraphEdge]:
        edges = []
        for edge in self.edges.values():
            if direction == "out" and edge.from_node_id == node_id:
                edges.append(edge)
            elif direction == "in" and edge.to_node_id == node_id:
                edges.append(edge)
            elif direction == "both" and (edge.from_node_id == node_id or edge.to_node_id == node_id):
                edges.append(edge)
        return edges
    
    def find_graph_node(self, node_type: str, properties: Dict[str, Any]) -> Optional[GraphNode]:
        for node in self.nodes.values():
            if node.node_type == node_type:
                match = True
                for key, value in properties.items():
                    if node.properties.get(key) != value:
                        match = False
                        break
                if match:
                    return node
        return None
    
    def get_all_graph_nodes(self, project_id: Optional[str] = None) -> List[GraphNode]:
        if project_id:
            return [n for n in self.nodes.values() if n.project_id == project_id]
        return list(self.nodes.values())
    
    def get_all_graph_edges(self, project_id: Optional[str] = None) -> List[GraphEdge]:
        if project_id:
            result = []
            for edge in self.edges.values():
                from_node = self.get_graph_node(edge.from_node_id)
                to_node = self.get_graph_node(edge.to_node_id)
                if (from_node and from_node.project_id == project_id) or \
                   (to_node and to_node.project_id == project_id):
                    result.append(edge)
            return result
        return list(self.edges.values())
    
    def create_memory_node_link(self, memory_id: str, node_id: str) -> None:
        if memory_id not in self.memory_node_links:
            self.memory_node_links[memory_id] = []
        if node_id not in self.memory_node_links[memory_id]:
            self.memory_node_links[memory_id].append(node_id)
        
        if node_id not in self.node_memory_links:
            self.node_memory_links[node_id] = []
        if memory_id not in self.node_memory_links[node_id]:
            self.node_memory_links[node_id].append(memory_id)
    
    def get_all_memory_node_links(self, project_id: Optional[str] = None) -> List[Tuple[str, str]]:
        links = []
        for memory_id, node_ids in self.memory_node_links.items():
            for node_id in node_ids:
                if project_id is None:
                    links.append((memory_id, node_id))
                else:
                    node = self.get_graph_node(node_id)
                    if node and node.project_id == project_id:
                        links.append((memory_id, node_id))
        return links


def create_graph_memory(storage_backend: Any = None) -> GraphMemory:
    """Factory function to create graph memory with appropriate storage.
    
    Args:
        storage_backend: Optional storage backend
        
    Returns:
        GraphMemory instance
    """
    if storage_backend is None:
        # Use in-memory storage
        storage = InMemoryGraphStorage()
    else:
        storage = storage_backend
    
    graph = GraphMemory(storage)
    
    # Load from storage if available
    if hasattr(storage, 'get_all_graph_nodes'):
        graph.load_from_storage()
    
    return graph
