from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .http_auth import StaticTokenVerifier
from .memory_service import MemoryService
from .models import ClientRole, MemoryStatus, validate_client_role


class MemoryAccessError(PermissionError):
    """Raised when an MCP client exceeds this server's configured scope."""


class MemoryMCPPolicy:
    """Server-side guardrails for a shared Memorycore database.

    Environment variables are deliberately simple so every MCP host can use the
    same server configuration:

    - MEMORYCORE_CLIENT_ID and MEMORYCORE_CLIENT_ROLE identify this server
      process. The process, not the MCP caller, supplies this identity.
    - MEMORYCORE_READ_ONLY=true blocks every mutation.
    - MEMORYCORE_ALLOWED_PROJECTS=memorycore,hermes limits all access to those
      projects. An unset value permits all projects.
    - MEMORYCORE_REQUIRE_APPROVAL=true stores new writes as ``pending`` until
      a trusted client promotes them to ``active`` with memory_update.
    """

    def __init__(self, *, read_only: bool = False,
                 allowed_projects: set[str] | None = None,
                 require_approval: bool = False,
                 client_id: str = "memorycore-client",
                 client_role: str = ClientRole.ADMINISTRATOR.value,
                 model_provider: str | None = None,
                 model_name: str | None = None) -> None:
        self.read_only = read_only
        self.allowed_projects = allowed_projects
        self.require_approval = require_approval
        self.client_id = client_id.strip() or "memorycore-client"
        self.client_role = validate_client_role(client_role)
        self.model_provider = model_provider
        self.model_name = model_name

    @classmethod
    def from_environment(cls) -> "MemoryMCPPolicy":
        raw_projects = os.getenv("MEMORYCORE_ALLOWED_PROJECTS", "")
        projects = {item.strip() for item in raw_projects.split(",") if item.strip()}
        return cls(
            read_only=os.getenv("MEMORYCORE_READ_ONLY", "").lower() in {"1", "true", "yes"},
            allowed_projects=projects or None,
            require_approval=os.getenv("MEMORYCORE_REQUIRE_APPROVAL", "").lower() in {"1", "true", "yes"},
            client_id=os.getenv("MEMORYCORE_CLIENT_ID", "memorycore-client"),
            client_role=os.getenv("MEMORYCORE_CLIENT_ROLE", ClientRole.ADMINISTRATOR.value),
            model_provider=os.getenv("MEMORYCORE_MODEL_PROVIDER") or None,
            model_name=os.getenv("MEMORYCORE_MODEL_NAME") or None,
        )

    def check_project(self, project_id: str) -> None:
        if self.allowed_projects is not None and project_id not in self.allowed_projects:
            raise MemoryAccessError(f"project is not allowed by this server: {project_id}")

    def check_mutation(self) -> None:
        if self.read_only:
            raise MemoryAccessError("Memorycore is configured as read-only")

    def require_role(self, *roles: ClientRole) -> None:
        self.check_mutation()
        if self.client_role not in {role.value for role in roles}:
            allowed = ", ".join(role.value for role in roles)
            raise MemoryAccessError(f"role {self.client_role} cannot perform this operation; requires {allowed}")

    def creation_status(self) -> str:
        if self.require_approval or self.client_role == ClientRole.WRITER.value:
            return MemoryStatus.PENDING.value
        return MemoryStatus.ACTIVE.value


