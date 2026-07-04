from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .memory_service import MemoryService


class MemoryMCPAdapter:
    def __init__(self, service: MemoryService) -> None:
        self.service = service

    async def memory_add(self, project_id: str, memory_type: str, content: str,
                         summary: str | None = None, tags: list[str] | None = None,
                         created_by: str | None = None,
                         metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.service.add_memory(project_id=project_id, memory_type=memory_type,
            content=content, summary=summary, tags=tags, created_by=created_by,
            metadata=metadata).to_dict()

    async def memory_get(self, memory_id: str) -> dict[str, Any] | None:
        memory = self.service.get_memory(memory_id)
        return memory.to_dict() if memory else None

    async def memory_search(self, query: str, project_id: str, limit: int = 10,
                            memory_type: str | None = None) -> list[dict[str, Any]]:
        return [memory.to_dict() for memory in self.service.search_memory(
            query=query, project_id=project_id, limit=limit, memory_type=memory_type)]

    async def memory_retrieve_context(self, query: str, project_id: str, limit: int = 10,
                                      memory_type: str | None = None) -> dict[str, Any]:
        return self.service.retrieve_context(query=query, project_id=project_id,
            limit=limit, memory_type=memory_type)

    async def memory_update(self, memory_id: str, content: str | None = None,
                            summary: str | None = None, tags: list[str] | None = None,
                            metadata: dict[str, Any] | None = None,
                            status: str | None = None) -> dict[str, Any] | None:
        memory = self.service.update_memory(memory_id, content=content, summary=summary,
            tags=tags, metadata=metadata, status=status)
        return memory.to_dict() if memory else None

    async def memory_archive(self, memory_id: str) -> dict[str, Any] | None:
        memory = self.service.archive_memory(memory_id)
        return memory.to_dict() if memory else None

    async def memory_health(self) -> dict[str, Any]:
        return self.service.health()


def create_server(service: MemoryService) -> FastMCP:
    server = FastMCP("Memorycore")
    adapter = MemoryMCPAdapter(service)
    server.tool(name="memory_add")(adapter.memory_add)
    server.tool(name="memory_get")(adapter.memory_get)
    server.tool(name="memory_search")(adapter.memory_search)
    server.tool(name="memory_retrieve_context")(adapter.memory_retrieve_context)
    server.tool(name="memory_update")(adapter.memory_update)
    server.tool(name="memory_archive")(adapter.memory_archive)
    server.tool(name="memory_health")(adapter.memory_health)
    return server


def default_database_path() -> Path:
    configured = os.getenv("MEMORYCORE_DB")
    return Path(configured).expanduser() if configured else Path.home() / ".memorycore" / "memorycore.db"


def run_server(database_path: str | Path | None = None) -> None:
    service = MemoryService(database_path or default_database_path())
    try:
        create_server(service).run()
    finally:
        service.close()


def main() -> None:
    run_server()


if __name__ == "__main__":
    main()
