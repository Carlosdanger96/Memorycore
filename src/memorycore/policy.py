"""Shared authorization and provenance policy for every Memorycore interface.

CLI commands and MCP tools route through this single contract so both
interfaces obey identical lifecycle, permission, duplicate, and provenance
rules. Adapters must not implement competing rules.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .models import ClientRole, MemoryStatus, validate_client_role

DEFAULT_CLIENT_ID = "memorycore-client"


class MemoryAccessError(PermissionError):
    """Raised when a client exceeds its configured scope."""


@dataclass(frozen=True)
class ClientPolicy:
    """Server-assigned identity and scope for one operation."""

    client_id: str
    client_role: str
    allowed_projects: frozenset[str] | None = None
    read_only: bool = False
    require_approval: bool = False
    model_provider: str | None = None
    model_name: str | None = None

    def check_project(self, project_id: str) -> None:
        if self.allowed_projects is not None and project_id not in self.allowed_projects:
            raise MemoryAccessError(f"project is not allowed by this client: {project_id}")

    def check_mutation(self) -> None:
        if self.read_only:
            raise MemoryAccessError("Memorycore is configured as read-only for this client")

    def require_role(self, *roles: ClientRole) -> None:
        self.check_mutation()
        if self.client_role not in {role.value for role in roles}:
            allowed = ", ".join(role.value for role in roles)
            raise MemoryAccessError(
                f"role {self.client_role} cannot perform this operation; requires {allowed}"
            )

    def creation_status(self) -> str:
        if self.require_approval or self.client_role == ClientRole.WRITER.value:
            return MemoryStatus.PENDING.value
        return MemoryStatus.ACTIVE.value


def policy_from_environment(environ: dict[str, Any] | None = None) -> ClientPolicy:
    env = os.environ if environ is None else environ
    truthy = {"1", "true", "yes"}

    def flag(name: str) -> bool:
        return str(env.get(name, "")).lower() in truthy

    raw_projects = str(env.get("MEMORYCORE_ALLOWED_PROJECTS", ""))
    projects = {item.strip() for item in raw_projects.split(",") if item.strip()}

    def optional(name: str) -> str | None:
        value = env.get(name)
        return str(value).strip() if value else None

    return ClientPolicy(
        client_id=str(env.get("MEMORYCORE_CLIENT_ID", DEFAULT_CLIENT_ID)).strip() or DEFAULT_CLIENT_ID,
        client_role=validate_client_role(str(env.get("MEMORYCORE_CLIENT_ROLE", ClientRole.ADMINISTRATOR.value))),
        allowed_projects=frozenset(projects) if projects else None,
        read_only=flag("MEMORYCORE_READ_ONLY"),
        require_approval=flag("MEMORYCORE_REQUIRE_APPROVAL"),
        model_provider=optional("MEMORYCORE_MODEL_PROVIDER"),
        model_name=optional("MEMORYCORE_MODEL_NAME"),
    )


class DuplicateMemoryError(ValueError):
    """Raised when normalized duplicate content already exists in a live state."""

    def __init__(self, existing: dict[str, Any]) -> None:
        self.existing = existing
        super().__init__(f"exact duplicate memory exists: {existing['id']}")


class RevisionConflictError(ValueError):
    """Raised when an update targets a revision that is no longer current."""

    def __init__(self, memory_id: str, current_revision: int, expected_revision: int) -> None:
        self.memory_id = memory_id
        self.current_revision = current_revision
        self.expected_revision = expected_revision
        super().__init__(
            f"revision conflict for memory {memory_id}: "
            f"expected revision {expected_revision}, current revision is {current_revision}"
        )
