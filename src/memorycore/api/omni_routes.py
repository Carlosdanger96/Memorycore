from __future__ import annotations

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from ..http_auth import HTTPClientIdentity, StaticTokenVerifier
from ..mcp_server import MemoryAccessError, MemoryMCPAdapter, MemoryMCPPolicy
from ..memory_service import MemoryService


MAX_REQUEST_BYTES = 256 * 1024


def _policy(identity: HTTPClientIdentity) -> MemoryMCPPolicy:
    return MemoryMCPPolicy(
        read_only=identity.read_only,
        allowed_projects=set(identity.allowed_projects) if identity.allowed_projects is not None else None,
        require_approval=identity.require_approval, client_id=identity.client_id,
        client_role=identity.client_role, model_provider=identity.model_provider,
        model_name=identity.model_name,
    )


class OmniAPIRouter:
    def __init__(self, service: MemoryService) -> None:
        self.service = service

    def dispatch(self, method: str, path: str, query: dict[str, list[str]],
                 body: dict[str, Any], identity: HTTPClientIdentity) -> Any:
        adapter = MemoryMCPAdapter(self.service, _policy(identity))
        project_id = self._one(query, "project_id") or body.get("project_id")
        if method == "GET" and path == "/v1/omni/health":
            return asyncio.run(adapter.omni_health())
        if method == "GET" and path == "/v1/omni/openapi.json":
            return openapi_schema()
        if method == "GET" and path == "/v1/omni/behaviors":
            return asyncio.run(adapter.omni_search_behaviors(
                project_id=self._required(project_id, "project_id"),
                query=self._one(query, "query") or "",
                repository=self._one(query, "repository"),
                limit=int(self._one(query, "limit") or 50),
            ))
        if method == "GET" and path.startswith("/v1/omni/behaviors/"):
            behavior_id = path.removeprefix("/v1/omni/behaviors/")
            return asyncio.run(adapter.omni_get_behavior(
                behavior_id, self._required(project_id, "project_id"),
            ))
        if method == "GET" and path.startswith("/v1/omni/trajectories/"):
            return asyncio.run(adapter.omni_get_trajectory(path.rsplit("/", 1)[-1]))
        if method == "GET" and path == "/v1/omni/corrections":
            return asyncio.run(adapter.omni_search_corrections(
                project_id=self._required(project_id, "project_id"),
                task_type=self._required(self._one(query, "task_type"), "task_type"),
                behavior_ids=query.get("behavior_id"), repository=self._one(query, "repository"),
                error_signature=self._one(query, "error_signature"),
                tool_name=self._one(query, "tool_name"),
                limit=int(self._one(query, "limit") or 10),
            ))
        if method == "POST" and path == "/v1/omni/repository-scans":
            return asyncio.run(adapter.omni_scan_repository(
                self._required(body.get("repository_path"), "repository_path"),
                self._required(project_id, "project_id"), body.get("repository"),
            ))
        if method == "POST" and path == "/v1/omni/trajectories":
            return asyncio.run(adapter.omni_create_trajectory(
                self._required(project_id, "project_id"),
                self._required(body.get("task_type"), "task_type"),
                self._required(body.get("task_description"), "task_description"),
                self._required(body.get("agent_id"), "agent_id"),
                self._required(body.get("repository"), "repository"),
                str(body.get("source_revision") or "unversioned"),
            ))
        if method == "POST" and path.endswith("/events") and path.startswith("/v1/omni/trajectories/"):
            trajectory_id = path.split("/")[-2]
            return asyncio.run(adapter.omni_record_trajectory_event(
                trajectory_id, self._required(body.get("event_type"), "event_type"),
                int(self._required(body.get("sequence"), "sequence")),
                request_id=body.get("request_id"), behavior_ids=body.get("behavior_ids"),
                memory_ids=body.get("memory_ids"), correction_ids=body.get("correction_ids"),
                tool_name=body.get("tool_name"), input_data=body.get("input"),
                output_data=body.get("output"), error_signature=body.get("error_signature"),
                outcome=body.get("outcome"),
            ))
        if method == "POST" and path == "/v1/omni/corrections":
            return asyncio.run(adapter.omni_propose_correction(
                self._required(project_id, "project_id"),
                self._required(body.get("task_type"), "task_type"),
                body.get("behavior_ids") or [], self._required(body.get("repository"), "repository"),
                self._required(body.get("operation"), "operation"),
                self._required(body.get("instruction"), "instruction"),
                body.get("evidence_trajectory_ids") or [], error_signature=body.get("error_signature"),
                trigger=body.get("trigger"), confidence=float(body.get("confidence", 0.7)),
            ))
        if method == "POST" and path.endswith("/approve") and path.startswith("/v1/omni/corrections/"):
            return asyncio.run(adapter.omni_approve_correction(path.split("/")[-2]))
        if method == "POST" and path.endswith("/outcomes") and path.startswith("/v1/omni/corrections/"):
            return asyncio.run(adapter.omni_record_correction_outcome(
                path.split("/")[-2],
                self._required(body.get("trajectory_id"), "trajectory_id"),
                self._required(body.get("outcome"), "outcome"),
                self._required(body.get("evidence_event_id"), "evidence_event_id"),
                self._required(body.get("request_id"), "request_id"),
                details=body.get("details"),
            ))
        if method == "POST" and path == "/v1/omni/context-packs":
            return asyncio.run(adapter.omni_build_context_pack(
                self._required(project_id, "project_id"),
                self._required(body.get("query"), "query"),
                self._required(body.get("task_type"), "task_type"),
                behavior_ids=body.get("behavior_ids"), repository=body.get("repository"),
                limit=int(body.get("limit", 10)),
            ))
        if method == "POST" and path == "/v1/omni/audits":
            return asyncio.run(adapter.omni_audit_memories(self._required(project_id, "project_id")))
        if method == "POST" and path.endswith("/approve") and path.startswith("/v1/omni/findings/"):
            return asyncio.run(adapter.omni_approve_revision(path.split("/")[-2]))
        if method == "POST" and path == "/v1/omni/projections/obsidian":
            return asyncio.run(adapter.omni_project_obsidian(
                self._required(project_id, "project_id"),
                self._required(body.get("vault_root"), "vault_root"),
            ))
        raise LookupError("route not found")

    @staticmethod
    def _one(query: dict[str, list[str]], name: str) -> str | None:
        values = query.get(name)
        return values[0] if values else None

    @staticmethod
    def _required(value: Any, name: str):
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError(f"{name} is required")
        return value


