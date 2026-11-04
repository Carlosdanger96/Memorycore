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
from urllib.parse import urlsplit

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


@dataclass(frozen=True)
class OAuthClientPolicy:
    client_id: str
    client_role: str
    allowed_projects: frozenset[str] | None = None
    read_only: bool = False
    require_approval: bool = False
    model_provider: str | None = None
    model_name: str | None = None


class JWKSClientVerifier:
    """Verify issuer-signed JWTs and map the verified subject to local policy."""

    def __init__(self, *, issuer: str, audience: str, jwks_url: str,
                 identities: list[OAuthClientPolicy]) -> None:
        try:
            import jwt
        except ModuleNotFoundError as exc:
            raise TokenConfigurationError("install memorycore[oauth] for JWT verification") from exc
        for label, value in (("issuer", issuer), ("audience", audience), ("JWKS URL", jwks_url)):
            parsed = urlsplit(value)
            if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
                raise TokenConfigurationError(f"OAuth {label} must be an HTTPS URL")
        if not identities or len({item.client_id for item in identities}) != len(identities):
            raise TokenConfigurationError("OAuth clients need unique local identities")
        self.issuer = issuer
        self.audience = audience
        self.identities = {item.client_id: item for item in identities}
        self._jwt = jwt
        self._keys = jwt.PyJWKClient(jwks_url)

    @classmethod
    def from_environment(cls) -> "JWKSClientVerifier | None":
        keys = ("MEMORYCORE_OAUTH_ISSUER", "MEMORYCORE_OAUTH_AUDIENCE",
                "MEMORYCORE_OAUTH_JWKS_URL", "MEMORYCORE_OAUTH_CLIENTS_FILE")
        values = [os.getenv(key) for key in keys]
        if not any(values):
            return None
        if not all(values):
            raise TokenConfigurationError("OAuth requires issuer, audience, JWKS URL, and clients file")
        try:
            records = json.loads(Path(values[3]).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise TokenConfigurationError("cannot read OAuth client policy file") from exc
        if not isinstance(records, list):
            raise TokenConfigurationError("OAuth client policy file must contain a list")
        identities = []
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("client_id"), str) or not record["client_id"].strip():
                raise TokenConfigurationError("every OAuth client policy needs a client_id")
            projects = record.get("allowed_projects")
            if projects is not None and (not isinstance(projects, list) or
                                        not all(isinstance(item, str) and item.strip() for item in projects)):
                raise TokenConfigurationError("allowed_projects must be a list of project IDs")
            identities.append(OAuthClientPolicy(
                client_id=record["client_id"].strip(),
                client_role=validate_client_role(str(record.get("client_role", "reader"))),
                allowed_projects=frozenset(projects) if projects is not None else None,
                read_only=bool(record.get("read_only", False)),
                require_approval=bool(record.get("require_approval", False)),
                model_provider=record.get("model_provider"),
                model_name=record.get("model_name"),
            ))
        return cls(issuer=values[0], audience=values[1], jwks_url=values[2], identities=identities)

    def identity_for_client(self, client_id: str) -> OAuthClientPolicy:
        try:
            return self.identities[client_id]
        except KeyError as exc:
            raise TokenConfigurationError("authenticated subject has no local client policy") from exc

    async def verify_token(self, token: str):
        from mcp.server.auth.provider import AccessToken
        import asyncio

        if len(token) > 8192:
            return None
        try:
            signing_key = await asyncio.to_thread(self._keys.get_signing_key_from_jwt, token)
            claims = self._jwt.decode(
                token, signing_key.key, algorithms=["RS256"],
                issuer=self.issuer, audience=self.audience,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
            client_id = claims["sub"]
            scopes = claims.get("scope", "").split()
            if client_id not in self.identities or "memorycore" not in scopes:
                return None
            return AccessToken(token=token, client_id=client_id,
                               scopes=scopes, expires_at=claims["exp"])
        except (self._jwt.PyJWTError, ValueError, TypeError, KeyError):
            return None
