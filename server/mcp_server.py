"""Memorycore MCP Server

Exposes memory operations via MCP protocol.
"""

import asyncio
import argparse
from typing import Any, Dict, List, Optional
from mcp.server import Server
from mcp.server.models import InitializationOptions

from server.controller import MemoryController, MemoryType, MemoryStatus
from server.consolidator import MemoryConsolidator
from server.audit_jsonl import JSONLAuditLogger

server = Server("memorycore")

controller: Optional[MemoryController] = None
consolidator: Optional[MemoryConsolidator] = None
audit_logger: Optional[JSONLAuditLogger] = None


@server.list_tools()
def handle_list_tools() -> List[Dict[str, Any]]:
    return [
        {
            "name": "memory.add",
            "description": "Add a new memory card",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "Project ID"},
                    "content": {"type": "string", "description": "Memory content"},
                    "memory_type": {
                        "type": "string",
                        "enum": list(MemoryType.values()),
                        "description": "Memory type"
                    },
                    "summary": {"type": "string", "description": "Brief summary"},
                    "evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Evidence references"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags"
                    },
                    "created_by": {"type": "string", "description": "Creator"}
                },
                "required": ["project_id", "content"]
            }
        },
        {
            "name": "memory.get",
            "description": "Get a memory by ID",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string", "description": "Memory ID"}
                },
                "required": ["memory_id"]
            }
        },
        {
            "name": "memory.search",
            "description": "Search memories with FTS",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "project_id": {"type": "string", "description": "Filter by project"},
                    "memory_type": {
                        "type": "string",
                        "enum": list(MemoryType.values()) + [None],
                        "description": "Filter by type"
                    },
                    "status": {
                        "type": "string",
                        "enum": list(MemoryStatus.values()) + [None],
                        "description": "Filter by status"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by tags"
                    },
                    "limit": {"type": "integer", "description": "Max results", "default": 100}
                },
                "required": ["query"]
            }
        },
        {
            "name": "memory.list_by_project",
            "description": "List all memories for a project",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "Project ID"},
                    "memory_type": {
                        "type": "string",
                        "enum": list(MemoryType.values()) + [None],
                        "description": "Filter by type"
                    },
                    "status": {
                        "type": "string",
                        "enum": list(MemoryStatus.values()) + [None],
                        "description": "Filter by status"
                    },
                    "limit": {"type": "integer", "description": "Max results", "default": 100}
                },
                "required": ["project_id"]
            }
        },
        {
            "name": "memory.supersede",
            "description": "Mark a memory as superseded",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "old_memory_id": {"type": "string", "description": "Old memory ID"},
                    "new_memory_id": {"type": "string", "description": "New memory ID"},
                    "reason": {"type": "string", "description": "Reason for supersession"}
                },
                "required": ["old_memory_id", "new_memory_id"]
            }
        },
        {
            "name": "memory.retrieve_context",
            "description": "Get comprehensive project context",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "Project ID"},
                    "limit": {"type": "integer", "description": "Max memories", "default": 50}
                },
                "required": ["project_id"]
            }
        },
        {
            "name": "memory.consolidate",
            "description": "Consolidate raw input into memory card",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "raw_input": {"type": "string", "description": "Raw conversation/task/source"},
                    "project_id": {"type": "string", "description": "Project ID"},
                    "source_ref": {"type": "string", "description": "Source reference"},
                    "created_by": {"type": "string", "description": "Creator", "default": "system"}
                },
                "required": ["raw_input", "project_id", "source_ref"]
            }
        },
        {
            "name": "project.create",
            "description": "Create a new project",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "Project ID"},
                    "name": {"type": "string", "description": "Project name"},
                    "description": {"type": "string", "description": "Description"}
                },
                "required": ["project_id", "name"]
            }
        },
        {
            "name": "project.list",
            "description": "List all projects",
            "inputSchema": {"type": "object"}
        },
        {
            "name": "system.health_check",
            "description": "Check system health",
            "inputSchema": {"type": "object"}
        }
    ]


