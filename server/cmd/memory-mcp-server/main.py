#!/usr/bin/env python3
"""Memory Core MCP Server.

MCP server entrypoint exposing 5 tools:
- memory.search
- memory.write_candidate
- memory.get_project_context
- memory.open_raw
- memory.audit

Architecture: MCP Gateway -> Policy Layer -> Memory Engine -> Storage
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

# Try to import mcp library
try:
    from mcp.server import Server
    from mcp.server.models import InitializationOptions
    from mcp.types import TextContent, ImageContent, EmbeddedResource, Tool
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logger.warning("mcp library not found. Install with: pip install mcp")

# Local imports
# Add the server directory to the path
server_dir = str(Path(__file__).parent.parent)
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from storage import Storage, MemoryRecord
from memory_engine import MemoryEngine, MemoryStatus
from policy import PolicyEnforcer, PolicyEngine
from audit import AuditLogger


class MemoryMCPServer:
    """MCP Server for Memory Core.
    
    Exposes 5 tools as specified:
    - memory.search: Search memory records
    - memory.write_candidate: Write a new memory candidate
    - memory.get_project_context: Get comprehensive project context
    - memory.open_raw: Get raw memory content
    - memory.audit: Get audit log entries
    """

    def __init__(self, storage: Storage, engine: MemoryEngine):
        """Initialize MCP server.
        
        Args:
            storage: Storage backend
            engine: Memory engine
        """
        self.storage = storage
        self.engine = engine
        self.server: Optional[Server] = None

    async def initialize(self) -> Dict[str, Any]:
        """Initialize the MCP server."""
        logger.info("Initializing Memory Core MCP Server")
        
        # Initialize storage schema
        logger.info("Storage initialized with schema")
        
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
            },
            "serverInfo": {
                "name": "memory.exe-core",
                "version": "0.1.0",
            },
        }

    def _get_tools(self) -> List[Tool]:
        """Get the list of available tools."""
        return [
            Tool(
                name="memory.search",
                description="Search memory records with optional filters",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Full-text search query",
                        },
                        "project_id": {
                            "type": "string",
                            "description": "Filter by project ID",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["candidate", "accepted", "archived"],
                            "description": "Filter by memory status",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Filter by tags (AND logic)",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 100,
                            "minimum": 1,
                            "maximum": 1000,
                            "description": "Maximum number of results",
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
                name="memory.write_candidate",
                description="Write a new memory candidate",
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
                        "source_refs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Source references for the memory",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Tags for categorization",
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "default": 0.0,
                            "description": "Confidence score (0.0 to 1.0)",
                        },
                        "memory_id": {
                            "type": "string",
                            "description": "Optional memory ID (generated if not provided)",
                        },
                    },
                },
            ),
            Tool(
                name="memory.get_project_context",
                description="Get comprehensive context for a project",
                inputSchema={
                    "type": "object",
                    "required": ["project_id"],
                    "properties": {
                        "project_id": {
                            "type": "string",
                            "description": "Project ID",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 50,
                            "minimum": 1,
                            "maximum": 500,
                            "description": "Maximum number of recent memories to include",
                        },
                    },
                },
            ),
            Tool(
                name="memory.open_raw",
                description="Get raw memory content by ID",
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
                name="memory.audit",
                description="Get audit log entries",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": {
                            "type": "string",
                            "description": "Filter by project ID",
                        },
                        "user_id": {
                            "type": "string",
                            "description": "Filter by user ID",
                        },
                        "action": {
                            "type": "string",
                            "description": "Filter by action type (read, write, delete, update)",
                        },
                        "limit": {
                            "type": "integer",
                            "default": 100,
                            "minimum": 1,
                            "maximum": 1000,
                            "description": "Maximum number of results",
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
        ]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> List[Any]:
        """Handle tool calls.
        
        Args:
            name: Tool name
            arguments: Tool arguments
            
        Returns:
            List of content items (text, images, etc.)
        """
        logger.info(f"Tool call: {name} with args: {json.dumps(arguments, default=str)}")
        
        try:
            if name == "memory.search":
                return await self._handle_search(arguments)
            elif name == "memory.write_candidate":
                return await self._handle_write_candidate(arguments)
            elif name == "memory.get_project_context":
                return await self._handle_get_project_context(arguments)
            elif name == "memory.open_raw":
                return await self._handle_open_raw(arguments)
            elif name == "memory.audit":
                return await self._handle_audit(arguments)
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]
        except Exception as e:
            logger.error(f"Error in tool {name}: {e}", exc_info=True)
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def _handle_search(self, args: Dict[str, Any]) -> List[Any]:
        """Handle memory.search tool call."""
        query = args.get("query")
        project_id = args.get("project_id")
        status = args.get("status")
        tags = args.get("tags")
        limit = args.get("limit", 100)
        offset = args.get("offset", 0)
        
        # Extract user_id from context if available
        user_id = args.get("user_id", "")
        
        result = self.engine.search(
            query=query,
            project_id=project_id,
            status=status,
            tags=tags,
            limit=limit,
            offset=offset,
            user_id=user_id,
        )
        
        # Format results
        output = {
            "total": result.total,
            "limit": result.limit,
            "offset": result.offset,
            "results": [r.to_dict() for r in result.results],
        }
        
        return [TextContent(type="text", text=json.dumps(output, default=str))]

    async def _handle_write_candidate(self, args: Dict[str, Any]) -> List[Any]:
        """Handle memory.write_candidate tool call."""
        project_id = args["project_id"]
        content = args["content"]
        source_refs = args.get("source_refs", [])
        tags = args.get("tags", [])
        confidence = args.get("confidence", 0.0)
        memory_id = args.get("memory_id")
        
        # Extract user_id from context
        user_id = args.get("user_id", "")
        
        record = self.engine.write_candidate(
            project_id=project_id,
            content=content,
            source_refs=source_refs,
            tags=tags,
            confidence=confidence,
            user_id=user_id,
            memory_id=memory_id,
        )
        
        return [TextContent(type="text", text=json.dumps(record.to_dict(), default=str))]

    async def _handle_get_project_context(self, args: Dict[str, Any]) -> List[Any]:
        """Handle memory.get_project_context tool call."""
        project_id = args["project_id"]
        limit = args.get("limit", 50)
        
        # Extract user_id from context
        user_id = args.get("user_id", "")
        
        context = self.engine.get_project_context(
            project_id=project_id,
            user_id=user_id,
            limit=limit,
        )
        
        return [TextContent(type="text", text=json.dumps(context.to_dict(), default=str))]

    async def _handle_open_raw(self, args: Dict[str, Any]) -> List[Any]:
        """Handle memory.open_raw tool call."""
        memory_id = args["memory_id"]
        
        # Extract user_id from context
        user_id = args.get("user_id", "")
        
        raw = self.engine.open_raw(
            memory_id=memory_id,
            user_id=user_id,
        )
        
        if raw:
            return [TextContent(type="text", text=json.dumps(raw, default=str))]
        else:
            return [TextContent(type="text", text=json.dumps({"error": "Memory not found"}))]

    async def _handle_audit(self, args: Dict[str, Any]) -> List[Any]:
        """Handle memory.audit tool call."""
        project_id = args.get("project_id")
        user_id = args.get("user_id")
        action = args.get("action")
        limit = args.get("limit", 100)
        offset = args.get("offset", 0)
        
        # Extract requester_id from context
        requester_id = args.get("requester_id", "")
        
        logs, total = self.engine.get_audit_log(
            project_id=project_id,
            user_id=user_id,
            action=action,
            limit=limit,
            offset=offset,
            requester_id=requester_id,
        )
        
        output = {
            "total": total,
            "limit": limit,
            "offset": offset,
            "logs": logs,
        }
        
        return [TextContent(type="text", text=json.dumps(output, default=str))]


def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from YAML file."""
    import yaml
    
    with open(config_path, "r") as f:
        return yaml.safe_load(f) or {}