def create_api_server(service: MemoryService, verifier: StaticTokenVerifier,
                      *, host: str = "127.0.0.1", port: int = 8080) -> ThreadingHTTPServer:
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host == "localhost"
    if not loopback:
        raise ValueError("Omni REST API binds only to a loopback address")
    router = OmniAPIRouter(service)

    class Handler(BaseHTTPRequestHandler):
        server_version = "MemorycoreOmni/1"

        def do_GET(self) -> None:
            self._handle()

        def do_POST(self) -> None:
            self._handle()

        def _handle(self) -> None:
            request_id = self.headers.get("X-Request-ID") or f"req_{uuid4().hex}"
            try:
                identity = self._authenticate()
                length = int(self.headers.get("Content-Length", "0"))
                if length > MAX_REQUEST_BYTES:
                    raise OverflowError("request body exceeds 262144 bytes")
                raw = self.rfile.read(length) if length else b"{}"
                body = json.loads(raw) if raw else {}
                if not isinstance(body, dict):
                    raise ValueError("JSON body must be an object")
                body.setdefault("request_id", request_id)
                parsed = urlsplit(self.path)
                result = router.dispatch(self.command, parsed.path, parse_qs(parsed.query), body, identity)
                self._json(200, {"request_id": request_id, "result": result})
            except PermissionError as exc:
                self._json(403, {"request_id": request_id, "error": str(exc)})
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"request_id": request_id, "error": str(exc)})
            except OverflowError as exc:
                self._json(413, {"request_id": request_id, "error": str(exc)})
            except LookupError as exc:
                self._json(404, {"request_id": request_id, "error": str(exc)})
            except Exception:
                self._json(500, {"request_id": request_id, "error": "internal server error"})

        def _authenticate(self) -> HTTPClientIdentity:
            header = self.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                raise PermissionError("bearer authentication required")
            identity = verifier.identity_for_token(header.removeprefix("Bearer ").strip())
            if identity is None:
                raise PermissionError("invalid bearer token")
            return identity

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            content = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def run_api_server(database_path: str | Path | None = None, *, host: str = "127.0.0.1",
                   port: int = 8080, token_file: str | Path | None = None) -> None:
    token_path = token_file or os.getenv("MEMORYCORE_HTTP_TOKENS_FILE")
    if not token_path:
        raise ValueError("Omni REST API requires MEMORYCORE_HTTP_TOKENS_FILE")
    service = MemoryService(database_path or os.getenv("MEMORYCORE_DB") or Path.home() / ".memorycore" / "memorycore.db")
    server = create_api_server(service, StaticTokenVerifier.from_file(token_path), host=host, port=port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        service.close()


def openapi_schema() -> dict[str, Any]:
    paths = {
        "/v1/omni/health": ["get"], "/v1/omni/behaviors": ["get"],
        "/v1/omni/behaviors/{behavior_id}": ["get"],
        "/v1/omni/repository-scans": ["post"], "/v1/omni/trajectories": ["post"],
        "/v1/omni/trajectories/{trajectory_id}": ["get"],
        "/v1/omni/trajectories/{trajectory_id}/events": ["post"],
        "/v1/omni/corrections": ["get", "post"],
        "/v1/omni/corrections/{correction_id}/approve": ["post"],
        "/v1/omni/corrections/{correction_id}/outcomes": ["post"],
        "/v1/omni/context-packs": ["post"], "/v1/omni/audits": ["post"],
        "/v1/omni/findings/{finding_id}/approve": ["post"],
        "/v1/omni/projections/obsidian": ["post"],
    }
    return {
        "openapi": "3.1.0", "info": {"title": "Omni Memory Harness API", "version": "1.0.0"},
        "servers": [{"url": "http://127.0.0.1:8080"}],
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}},
        "security": [{"bearerAuth": []}],
        "paths": {path: {method: {"responses": {"200": {"description": "Success"}}} for method in methods}
                  for path, methods in paths.items()},
    }


def main() -> None:
    run_api_server(host=os.getenv("MEMORYCORE_API_HOST", "127.0.0.1"),
                   port=int(os.getenv("MEMORYCORE_API_PORT", "8080")))


if __name__ == "__main__":
    main()