class MemoryMCPAdapter:
    def __init__(self, service: MemoryService,
                 policy: MemoryMCPPolicy | None = None,
                 token_verifier: StaticTokenVerifier | None = None) -> None:
        self.service = service
        self._default_policy = policy or MemoryMCPPolicy.from_environment()
        self._token_verifier = token_verifier

    @property
    def policy(self) -> MemoryMCPPolicy:
        """Return request-authenticated HTTP policy, or the stdio policy."""
        if self._token_verifier is None:
            return self._default_policy
        from mcp.server.auth.middleware.auth_context import get_access_token

        access_token = get_access_token()
        if access_token is None:
            raise MemoryAccessError("HTTP request has no authenticated client identity")
        identity = self._token_verifier.identity_for_client(access_token.client_id)
        return MemoryMCPPolicy(
            read_only=identity.read_only,
            allowed_projects=set(identity.allowed_projects) if identity.allowed_projects is not None else None,
            require_approval=identity.require_approval,
            client_id=identity.client_id,
            client_role=identity.client_role,
            model_provider=identity.model_provider,
            model_name=identity.model_name,
        )

    async def memory_add(self, project_id: str, memory_type: str, content: str,
                         summary: str | None = None, tags: list[str] | None = None,
                         metadata: dict[str, Any] | None = None,
                         session_id: str | None = None,
                         source_type: str = "manual_import",
                         source_uri: str | None = None,
                         source_id: str | None = None,
                         confidence: float | None = None) -> dict[str, Any]:
        self.policy.require_role(ClientRole.WRITER, ClientRole.APPROVER, ClientRole.ADMINISTRATOR)
        self.policy.check_project(project_id)
        duplicate = self.service.find_exact_duplicate(project_id=project_id, memory_type=memory_type, content=content)
        if duplicate is not None:
            raise ValueError(f"exact duplicate memory exists: {duplicate.id}")
        return self.service.add_memory(project_id=project_id, memory_type=memory_type,
            content=content, summary=summary, tags=tags, created_by=self.policy.client_id,
            metadata=metadata, client_id=self.policy.client_id,
            model_provider=self.policy.model_provider, model_name=self.policy.model_name,
            session_id=session_id, source_type=source_type,
            source_uri=source_uri, source_id=source_id, confidence=confidence,
            status=self.policy.creation_status()).to_dict()

    async def memory_get(self, memory_id: str) -> dict[str, Any] | None:
        memory = self.service.get_memory(memory_id)
        if memory is not None:
            self.policy.check_project(memory.project_id)
        return memory.to_dict() if memory else None

    async def memory_search(self, query: str, project_id: str, limit: int = 10,
                            memory_type: str | None = None,
                            status: str = "active") -> list[dict[str, Any]]:
        self.policy.check_project(project_id)
        return [memory.to_dict() for memory in self.service.search_memory(
            query=query, project_id=project_id, limit=limit, memory_type=memory_type, status=status)]

    async def memory_retrieve_context(self, query: str, project_id: str, limit: int = 10,
                                      memory_type: str | None = None,
                                      status: str = "active") -> dict[str, Any]:
        self.policy.check_project(project_id)
        return self.service.retrieve_context(query=query, project_id=project_id,
            limit=limit, memory_type=memory_type, status=status)

    async def memory_update(self, memory_id: str, content: str | None = None,
                            summary: str | None = None, tags: list[str] | None = None,
                            metadata: dict[str, Any] | None = None) -> dict[str, Any] | None:
        self.policy.require_role(ClientRole.WRITER, ClientRole.APPROVER, ClientRole.ADMINISTRATOR)
        existing = self.service.get_memory(memory_id)
        if existing is not None:
            self.policy.check_project(existing.project_id)
            if self.policy.client_role == ClientRole.WRITER.value and (
                existing.status != MemoryStatus.PENDING.value or existing.client_id != self.policy.client_id
            ):
                raise MemoryAccessError("writers may only update their own pending memories")
        memory = self.service.update_memory(memory_id, content=content, summary=summary,
            tags=tags, metadata=metadata, updated_by=self.policy.client_id)
        return memory.to_dict() if memory else None

    async def memory_approve(self, memory_id: str) -> dict[str, Any] | None:
        self.policy.require_role(ClientRole.APPROVER, ClientRole.ADMINISTRATOR)
        existing = self.service.get_memory(memory_id)
        if existing is not None:
            self.policy.check_project(existing.project_id)
            if existing.client_id == self.policy.client_id:
                raise MemoryAccessError("a client cannot approve its own memory")
        memory = self.service.approve_memory(memory_id, approved_by=self.policy.client_id)
        return memory.to_dict() if memory else None

    async def memory_reject(self, memory_id: str) -> dict[str, Any] | None:
        self.policy.require_role(ClientRole.APPROVER, ClientRole.ADMINISTRATOR)
        existing = self.service.get_memory(memory_id)
        if existing is not None:
            self.policy.check_project(existing.project_id)
        memory = self.service.reject_memory(memory_id, rejected_by=self.policy.client_id)
        return memory.to_dict() if memory else None

    async def memory_supersede(self, memory_id: str, content: str, summary: str | None = None,
                               tags: list[str] | None = None) -> dict[str, Any]:
        self.policy.require_role(ClientRole.APPROVER, ClientRole.ADMINISTRATOR)
        existing = self.service.get_memory(memory_id)
        if existing is not None:
            self.policy.check_project(existing.project_id)
        return self.service.supersede_memory(memory_id, content=content, summary=summary, tags=tags, updated_by=self.policy.client_id).to_dict()

    async def memory_correct(self, memory_id: str, content: str, summary: str | None = None,
                             tags: list[str] | None = None) -> dict[str, Any]:
        self.policy.require_role(ClientRole.APPROVER, ClientRole.ADMINISTRATOR)
        existing = self.service.get_memory(memory_id)
        if existing is not None:
            self.policy.check_project(existing.project_id)
        return self.service.correct_memory(memory_id, content=content, summary=summary, tags=tags, updated_by=self.policy.client_id).to_dict()

    async def memory_archive(self, memory_id: str) -> dict[str, Any] | None:
        self.policy.require_role(ClientRole.APPROVER, ClientRole.ADMINISTRATOR)
        existing = self.service.get_memory(memory_id)
        if existing is not None:
            self.policy.check_project(existing.project_id)
        memory = self.service.archive_memory(memory_id)
        return memory.to_dict() if memory else None

    async def memory_history(self, memory_id: str, limit: int = 100) -> list[dict[str, Any]]:
        memory = self.service.get_memory(memory_id)
        if memory is not None:
            self.policy.check_project(memory.project_id)
        return self.service.get_memory_history(memory_id, limit)

    async def memory_health(self) -> dict[str, Any]:
        return self.service.health()


