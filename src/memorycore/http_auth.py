"""Bearer-token identity for the HTTP MCP service.

This module deliberately keeps tokens outside the database.  A connector token
is a deployment secret, while the database is the durable shared-memory store.
Each valid token resolves to a server-controlled policy; callers never choose
their own client ID, role, model provenance, or project scope.
"""

from __future__ import annotations

import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import validate_client_role


class TokenConfigurationError(ValueError):
    """Raised for invalid or unsafe HTTP token configuration."""


@dataclass(frozen=True)
class HTTPClientIdentity:
    token: str
    client_id: str
    client_role: str
    allowed_projects: frozenset[str] | None = None
    read_only: bool = False
    require_approval: bool = False
    model_provider: str | None = None
    model_name: str | None = None

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "HTTPClientIdentity":
        token = raw.get("token")
        client_id = raw.get("client_id")
        if not isinstance(token, str) or len(token.strip()) < 24:
            raise TokenConfigurationError("every HTTP token must be at least 24 characters")
        if not isinstance(client_id, str) or not client_id.strip():
            raise TokenConfigurationError("every HTTP token needs a client_id")
        projects = raw.get("allowed_projects")
        if projects is not None and (not isinstance(projects, list) or not all(isinstance(x, str) and x.strip() for x in projects)):
            raise TokenConfigurationError("allowed_projects must be a list of non-empty project IDs")
        return cls(
            token=token.strip(),
            client_id=client_id.strip(),
            client_role=validate_client_role(str(raw.get("client_role", "reader"))),
            allowed_projects=frozenset(item.strip() for item in projects) if projects is not None else None,
            read_only=bool(raw.get("read_only", False)),
            require_approval=bool(raw.get("require_approval", False)),
            model_provider=raw.get("model_provider") if isinstance(raw.get("model_provider"), str) else None,
            model_name=raw.get("model_name") if isinstance(raw.get("model_name"), str) else None,
        )


class StaticTokenVerifier:
    """MCP SDK TokenVerifier backed by a local JSON secret file."""

    def __init__(self, identities: list[HTTPClientIdentity]) -> None:
        if not identities:
            raise TokenConfigurationError("HTTP authentication needs at least one client token")
        if len({identity.token for identity in identities}) != len(identities):
            raise TokenConfigurationError("HTTP client tokens must be unique")
        if len({identity.client_id for identity in identities}) != len(identities):
            raise TokenConfigurationError("HTTP client IDs must be unique")
        self.identities = identities

    @classmethod
    def from_file(cls, path: str | Path) -> "StaticTokenVerifier":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except OSError as exc:
            raise TokenConfigurationError(f"cannot read HTTP token file: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise TokenConfigurationError(f"HTTP token file is not valid JSON: {exc}") from exc
        records = raw.get("clients") if isinstance(raw, dict) else raw
        if not isinstance(records, list):
            raise TokenConfigurationError("HTTP token file must contain a JSON list or {\"clients\": [...]} ")
        return cls([HTTPClientIdentity.from_mapping(record) for record in records if isinstance(record, dict)])

    @classmethod
    def from_environment(cls) -> "StaticTokenVerifier | None":
        path = os.getenv("MEMORYCORE_HTTP_TOKENS_FILE")
        return cls.from_file(path) if path else None

    def identity_for_client(self, client_id: str) -> HTTPClientIdentity:
        for identity in self.identities:
            if identity.client_id == client_id:
                return identity
        raise TokenConfigurationError("authenticated client is not in the configured token registry")

    async def verify_token(self, token: str):
        # Import only when the optional MCP HTTP dependency is installed.
        from mcp.server.auth.provider import AccessToken

        for identity in self.identities:
            if hmac.compare_digest(token, identity.token):
                return AccessToken(token=token, client_id=identity.client_id, scopes=["memorycore"])
        return None
