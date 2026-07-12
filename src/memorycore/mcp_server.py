from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .memory_service import MemoryService


class MemoryAccessError(PermissionError):
    """Raised when an MCP client exceeds this server's configured scope."""


class MemoryMCPPolicy:
    """Server-side guardrails for a shared Memorycore database.

    Environment variables are deliberately simple so every MCP host can use the
    same server configuration:

    - MEMORYCORE_READ_ONLY=true blocks add, update, and archive.
    - MEMORYCORE_ALLOWED_PROJECTS=memorycore,hermes limits all access to those
      projects. An unset value permits all projects.
    - MEMORYCORE_REQUIRE_APPROVAL=true stores new writes as ``pending`` until
      a trusted client promotes them to ``active`` with memory_update.
    """

    def __init__(self, *, read_only: bool = False,
                 allowed_projects: set[str] | None = None,
                 require_approval: bool = False) -> None:
        self.read_only = read_only
        self.allowed_projects = allowed_projects
        self.require_approval = require_approval

    @classmethod
    def from_environment(cls) -> "MemoryMCPPolicy":
        raw_projects = os.getenv("MEMORYCORE_ALLOWED_PROJECTS", "")
        projects = {item.strip() for item in raw_projects.split(",") if item.strip()}
        return cls(
            read_only=os.getenv("MEMORYCORE_READ_ONLY", "").lower() in {"1", "true", "yes"},
            allowed_projects=projects or None,
            require_approval=os.getenv("MEMORYCORE_REQUIRE_APPROVAL", "").lower() in {"1", "true", "yes"},
        )

    def check_project(self, project_id: str) -> None:
        if self.allowed_projects is not None and project_id not in self.allowed_projects:
            raise MemoryAccessError(f"project is not allowed by this server: {project_id}")

    def check_write(self) -> None:
        if self.read_only:
            raise MemoryAccessError("Memorycore is configured as read-only")


class MemoryMCPAdapter:
    def __init__(self, service: MemoryService,
                 policy: MemoryMCPPolicy | None = None) -> None:
        self.service = service
        self.policy = policy or MemoryMCPPolicy.from_environment()

    async def memory_add(self, project_id: str, memory_type: str, content: str,
                         summary: str | None = None, tags: list[str] | None = None,
                         created_by: str | None = None,
                         metadata: dict[str, Any] | None = None,
                         client_id: str | None = None,
                         model_provider: str | None = None,
                         model_name: str | None = None,
                         session_id: str | None = None,
                         source_type: str = "manual_import",
                         source_uri: str | None = None,
                         source_id: str | None = None,
                         confidence: float | None = None) -> dict[str, Any]:
        self.policy.check_write()
        self.policy.check_project(project_id)
        return self.service.add_memory(project_id=project_id, memory_type=memory_type,
            content=content, summary=summary, tags=tags, created_by=created_by,
            metadata=metadata, client_id=client_id, model_provider=model_provider,
            model_name=model_name, session_id=session_id, source_type=source_type,
            source_uri=source_uri, source_id=source_id, confidence=confidence,
            status="pending" if self.policy.require_approval else "active").to_dict()

    async def memory_get(self, memory_id: str) -> dict[str, Any] | None:
        memory = self.service.get_memory(memory_id)
        if memory is not None:
            self.policy.check_project(memory.project_id)
        return memory.to_dict() if memory else None

    async def memory_search(self, query: str, project_id: str, limit: int = 10,
                            memory_type: str | None = None) -> list[dict[str, Any]]:
        self.policy.check_project(project_id)
        return [memory.to_dict() for memory in self.service.search_memory(
            query=query, project_id=project_id, limit=limit, memory_type=memory_type)]

    async def memory_retrieve_context(self, query: str, project_id: str, limit: int = 10,
                                      memory_type: str | None = None) -> dict[str, Any]:
        self.policy.check_project(project_id)
        return self.service.retrieve_context(query=query, project_id=project_id,
            limit=limit, memory_type=memory_type)

    async def memory_update(self, memory_id: str, content: str | None = None,
                            summary: str | None = None, tags: list[str] | None = None,
                            metadata: dict[str, Any] | None = None,
                            status: str | None = None,
                            updated_by: str | None = None) -> dict[str, Any] | None:
        self.policy.check_write()
        existing = self.service.get_memory(memory_id)
        if existing is not None:
            self.policy.check_project(existing.project_id)
        memory = self.service.update_memory(memory_id, content=content, summary=summary,
            tags=tags, metadata=metadata, status=status, updated_by=updated_by)
        return memory.to_dict() if memory else None

    async def memory_archive(self, memory_id: str) -> dict[str, Any] | None:
        self.policy.check_write()
        existing = self.service.get_memory(memory_id)
        if existing is not None:
            self.policy.check_project(existing.project_id)
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