def create_server(service: MemoryService, *, token_verifier: StaticTokenVerifier | None = None,
                  public_url: str | None = None) -> FastMCP:
    auth = None
    if token_verifier is not None:
        from mcp.server.auth.settings import AuthSettings
        # A bearer-token connector does not need us to operate an OAuth issuer,
        # but FastMCP requires a valid issuer URL when enabling its auth layer.
        issuer_url = os.getenv("MEMORYCORE_AUTH_ISSUER_URL", public_url or "https://memorycore.invalid")
        auth = AuthSettings(issuer_url=issuer_url, resource_server_url=public_url)
    server = FastMCP(
        "Memorycore",
        instructions=(
            "Shared durable memory for multiple LLM clients. Retrieve active project "
            "memory before writing. Memory identity and permissions are assigned by "
            "the Memorycore service, not supplied by the caller."
        ), token_verifier=token_verifier, auth=auth,
    )
    adapter = MemoryMCPAdapter(service, token_verifier=token_verifier)
    server.tool(name="memory_add")(adapter.memory_add)
    server.tool(name="memory_get")(adapter.memory_get)
    server.tool(name="memory_search")(adapter.memory_search)
    server.tool(name="memory_retrieve_context")(adapter.memory_retrieve_context)
    server.tool(name="memory_update")(adapter.memory_update)
    server.tool(name="memory_approve")(adapter.memory_approve)
    server.tool(name="memory_reject")(adapter.memory_reject)
    server.tool(name="memory_supersede")(adapter.memory_supersede)
    server.tool(name="memory_correct")(adapter.memory_correct)
    server.tool(name="memory_archive")(adapter.memory_archive)
    server.tool(name="memory_history")(adapter.memory_history)
    server.tool(name="memory_health")(adapter.memory_health)
    return server


def default_database_path() -> Path:
    configured_url = os.getenv("MEMORYCORE_DATABASE_URL")
    if configured_url:
        return configured_url  # type: ignore[return-value]
    configured = os.getenv("MEMORYCORE_DB")
    return Path(configured).expanduser() if configured else Path.home() / ".memorycore" / "memorycore.db"


def run_server(database_path: str | Path | None = None, *, transport: str | None = None,
               host: str | None = None, port: int | None = None) -> None:
    """Run one Memorycore service instance.

    ``streamable-http`` is the central-service transport. Stdio remains useful
    for local development and hosts that cannot yet connect to HTTP MCP.
    """
    service = MemoryService(database_path or default_database_path())
    try:
        selected_transport = transport or os.getenv("MEMORYCORE_TRANSPORT", "stdio")
        if selected_transport not in {"stdio", "streamable-http", "sse"}:
            raise ValueError("transport must be stdio, streamable-http, or sse")
        token_verifier = StaticTokenVerifier.from_environment() if selected_transport != "stdio" else None
        if selected_transport != "stdio" and token_verifier is None and os.getenv("MEMORYCORE_ALLOW_INSECURE_HTTP", "").lower() not in {"1", "true", "yes"}:
            raise ValueError(
                "HTTP MCP requires MEMORYCORE_HTTP_TOKENS_FILE. Set MEMORYCORE_ALLOW_INSECURE_HTTP=true only for isolated testing."
            )
        server = create_server(service, token_verifier=token_verifier,
            public_url=os.getenv("MEMORYCORE_PUBLIC_URL") or None)
        if selected_transport == "stdio":
            server.run(transport="stdio")
        else:
            server.settings.host = host or os.getenv("MEMORYCORE_HOST", "127.0.0.1")
            server.settings.port = port or int(os.getenv("MEMORYCORE_PORT", "8000"))
            server.run(transport=selected_transport)
    finally:
        service.close()


def main() -> None:
    run_server(transport=os.getenv("MEMORYCORE_TRANSPORT", "stdio"))


if __name__ == "__main__":
    main()