@server.call_tool()
def handle_call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    global controller, consolidator, audit_logger

    try:
        if name == "memory.add":
            memory = controller.add_memory(
                project_id=arguments["project_id"],
                content=arguments["content"],
                memory_type=arguments.get("memory_type", MemoryType.FACT),
                summary=arguments.get("summary", ""),
                evidence=arguments.get("evidence", []),
                tags=arguments.get("tags", []),
                created_by=arguments.get("created_by", "system")
            )
            return {"memory": memory.to_dict()}

        elif name == "memory.get":
            memory = controller.get_memory(arguments["memory_id"])
            if memory:
                return {"memory": memory.to_dict()}
            return {"error": "Memory not found"}

        elif name == "memory.search":
            results = controller.search_memories(
                query=arguments["query"],
                project_id=arguments.get("project_id"),
                memory_type=arguments.get("memory_type"),
                status=arguments.get("status"),
                tags=arguments.get("tags"),
                limit=arguments.get("limit", 100)
            )
            return {"results": [m.to_dict() for m in results]}

        elif name == "memory.list_by_project":
            results = controller.list_by_project(
                project_id=arguments["project_id"],
                memory_type=arguments.get("memory_type"),
                status=arguments.get("status"),
                limit=arguments.get("limit", 100)
            )
            return {"results": [m.to_dict() for m in results]}

        elif name == "memory.supersede":
            success = controller.supersede(
                old_memory_id=arguments["old_memory_id"],
                new_memory_id=arguments["new_memory_id"],
                reason=arguments.get("reason", ""),
                created_by=arguments.get("created_by", "system")
            )
            return {"success": success}

        elif name == "memory.retrieve_context":
            context = controller.retrieve_context(
                project_id=arguments["project_id"],
                limit=arguments.get("limit", 50)
            )
            return context

        elif name == "memory.consolidate":
            result = consolidator.consolidate(
                raw_input=arguments["raw_input"],
                project_id=arguments["project_id"],
                source_ref=arguments["source_ref"],
                created_by=arguments.get("created_by", "system")
            )
            return {
                "memory": result.memory.to_dict(),
                "superseded_ids": result.superseded_ids,
                "evidence_links": result.evidence_links
            }

        elif name == "project.create":
            project = controller.create_project(
                project_id=arguments["project_id"],
                name=arguments["name"],
                description=arguments.get("description", ""),
                created_by=arguments.get("created_by", "system")
            )
            return {"project": {
                "project_id": project.project_id,
                "name": project.name,
                "description": project.description
            }}

        elif name == "project.list":
            projects = controller.list_projects()
            return {"projects": [{
                "project_id": p.project_id,
                "name": p.name,
                "description": p.description
            } for p in projects]}

        elif name == "system.health_check":
            return controller.health_check()

        else:
            return {"error": f"Unknown tool: {name}"}

    except Exception as e:
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Memorycore MCP Server")
    parser.add_argument("--db-path", type=str, default="memorycore.cozo",
                       help="Path to CozoDB database file")
    parser.add_argument("--schema-path", type=str, default="cozodb/schema.cozo",
                       help="Path to CozoDB schema file")
    parser.add_argument("--audit-path", type=str, default="audit.jsonl",
                       help="Path to audit log file")
    parser.add_argument("--host", type=str, default="0.0.0.0",
                       help="Host to bind to")
    parser.add_argument("--port", type=int, default=8080,
                       help="Port to listen on")
    parser.add_argument("--init-db", action="store_true",
                       help="Initialize database and exit")

    args = parser.parse_args()

    global controller, consolidator, audit_logger

    audit_logger = JSONLAuditLogger(log_path=args.audit_path)
    controller = MemoryController(
        db_path=args.db_path,
        schema_path=args.schema_path,
        audit_logger=audit_logger
    )
    consolidator = MemoryConsolidator(controller)

    if args.init_db:
        print("Database initialized successfully")
        controller.close()
        return

    print(f"Starting Memorycore MCP server on {args.host}:{args.port}")
    server.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