def create_server(config: Dict[str, Any]) -> MemoryMCPServer:
    """Create and configure the MCP server.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Configured MemoryMCPServer
    """
    # Get storage configuration
    storage_config = config.get("storage", {})
    db_path = storage_config.get("dsn", "file:memorycore.db")
    
    # Initialize storage
    storage = Storage(db_path=db_path)
    
    # Initialize audit logger
    audit_logger = AuditLogger(storage=storage)
    
    # Initialize policy engine and enforcer
    policy_engine = PolicyEngine(storage=storage)
    policy_enforcer = PolicyEnforcer(storage=storage, audit_logger=audit_logger)
    
    # Initialize memory engine
    engine = MemoryEngine(
        storage=storage,
        audit_logger=audit_logger,
        policy_enforcer=policy_enforcer,
    )
    
    # Create MCP server
    server = MemoryMCPServer(storage=storage, engine=engine)
    
    return server


async def run_server(config: Dict[str, Any]) -> None:
    """Run the MCP server.
    
    Args:
        config: Configuration dictionary
    """
    if not MCP_AVAILABLE:
        logger.error("mcp library is required. Install with: pip install mcp")
        sys.exit(1)
    
    server = create_server(config)
    
    # Get server configuration
    server_config = config.get("server", {})
    host = server_config.get("host", "127.0.0.1")
    port = server_config.get("port", 8080)
    
    # Create MCP server instance
    mcp_server = Server(
        name="memory.exe-core",
        version="0.1.0",
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
        description="Memory Core MCP Server - Phase 1 MVP",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to configuration YAML file",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Database path (overrides config)",
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
    
    # Load configuration
    config: Dict[str, Any] = {}
    if args.config:
        config = load_config(args.config)
    
    # Override with command-line args
    if args.db_path:
        config.setdefault("storage", {})["dsn"] = args.db_path
    if args.host:
        config.setdefault("server", {})["host"] = args.host
    if args.port:
        config.setdefault("server", {})["port"] = args.port
    
    # Initialize database only
    if args.init_db:
        storage_config = config.get("storage", {})
        db_path = storage_config.get("dsn", "file:memorycore.db")
        storage = Storage(db_path=db_path)
        logger.info(f"Database initialized at: {db_path}")
        storage.close()
        return
    
    # Run the server
    asyncio.run(run_server(config))


if __name__ == "__main__":
    main()
