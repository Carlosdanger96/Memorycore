#!/usr/bin/env python3
"""Memory Core MCP Server v2 - Shared Memory Layer for Agents.

MCP server entrypoint exposing the new Memorycore v2 memory tools.

Architecture:
    Hermes / Codex / Vibe CLI / Agent Radio / Research Agents
        ↓
    MCP Interface (this server)
        ↓
    Memory Engine v2
        ↓
    Graph Memory + Consolidation + Storage

New Tools:
- memory.record_episode: Record raw task logs
- memory.add_card: Add consolidated memory cards
- memory.retrieve_context: Get comprehensive context (graph + vector + text)
- memory.supersede: Create supersession relationships
- memory.audit: Get audit logs
- memory.search: Search memory cards
- memory.consolidate: Consolidate episodes to memory cards
- graph.add_node: Add graph nodes
- graph.add_edge: Add graph edges
- graph.traverse: Traverse the graph

This makes Memorycore the shared memory operating layer for agents,
not just a note store.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Try to import MCP library
try:
    from mcp.server import Server
    from mcp.server.models import InitializationOptions
    from mcp.types import TextContent, Tool
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logger.warning("mcp library not found. Install with: pip install mcp")

# Local imports
server_dir = str(Path(__file__).parent)
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from memory_types import (
    MemoryCard, MemoryType, MemoryStatus, MemoryScope,
    EpisodeRecord, GraphNode, GraphNodeType, GraphEdgeType,
    SupersessionRecord, ContextResult
)
from memory_engine_v2 import MemoryEngineV2, MemoryEngineConfig, create_memory_engine_v2
from graph_memory import GraphMemory, create_graph_memory
from consolidator import Consolidator, create_consolidator
from audit_jsonl import JSONLAuditLogger


class MemoryMCPServerV2:
    """MCP Server for Memory Core v2.
    
    Exposes the new memory operations as MCP tools.
    """

    def __init__(
        self,
        engine: MemoryEngineV2,
        audit_logger: JSONLAuditLogger,
    ):
        """Initialize MCP server v2.
        
        Args:
            engine: Memory Engine v2
            audit_logger: JSONL audit logger
        """
        self.engine = engine
        self.audit_logger = audit_logger
        self.server: Optional[Server] = None

    async def initialize(self) -> Dict[str, Any]:
        """Initialize the MCP server."""
        logger.info("Initializing Memory Core MCP Server v2")
        
        # Check engine health
        health = self.engine.health_check()
        logger.info(f"Engine health: {health}")
        
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
            },
            "serverInfo": {
                "name": "memorycore-v2",
                "version": "2.0.0",
                "description": "Memory Core v2 - Shared Memory Layer for Agents",
            },
        }

    def _get_tools(self) -> List[Tool]:
        """Get the list of available tools."""
        return [
            # ================================================================
            # CORE MEMORY OPERATIONS
            # ================================================================
            
            Tool(
                name="memory.record_episode",
                description="Record a raw episode (task log) for later consolidation",
                inputSchema={
                    "type": "object",
                    "required": ["project_id", "task_id", "raw_log"],
                    "properties": {
                        "project_id": {
                            "type": "string",
                            "description": "Project ID to associate with",
                        },
                        "task_id": {
                            "type": "string",
                            "description": "Task ID for this episode",
                        },
                        "raw_log": {
                            "type": ["string", "object"],
                            "description": "Raw log content (string or JSON object)",
                        },
                        "agent_id": {
                            "type": "string",
                            "default": "",
                            "description": "Agent that performed the task",
                        },
                        "metadata": {
                            "type": "object",
                            "default": {},
                            "description": "Additional metadata",
                        },
                    },
                },
            ),
            
            Tool(
                name="memory.add_card",
                description="Add a new memory card (consolidated memory)",
                inputSchema={
                    "type": "object",
                    "required": ["project", "content"],
                    "properties": {
                        "id": {
                            "type": "string",
                            "default": "",
                            "description": "Optional memory card ID",
                        },
                        "scope": {
                            "type": "string",
                            "enum": ["project", "global", "user", "agent"],
                            "default": "project",
                            "description": "Memory scope",
                        },
                        "project": {
                            "type": "string",
                            "description": "Project identifier",
                        },
                        "type": {
                            "type": "string",
                            "enum": ["episodic", "semantic", "procedural", "decision", "correction", "source", "audit"],
                            "default": "semantic",
                            "description": "Memory type",
                        },
                        "summary": {
                            "type": "string",
                            "default": "",
                            "description": "Brief summary",
                        },
                        "content": {
                            "type": "string",
                            "description": "Full content",
                        },
                        "evidence_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                            "description": "Links to raw evidence",
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "default": 0.0,
                            "description": "Confidence score",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["active", "stale", "superseded", "contradicted", "archived"],
                            "default": "active",
                            "description": "Memory status",
                        },
                        "stale_after": {
                            "type": "string",
                            "default": "",
                            "description": "Expiration timestamp (ISO format)",
                        },
                        "allowed_agents": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                            "description": "Agents that can access this memory",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                            "description": "Tags for categorization",
                        },
                        "metadata": {
                            "type": "object",
                            "default": {},
                            "description": "Additional metadata",
                        },
                    },
                },
            ),
            
            Tool(
                name="memory.retrieve_context",
                description="Retrieve comprehensive context for a project or task",
                inputSchema={
                    "type": "object",
                    "required": ["project_id"],
                    "properties": {
                        "project_id": {
                            "type": "string",
                            "description": "Project ID",
                        },
                        "task_id": {
                            "type": "string",
                            "default": "",
                            "description": "Optional task ID for more specific context",
                        },
                        "query": {
                            "type": "string",
                            "default": "",
                            "description": "Optional search query",
                        },
                        "memory_types": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["episodic", "semantic", "procedural", "decision", "correction", "source", "audit"],
                            },
                            "default": [],
                            "description": "Filter by memory types",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 50,
                            "minimum": 1,
                            "maximum": 500,
                            "description": "Maximum results",
                        },
                    },
                },
            ),
            
            Tool(
                name="memory.supersede",
                description="Create supersession relationship - new memory replaces old",
                inputSchema={
                    "type": "object",
                    "required": ["old_memory_id", "new_memory_id", "reason"],
                    "properties": {
                        "old_memory_id": {
                            "type": "string",
                            "description": "Memory being superseded",
                        },
                        "new_memory_id": {
                            "type": "string",
                            "description": "New memory that supersedes",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Reason for supersession",
                        },
                        "created_by": {
                            "type": "string",
                            "default": "",
                            "description": "User creating the relationship",
                        },
                    },
                },
            ),
            
            Tool(
                name="memory.audit",
                description="Get audit log entries",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": {
                            "type": "string",
                            "default": "",
                            "description": "Filter by project ID",
                        },
                        "user_id": {
                            "type": "string",
                            "default": "",
                            "description": "Filter by user ID",
                        },
                        "action": {
                            "type": "string",
                            "default": "",
                            "description": "Filter by action type",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 100,
                            "minimum": 1,
                            "maximum": 1000,
                            "description": "Maximum results",
                        },
                        "offset": {
                            "type": "integer",
                            "default": 0,
                            "minimum": 0,
                            "description": "Pagination offset",
                        },
                    },
                },
            ),
            
            Tool(
                name="memory.search",
                description="Search memory cards with filters",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "default": "",
                            "description": "Full-text search query",
                        },
                        "project_id": {
                            "type": "string",
                            "default": "",
                            "description": "Filter by project ID",
                        },
                        "memory_types": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["episodic", "semantic", "procedural", "decision", "correction", "source", "audit"],
                            },
                            "default": [],
                            "description": "Filter by memory types",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["active", "stale", "superseded", "contradicted", "archived"],
                            "default": "",
                            "description": "Filter by status",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                            "description": "Filter by tags",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 100,
                            "minimum": 1,
                            "maximum": 1000,
                            "description": "Maximum results",
                        },
                        "offset": {
                            "type": "integer",
                            "default": 0,
                            "minimum": 0,
                            "description": "Pagination offset",
                        },
                    },
                },
            ),
            
            # ================================================================
            # CONSOLIDATION OPERATIONS
            # ================================================================
            
            Tool(
                name="memory.consolidate_episode",
                description="Consolidate a specific episode into memory cards",
                inputSchema={
                    "type": "object",
                    "required": ["episode_id"],
                    "properties": {
                        "episode_id": {
                            "type": "string",
                            "description": "Episode ID to consolidate",
                        },
                    },
                },
            ),
            
            Tool(
                name="memory.consolidate_project",
                description="Consolidate all unconsolidated episodes for a project",
                inputSchema={
                    "type": "object",
                    "required": ["project_id"],
                    "properties": {
                        "project_id": {
                            "type": "string",
                            "description": "Project ID to consolidate",
                        },
                    },
                },
            ),
            
            # ================================================================
            # GRAPH OPERATIONS
            # ================================================================
            
            Tool(
                name="graph.add_node",
                description="Add a node to the memory graph",
                inputSchema={
                    "type": "object",
                    "required": ["node_type", "name"],
                    "properties": {
                        "node_id": {
                            "type": "string",
                            "default": "",
                            "description": "Optional node ID",
                        },
                        "node_type": {
                            "type": "string",
                            "enum": ["task", "project", "file", "command", "tool_call", "error", "fix", "decision", "source", "model_profile", "user_correction", "memory_card"],
                            "description": "Node type",
                        },
                        "name": {
                            "type": "string",
                            "description": "Human-readable name",
                        },
                        "project_id": {
                            "type": "string",
                            "default": "",
                            "description": "Project ID",
                        },
                        "properties": {
                            "type": "object",
                            "default": {},
                            "description": "Additional properties",
                        },
                    },
                },
            ),
            
            Tool(
                name="graph.add_edge",
                description="Add an edge between nodes in the memory graph",
                inputSchema={
                    "type": "object",
                    "required": ["from_node_id", "to_node_id", "edge_type"],
                    "properties": {
                        "edge_id": {
                            "type": "string",
                            "default": "",
                            "description": "Optional edge ID",
                        },
                        "from_node_id": {
                            "type": "string",
                            "description": "Source node ID",
                        },
                        "to_node_id": {
                            "type": "string",
                            "description": "Target node ID",
                        },
                        "edge_type": {
                            "type": "string",
                            "enum": ["used", "produced", "part_of", "touched", "fixed_by", "caused_by", "supported_by", "scoped_to", "derived_from", "supersedes", "contradicts"],
                            "description": "Edge type",
                        },
                        "strength": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "default": 1.0,
                            "description": "Relationship strength",
                        },
                        "description": {
                            "type": "string",
                            "default": "",
                            "description": "Human-readable description",
                        },
                        "created_by": {
                            "type": "string",
                            "default": "",
                            "description": "Who created this edge",
                        },
                    },
                },
            ),
            
            Tool(
                name="graph.traverse",
                description="Traverse the memory graph from a start node",
                inputSchema={
                    "type": "object",
                    "required": ["start_node_id"],
                    "properties": {
                        "start_node_id": {
                            "type": "string",
                            "description": "Node ID to start from",
                        },
                        "max_hops": {
                            "type": "integer",
                            "default": 3,
                            "minimum": 1,
                            "maximum": 10,
                            "description": "Maximum number of hops",
                        },
                        "edge_types": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["used", "produced", "part_of", "touched", "fixed_by", "caused_by", "supported_by", "scoped_to", "derived_from", "supersedes", "contradicts"],
                            },
                            "default": [],
                            "description": "Filter by edge types (empty = all)",
                        },
                    },
                },
            ),
            
            Tool(
                name="graph.get_summary",
                description="Get a summary of the graph for a project",
                inputSchema={
                    "type": "object",
                    "required": ["project_id"],
                    "properties": {
                        "project_id": {
                            "type": "string",
                            "description": "Project ID",
                        },
                    },
                },
            ),
            
            # ================================================================
            # SYSTEM OPERATIONS
            # ================================================================
            
            Tool(
                name="system.health_check",
                description="Check system health",
                inputSchema={
                    "type": "object",
                },
            ),
            
            Tool(
                name="system.get_config",
                description="Get current configuration",
                inputSchema={
                    "type": "object",
                },
            ),
        ]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> List[Any]:
        """Handle tool calls."""
        logger.info(f"Tool call: {name} with args: {json.dumps(arguments, default=str)}")
        
        try:
            # Core memory operations
            if name == "memory.record_episode":
                return await self._handle_record_episode(arguments)
            elif name == "memory.add_card":
                return await self._handle_add_card(arguments)
            elif name == "memory.retrieve_context":
                return await self._handle_retrieve_context(arguments)
            elif name == "memory.supersede":
                return await self._handle_supersede(arguments)
            elif name == "memory.audit":
                return await self._handle_audit(arguments)
            elif name == "memory.search":
                return await self._handle_search(arguments)
            
            # Consolidation operations
            elif name == "memory.consolidate_episode":
                return await self._handle_consolidate_episode(arguments)
            elif name == "memory.consolidate_project":
                return await self._handle_consolidate_project(arguments)
            
            # Graph operations
            elif name == "graph.add_node":
                return await self._handle_add_node(arguments)
            elif name == "graph.add_edge":
                return await self._handle_add_edge(arguments)
            elif name == "graph.traverse":
                return await self._handle_traverse(arguments)
            elif name == "graph.get_summary":
                return await self._handle_graph_summary(arguments)
            
            # System operations
            elif name == "system.health_check":
                return await self._handle_health_check(arguments)
            elif name == "system.get_config":
                return await self._handle_get_config(arguments)
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]
        except Exception as e:
            logger.error(f"Error in tool {name}: {e}", exc_info=True)
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    # ================================================================
    # TOOL HANDLERS - Core Memory Operations
    # ================================================================

    async def _handle_record_episode(self, args: Dict[str, Any]) -> List[Any]:
        """Handle memory.record_episode tool call."""
        project_id = args["project_id"]
        task_id = args["task_id"]
        raw_log = args["raw_log"]
        agent_id = args.get("agent_id", "")
        metadata = args.get("metadata", {})
        
        episode = self.engine.record_episode(
            project_id=project_id,
            task_id=task_id,
            raw_log=raw_log,
            agent_id=agent_id,
            metadata=metadata,
        )
        
        return [TextContent(type="text", text=json.dumps(episode.to_dict(), default=str))]

    async def _handle_add_card(self, args: Dict[str, Any]) -> List[Any]:
        """Handle memory.add_card tool call."""
        card_data = {
            "id": args.get("id", ""),
            "scope": args.get("scope", MemoryScope.PROJECT),
            "project": args["project"],
            "type": args.get("type", MemoryType.SEMANTIC),
            "summary": args.get("summary", ""),
            "content": args["content"],
            "evidence_ids": args.get("evidence_ids", []),
            "confidence": args.get("confidence", 0.0),
            "status": args.get("status", MemoryStatus.ACTIVE),
            "stale_after": args.get("stale_after"),
            "allowed_agents": args.get("allowed_agents", []),
            "tags": args.get("tags", []),
            "metadata": args.get("metadata", {}),
        }
        
        card = MemoryCard.from_dict(card_data)
        card = self.engine.add_card(card)
        
        return [TextContent(type="text", text=json.dumps(card.to_dict(), default=str))]

    async def _handle_retrieve_context(self, args: Dict[str, Any]) -> List[Any]:
        """Handle memory.retrieve_context tool call."""
        project_id = args["project_id"]
        task_id = args.get("task_id", "") or None
        query = args.get("query", "") or None
        memory_types = args.get("memory_types", [])
        limit = args.get("limit", 50)
        
        # Convert memory_types to list of strings
        if memory_types:
            memory_types = [mt for mt in memory_types]
        else:
            memory_types = None
        
        context = self.engine.retrieve_context(
            project_id=project_id,
            task_id=task_id,
            query=query,
            memory_types=memory_types,
            limit=limit,
        )
        
        return [TextContent(type="text", text=json.dumps(context.to_dict(), default=str))]

    async def _handle_supersede(self, args: Dict[str, Any]) -> List[Any]:
        """Handle memory.supersede tool call."""
        old_memory_id = args["old_memory_id"]
        new_memory_id = args["new_memory_id"]
        reason = args["reason"]
        created_by = args.get("created_by", "")
        
        record = self.engine.supersede(
            old_memory_id=old_memory_id,
            new_memory_id=new_memory_id,
            reason=reason,
            created_by=created_by,
        )
        
        return [TextContent(type="text", text=json.dumps(record.to_dict(), default=str))]

    async def _handle_audit(self, args: Dict[str, Any]) -> List[Any]:
        """Handle memory.audit tool call."""
        project_id = args.get("project_id", "") or None
        user_id = args.get("user_id", "") or None
        action = args.get("action", "") or None
        limit = args.get("limit", 100)
        offset = args.get("offset", 0)
        
        entries, total = self.engine.audit(
            project_id=project_id,
            user_id=user_id,
            action=action,
            limit=limit,
        )
        
        output = {
            "total": total,
            "limit": limit,
            "offset": offset,
            "logs": entries,
        }
        
        return [TextContent(type="text", text=json.dumps(output, default=str))]

    async def _handle_search(self, args: Dict[str, Any]) -> List[Any]:
        """Handle memory.search tool call."""
        query = args.get("query", "") or None
        project_id = args.get("project_id", "") or None
        memory_types = args.get("memory_types", [])
        status = args.get("status", "") or None
        tags = args.get("tags", [])
        limit = args.get("limit", 100)
        offset = args.get("offset", 0)
        
        results = self.engine.search_memory_cards(
            query=query,
            project_id=project_id,
            memory_types=memory_types if memory_types else None,
            status=status,
            tags=tags if tags else None,
            limit=limit,
            offset=offset,
        )
        
        output = {
            "total": len(results),
            "limit": limit,
            "offset": offset,
            "results": [r.to_dict() for r in results],
        }
        
        return [TextContent(type="text", text=json.dumps(output, default=str))]

    # ================================================================
    # TOOL HANDLERS - Consolidation Operations
    # ================================================================

    async def _handle_consolidate_episode(self, args: Dict[str, Any]) -> List[Any]:
        """Handle memory.consolidate_episode tool call."""
        episode_id = args["episode_id"]
        
        result = self.engine.consolidate_episode(episode_id)
        
        return [TextContent(type="text", text=json.dumps(result.to_dict(), default=str))]

    async def _handle_consolidate_project(self, args: Dict[str, Any]) -> List[Any]:
        """Handle memory.consolidate_project tool call."""
        project_id = args["project_id"]
        
        results = self.engine.consolidate_project(project_id)
        
        output = {
            "project_id": project_id,
            "results": [r.to_dict() for r in results],
            "total_episodes": len(results),
        }
        
        return [TextContent(type="text", text=json.dumps(output, default=str))]

    # ================================================================
    # TOOL HANDLERS - Graph Operations
    # ================================================================

    async def _handle_add_node(self, args: Dict[str, Any]) -> List[Any]:
        """Handle graph.add_node tool call."""
        node_data = {
            "node_id": args.get("node_id", ""),
            "node_type": args["node_type"],
            "name": args["name"],
            "project_id": args.get("project_id", ""),
            "properties": args.get("properties", {}),
        }
        
        node = GraphNode.from_dict(node_data)
        
        if self.engine.graph_memory:
            node = self.engine.graph_memory.add_node(node)
        
        return [TextContent(type="text", text=json.dumps(node.to_dict(), default=str))]

    async def _handle_add_edge(self, args: Dict[str, Any]) -> List[Any]:
        """Handle graph.add_edge tool call."""
        edge_data = {
            "edge_id": args.get("edge_id", ""),
            "from_node_id": args["from_node_id"],
            "to_node_id": args["to_node_id"],
            "edge_type": args["edge_type"],
            "strength": args.get("strength", 1.0),
            "description": args.get("description", ""),
            "created_by": args.get("created_by", ""),
        }
        
        edge = GraphEdge.from_dict(edge_data)
        
        if self.engine.graph_memory:
            edge = self.engine.graph_memory.add_edge(edge)
        
        return [TextContent(type="text", text=json.dumps(edge.to_dict(), default=str))]

    async def _handle_traverse(self, args: Dict[str, Any]) -> List[Any]:
        """Handle graph.traverse tool call."""
        start_node_id = args["start_node_id"]
        max_hops = args.get("max_hops", 3)
        edge_types = args.get("edge_types", [])
        
        result = self.engine.traverse_graph(
            start_node_id=start_node_id,
            max_hops=max_hops,
            edge_types=edge_types if edge_types else None,
        )
        
        return [TextContent(type="text", text=json.dumps(result.to_dict(), default=str))]

    async def _handle_graph_summary(self, args: Dict[str, Any]) -> List[Any]:
        """Handle graph.get_summary tool call."""
        project_id = args["project_id"]
        
        summary = self.engine.get_graph_summary(project_id)
        
        return [TextContent(type="text", text=json.dumps(summary, default=str))]

    # ================================================================
    # TOOL HANDLERS - System Operations
    # ================================================================

    async def _handle_health_check(self, args: Dict[str, Any]) -> List[Any]:
        """Handle system.health_check tool call."""
        health = self.engine.health_check()
        
        # Add audit logger status
        health["audit_logger"] = "healthy" if self.audit_logger else "not_configured"
        
        return [TextContent(type="text", text=json.dumps(health, default=str))]

    async def _handle_get_config(self, args: Dict[str, Any]) -> List[Any]:
        """Handle system.get_config tool call."""
        config = self.engine.config.to_dict()
        
        return [TextContent(type="text", text=json.dumps(config, default=str))]


def create_server_v2(
    db_path: str = "memorycore.cozo",
    schema_path: str = "cozodb/schema.cozo",
    audit_log_path: str = "audit.jsonl",
    use_graph_memory: bool = True,
    use_consolidation: bool = True,
    auto_consolidate: bool = True,
) -> MemoryMCPServerV2:
    """Create and configure the MCP server v2.
    
    Args:
        db_path: Path to CozoDB database
        schema_path: Path to CozoDB schema
        audit_log_path: Path to JSONL audit log
        use_graph_memory: Whether to use graph memory
        use_consolidation: Whether to use consolidation
        auto_consolidate: Whether to auto-consolidate episodes
        
    Returns:
        Configured MemoryMCPServerV2
    """
    # Initialize audit logger
    audit_logger = JSONLAuditLogger(log_path=audit_log_path)
    
    # Initialize engine config
    config = MemoryEngineConfig(
        storage_backend=None,  # Will be set by controller
        use_graph_memory=use_graph_memory,
        use_consolidation=use_consolidation,
        auto_consolidate=auto_consolidate,
    )
    
    # Create engine
    engine = create_memory_engine_v2(
        config=config,
        memory_store=None,  # Will be set by controller
        audit_logger=audit_logger,
    )
    
    # Create MCP server
    server = MemoryMCPServerV2(
        engine=engine,
        audit_logger=audit_logger,
    )
    
    return server


async def run_server_v2(
    db_path: str = "memorycore.cozo",
    schema_path: str = "cozodb/schema.cozo",
    audit_log_path: str = "audit.jsonl",
    host: str = "127.0.0.1",
    port: int = 8080,
    use_graph_memory: bool = True,
    use_consolidation: bool = True,
    auto_consolidate: bool = True,
) -> None:
    """Run the MCP server v2.
    
    Args:
        db_path: Path to CozoDB database
        schema_path: Path to CozoDB schema
        audit_log_path: Path to JSONL audit log
        host: Server host
        port: Server port
        use_graph_memory: Whether to use graph memory
        use_consolidation: Whether to use consolidation
        auto_consolidate: Whether to auto-consolidate episodes
    """
    if not MCP_AVAILABLE:
        logger.error("mcp library is required. Install with: pip install mcp")
        sys.exit(1)
    
    server = create_server_v2(
        db_path=db_path,
        schema_path=schema_path,
        audit_log_path=audit_log_path,
        use_graph_memory=use_graph_memory,
        use_consolidation=use_consolidation,
        auto_consolidate=auto_consolidate,
    )
    
    # Create MCP server instance
    mcp_server = Server(
        name="memorycore-v2",
        version="2.0.0",
    )
    
    # Register tools
    tools = server._get_tools()
    for tool in tools:
        mcp_server.register_tool(tool)
    
    # Set up initialization
    @mcp_server.initialization
    async def on_initialize() -> InitializationOptions:
        init_result = await server.initialize()
        return InitializationOptions(
            serverInfo=init_result.get("serverInfo", {}),
            protocolVersion=init_result.get("protocolVersion", "2024-11-05"),
            capabilities=init_result.get("capabilities", {}),
        )
    
    # Set up tool handler
    @mcp_server.call_tool
    async def on_call_tool(name: str, arguments: Dict[str, Any]) -> List[Any]:
        return await server.call_tool(name, arguments)
    
    # Start the server
    logger.info(f"Starting Memory Core MCP Server v2 on {host}:{port}")
    
    try:
        await mcp_server.start(
            host=host,
            port=port,
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise


def main():
    """Main entrypoint for the MCP server v2."""
    parser = argparse.ArgumentParser(
        description="Memory Core MCP Server v2 - Shared Memory Layer for Agents",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="memorycore.cozo",
        help="Path to CozoDB database file",
    )
    parser.add_argument(
        "--schema-path",
        type=str,
        default="cozodb/schema.cozo",
        help="Path to CozoDB schema file",
    )
    parser.add_argument(
        "--audit-path",
        type=str,
        default="audit.jsonl",
        help="Path to JSONL audit log file",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Server host",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Server port",
    )
    parser.add_argument(
        "--no-graph",
        action="store_true",
        help="Disable graph memory",
    )
    parser.add_argument(
        "--no-consolidation",
        action="store_true",
        help="Disable consolidation",
    )
    parser.add_argument(
        "--no-auto-consolidate",
        action="store_true",
        help="Disable auto-consolidation of episodes",
    )
    
    args = parser.parse_args()
    
    # Run the server
    asyncio.run(run_server_v2(
        db_path=args.db_path,
        schema_path=args.schema_path,
        audit_log_path=args.audit_path,
        host=args.host,
        port=args.port,
        use_graph_memory=not args.no_graph,
        use_consolidation=not args.no_consolidation,
        auto_consolidate=not args.no_auto_consolidate,
    ))


if __name__ == "__main__":
    main()
