#!/usr/bin/env python3
"""Memory Core MCP Server - CozoDB Edition.

MCP server entrypoint exposing memory tools using CozoDB as the primary store.

Architecture: LLM client -> MCP server -> Memorycore controller -> CozoDB

Tools exposed:
- memory.add: Add a new memory
- memory.get: Get a memory by ID
- memory.search: Search memories with FTS
- memory.list_by_project: List memories for a project
- memory.supersede: Create supersession chain
- memory.contradict: Create contradiction chain
- memory.retrieve_context: Get project context
- memory.audit: Get audit logs
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
from .controller import MemoryController, MemoryRecord, MemoryStatus, MemoryType
from .audit_jsonl import JSONLAuditLogger
from .ranking import MemoryRanker, RRFRanker


class MemoryMCPServer:
    """MCP Server for Memory Core with CozoDB backend.
    
    Exposes memory operations as MCP tools.
    """

    def __init__(
        self,
        controller: MemoryController,
        audit_logger: JSONLAuditLogger,
        ranker: MemoryRanker,
    ):
        """Initialize MCP server.
        
        Args:
            controller: Memory controller
            audit_logger: JSONL audit logger
            ranker: RRF ranker
        """
        self.controller = controller
        self.audit_logger = audit_logger
        self.ranker = ranker
        self.server: Optional[Server] = None

    async def initialize(self) -> Dict[str, Any]:
        """Initialize the MCP server."""
        logger.info("Initializing Memory Core MCP Server (CozoDB Edition)")
        
        # Check database health
        health = self.controller.health_check()
        logger.info(f"Database health: {health}")
        
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
            },
            "serverInfo": {
                "name": "memory.exe-core",
                "version": "1.0.0",
                "description": "Memory Core with CozoDB backend",
            },
        }

    def _get_tools(self) -> List[Tool]:
        """Get the list of available tools."""
        return [
            # Core CRUD
            Tool(
                name="memory.add",
                description="Add a new memory record",
                inputSchema={
                    "type": "object",
                    "required": ["project_id", "content"],
                    "properties": {
                        "project_id": {
                            "type": "string",
                            "description": "Project ID to associate with",
                        },
                        "content": {
                            "type": "string",
                            "description": "Memory content",
                        },
                        "created_by": {
                            "type": "string",
                            "default": "",
                            "description": "User/agent creating the memory",
                        },
                        "source_refs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                            "description": "Source references",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                            "description": "Tags for categorization",
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "default": 0.0,
                            "description": "Confidence score",
                        },
                        "memory_type": {
                            "type": "string",
                            "enum": ["fact", "decision", "design", "task", "reference", "warning", "experiment"],
                            "default": "fact",
                            "description": "Type of memory",
                        },
                        "summary": {
                            "type": "string",
                            "default": "",
                            "description": "Brief summary",
                        },
                        "raw_evidence_ref": {
                            "type": "string",
                            "default": "",
                            "description": "Reference to raw evidence",
                        },
                        "trust_score": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "default": 0.0,
                            "description": "Trust score",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["candidate", "accepted", "archived", "rejected"],
                            "default": "candidate",
                            "description": "Memory status",
                        },
                        "memory_id": {
                            "type": "string",
                            "default": "",
                            "description": "Optional memory ID",
                        },
                    },
                },
            ),
            Tool(
                name="memory.get",
                description="Get a memory record by ID",
                inputSchema={
                    "type": "object",
                    "required": ["memory_id"],
                    "properties": {
                        "memory_id": {
                            "type": "string",
                            "description": "Memory ID",
                        },
                    },
                },
            ),
            Tool(
                name="memory.search",
                description="Search memory records with FTS and filters",
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
                        "status": {
                            "type": "string",
                            "enum": ["candidate", "accepted", "archived", "rejected"],
                            "default": "",
                            "description": "Filter by status",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                            "description": "Filter by tags (AND logic)",
                        },
                        "memory_type": {
                            "type": "string",
                            "enum": ["fact", "decision", "design", "task", "reference", "warning", "experiment"],
                            "default": "",
                            "description": "Filter by memory type",
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
                name="memory.list_by_project",
                description="List all memories for a specific project",
                inputSchema={
                    "type": "object",
                    "required": ["project_id"],
                    "properties": {
                        "project_id": {
                            "type": "string",
                            "description": "Project ID",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["candidate", "accepted", "archived", "rejected"],
                            "default": "",
                            "description": "Filter by status",
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
            # Advanced operations
            Tool(
                name="memory.supersede",
                description="Create a supersession chain - new memory replaces old",
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
                            "description": "User creating the chain",
                        },
                    },
                },
            ),
            Tool(
                name="memory.contradict",
                description="Create a contradiction chain - two memories contradict",
                inputSchema={
                    "type": "object",
                    "required": ["memory_a_id", "memory_b_id"],
                    "properties": {
                        "memory_a_id": {
                            "type": "string",
                            "description": "First memory ID",
                        },
                        "memory_b_id": {
                            "type": "string",
                            "description": "Second memory ID",
                        },
                        "resolution_notes": {
                            "type": "string",
                            "default": "",
                            "description": "Notes about the contradiction",
                        },
                        "created_by": {
                            "type": "string",
                            "default": "",
                            "description": "User creating the chain",
                        },
                    },
                },
            ),
            # Context retrieval
            Tool(
                name="memory.retrieve_context",
                description="Get comprehensive context for a project",
                inputSchema={
                    "type": "object",
                    "required": ["project_id"],
                    "properties": {
                        "project_id": {
                            "type": "string",
                            "description": "Project ID",
                        },
                        "query": {
                            "type": "string",
                            "default": "",
                            "description": "Optional search query to filter memories",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 50,
                            "minimum": 1,
                            "maximum": 500,
                            "description": "Maximum recent memories to include",
                        },
                    },
                },
            ),
            # Audit
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
                        "entity_type": {
                            "type": "string",
                            "default": "",
                            "description": "Filter by entity type",
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
            # Project management
            Tool(
                name="project.create",
                description="Create a new project",
                inputSchema={
                    "type": "object",
                    "required": ["project_id", "name"],
                    "properties": {
                        "project_id": {
                            "type": "string",
                            "description": "Project ID",
                        },
                        "name": {
                            "type": "string",
                            "description": "Project name",
                        },
                        "description": {
                            "type": "string",
                            "default": "",
                            "description": "Project description",
                        },
                        "created_by": {
                            "type": "string",
                            "default": "",
                            "description": "User creating the project",
                        },
                    },
                },
            ),
            # Health check
            Tool(
                name="system.health_check",
                description="Check system health",
                inputSchema={
                    "type": "object",
                },
            ),
        ]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> List[Any]:
        """Handle tool calls."""
        logger.info(f"Tool call: {name} with args: {json.dumps(arguments, default=str)}")
        
        try:
            if name == "memory.add":
                return await self._handle_add(arguments)
            elif name == "memory.get":
                return await self._handle_get(arguments)
            elif name == "memory.search":
                return await self._handle_search(arguments)
            elif name == "memory.list_by_project":
                return await self._handle_list_by_project(arguments)
            elif name == "memory.supersede":
                return await self._handle_supersede(arguments)
            elif name == "memory.contradict":
                return await self._handle_contradict(arguments)
            elif name == "memory.retrieve_context":
                return await self._handle_retrieve_context(arguments)
            elif name == "memory.audit":
                return await self._handle_audit(arguments)
            elif name == "project.create":
                return await self._handle_create_project(arguments)
            elif name == "system.health_check":
                return await self._handle_health_check(arguments)
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]
        except Exception as e:
            logger.error(f"Error in tool {name}: {e}", exc_info=True)
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def _handle_add(self, args: Dict[str, Any]) -> List[Any]:
        """Handle memory.add tool call."""
        project_id = args["project_id"]
        content = args["content"]
        created_by = args.get("created_by", "")
        source_refs = args.get("source_refs", [])
        tags = args.get("tags", [])
        confidence = args.get("confidence", 0.0)
        memory_type = args.get("memory_type", MemoryType.FACT)
        summary = args.get("summary", "")
        raw_evidence_ref = args.get("raw_evidence_ref", "")
        trust_score = args.get("trust_score", 0.0)
        status = args.get("status", MemoryStatus.CANDIDATE)
        memory_id = args.get("memory_id")
        
        record = self.controller.add_memory(
            project_id=project_id,
            content=content,
            created_by=created_by,
            source_refs=source_refs,
            tags=tags,
            confidence=confidence,
            memory_type=memory_type,
            summary=summary,
            raw_evidence_ref=raw_evidence_ref,
            trust_score=trust_score,
            status=status,
            memory_id=memory_id,
        )
        
        return [TextContent(type="text", text=json.dumps(record.to_dict(), default=str))]

    async def _handle_get(self, args: Dict[str, Any]) -> List[Any]:
        """Handle memory.get tool call."""
        memory_id = args["memory_id"]
        
        record = self.controller.get_memory(memory_id)
        if record:
            return [TextContent(type="text", text=json.dumps(record.to_dict(), default=str))]
        else:
            return [TextContent(type="text", text=json.dumps({"error": "Memory not found"}))]

    async def _handle_search(self, args: Dict[str, Any]) -> List[Any]:
        """Handle memory.search tool call."""
        query = args.get("query", "")
        project_id = args.get("project_id", "") or None
        status = args.get("status", "") or None
        tags = args.get("tags", [])
        memory_type = args.get("memory_type", "") or None
        limit = args.get("limit", 100)
        offset = args.get("offset", 0)
        
        result = self.controller.search_memories(
            query=query if query else None,
            project_id=project_id,
            status=status,
            tags=tags if tags else None,
            memory_type=memory_type,
            limit=limit,
            offset=offset,
        )
        
        output = {
            "total": result.total,
            "limit": result.limit,
            "offset": result.offset,
            "results": [r.to_dict() for r in result.results],
        }
        if result.scores:
            output["scores"] = result.scores
        
        return [TextContent(type="text", text=json.dumps(output, default=str))]

    async def _handle_list_by_project(self, args: Dict[str, Any]) -> List[Any]:
        """Handle memory.list_by_project tool call."""
        project_id = args["project_id"]
        status = args.get("status", "") or None
        limit = args.get("limit", 100)
        offset = args.get("offset", 0)
        
        result = self.controller.list_by_project(
            project_id=project_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        
        output = {
            "total": result.total,
            "limit": result.limit,
            "offset": result.offset,
            "results": [r.to_dict() for r in result.results],
        }
        
        return [TextContent(type="text", text=json.dumps(output, default=str))]

    async def _handle_supersede(self, args: Dict[str, Any]) -> List[Any]:
        """Handle memory.supersede tool call."""
        old_memory_id = args["old_memory_id"]
        new_memory_id = args["new_memory_id"]
        reason = args["reason"]
        created_by = args.get("created_by", "")
        
        result = self.controller.supersede(
            old_memory_id=old_memory_id,
            new_memory_id=new_memory_id,
            reason=reason,
            created_by=created_by,
        )
        
        return [TextContent(type="text", text=json.dumps(result, default=str))]

    async def _handle_contradict(self, args: Dict[str, Any]) -> List[Any]:
        """Handle memory.contradict tool call."""
        memory_a_id = args["memory_a_id"]
        memory_b_id = args["memory_b_id"]
        resolution_notes = args.get("resolution_notes", "")
        created_by = args.get("created_by", "")
        
        result = self.controller.contradict(
            memory_a_id=memory_a_id,
            memory_b_id=memory_b_id,
            resolution_notes=resolution_notes,
            created_by=created_by,
        )
        
        return [TextContent(type="text", text=json.dumps(result, default=str))]

    async def _handle_retrieve_context(self, args: Dict[str, Any]) -> List[Any]:
        """Handle memory.retrieve_context tool call."""
        project_id = args["project_id"]
        query = args.get("query", "") or None
        limit = args.get("limit", 50)
        
        context = self.controller.retrieve_context(
            project_id=project_id,
            query=query,
            limit=limit,
        )
        
        return [TextContent(type="text", text=json.dumps(context.to_dict(), default=str))]

    async def _handle_audit(self, args: Dict[str, Any]) -> List[Any]:
        """Handle memory.audit tool call."""
        project_id = args.get("project_id", "") or None
        user_id = args.get("user_id", "") or None
        action = args.get("action", "") or None
        entity_type = args.get("entity_type", "") or None
        limit = args.get("limit", 100)
        offset = args.get("offset", 0)
        
        entries, total = self.audit_logger.get_logs_with_total(
            project_id=project_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            limit=limit,
            offset=offset,
        )
        
        output = {
            "total": total,
            "limit": limit,
            "offset": offset,
            "logs": [e.to_dict() for e in entries],
        }
        
        return [TextContent(type="text", text=json.dumps(output, default=str))]

    async def _handle_create_project(self, args: Dict[str, Any]) -> List[Any]:
        """Handle project.create tool call."""
        project_id = args["project_id"]
        name = args["name"]
        description = args.get("description", "")
        created_by = args.get("created_by", "")
        
        result = self.controller.create_project(
            project_id=project_id,
            name=name,
            description=description,
            created_by=created_by,
        )
        
        return [TextContent(type="text", text=json.dumps(result, default=str))]

    async def _handle_health_check(self, args: Dict[str, Any]) -> List[Any]:
        """Handle system.health_check tool call."""
        health = self.controller.health_check()
        
        # Add audit logger status
        health["audit_logger"] = "healthy"
        health["ranker"] = "healthy"
        
        return [TextContent(type="text", text=json.dumps(health, default=str))]


def create_server(
    db_path: str = "memorycore.cozo",
    schema_path: str = "cozodb/schema.cozo",
    audit_log_path: str = "audit.jsonl",
) -> MemoryMCPServer:
    """Create and configure the MCP server.
    
    Args:
        db_path: Path to CozoDB database
        schema_path: Path to CozoDB schema
        audit_log_path: Path to JSONL audit log
        
    Returns:
        Configured MemoryMCPServer
    """
    # Initialize audit logger
    audit_logger = JSONLAuditLogger(log_path=audit_log_path)
    
    # Initialize controller with audit logger
    controller = MemoryController(
        db_path=db_path,
        schema_path=schema_path,
        audit_logger=audit_logger,
    )
    
    # Initialize ranker
    ranker = MemoryRanker()
    
    # Create MCP server
    server = MemoryMCPServer(
        controller=controller,
        audit_logger=audit_logger,
        ranker=ranker,
    )
    
    return server


async def run_server(
    db_path: str = "memorycore.cozo",
    schema_path: str = "cozodb/schema.cozo",
    audit_log_path: str = "audit.jsonl",
    host: str = "127.0.0.1",
    port: int = 8080,
) -> None:
    """Run the MCP server.
    
    Args:
        db_path: Path to CozoDB database
        schema_path: Path to CozoDB schema
        audit_log_path: Path to JSONL audit log
        host: Server host
        port: Server port
    """
    if not MCP_AVAILABLE:
        logger.error("mcp library is required. Install with: pip install mcp")
        sys.exit(1)
    
    server = create_server(db_path, schema_path, audit_log_path)
    
    # Create MCP server instance
    mcp_server = Server(
        name="memory.exe-core",
        version="1.0.0",
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
    logger.info(f"Starting Memory Core MCP Server on {host}:{port}")
    
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
    """Main entrypoint for the MCP server."""
    parser = argparse.ArgumentParser(
        description="Memory Core MCP Server - CozoDB Edition",
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
        "--init-db",
        action="store_true",
        help="Initialize database and exit",
    )
    
    args = parser.parse_args()
    
    # Initialize database only
    if args.init_db:
        try:
            controller = MemoryController(
                db_path=args.db_path,
                schema_path=args.schema_path,
            )
            health = controller.health_check()
            logger.info(f"Database initialized: {health}")
            controller.close()
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            sys.exit(1)
        return
    
    # Run the server
    asyncio.run(run_server(
        db_path=args.db_path,
        schema_path=args.schema_path,
        audit_log_path=args.audit_path,
        host=args.host,
        port=args.port,
    ))


if __name__ == "__main__":
    main()
