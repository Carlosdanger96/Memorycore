import json
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from memorycore.api.omni_routes import create_api_server, openapi_schema
from memorycore.http_auth import HTTPClientIdentity, StaticTokenVerifier
from memorycore.mcp_server import MemoryAccessError, MemoryMCPAdapter, MemoryMCPPolicy, create_server
from memorycore.memory_service import MemoryService


@pytest.mark.asyncio
async def test_mcp_exposes_omni_tools_and_enforces_write_policy(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "agent.py").write_text("def verify_output(value):\n    return bool(value)\n", encoding="utf-8")
    service = MemoryService(tmp_path / "mcp-omni.db", scanner_roots=[repo])
    readonly = MemoryMCPAdapter(service, MemoryMCPPolicy(read_only=True, client_role="reader"))
    with pytest.raises(MemoryAccessError):
        await readonly.omni_scan_repository(str(repo), "p")
    writer = MemoryMCPAdapter(service, MemoryMCPPolicy(client_id="writer", client_role="writer"))
    records = await writer.omni_scan_repository(str(repo), "p")
    assert records[0]["behavior_id"] == "agent.output.verify"
    tools = {tool.name for tool in create_server(service)._tool_manager.list_tools()}
    assert {"omni_scan_repository", "omni_build_context_pack", "omni_approve_revision"} <= tools
    service.close()


def test_rest_requires_bearer_and_returns_health(tmp_path):
    service = MemoryService(tmp_path / "api.db")
    token = "test-token-that-is-at-least-24-characters"
    verifier = StaticTokenVerifier([HTTPClientIdentity(
        token=token, client_id="reader", client_role="reader",
    )])
    server = create_api_server(service, verifier, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1/omni/health"
    try:
        with pytest.raises(HTTPError) as denied:
            urlopen(url)
        assert denied.value.code == 403
        request = Request(url, headers={"Authorization": f"Bearer {token}"})
        with urlopen(request) as response:
            payload = json.load(response)
        assert payload["result"]["ok"] is True
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2); service.close()


def test_openapi_uses_loopback_and_bearer_security():
    schema = openapi_schema()
    assert schema["servers"] == [{"url": "http://127.0.0.1:8080"}]
    assert "bearerAuth" in schema["components"]["securitySchemes"]
