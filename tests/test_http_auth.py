import asyncio
import json
import os
import socket
import sys

import pytest

pytest.importorskip("mcp")
httpx = pytest.importorskip("httpx")

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _connect(url: str, token: str):
    client = httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=10, trust_env=False)
    transport = streamable_http_client(url, http_client=client)
    read, write, _ = await transport.__aenter__()
    session = ClientSession(read, write)
    await session.__aenter__()
    await session.initialize()
    return client, transport, session


@pytest.mark.asyncio
async def test_http_mcp_uses_bearer_tokens_for_identity_and_roles(tmp_path):
    """The public transport rejects anonymous callers and cannot be identity-spoofed."""
    port = _free_port()
    token_file = tmp_path / "http-tokens.json"
    token_file.write_text(json.dumps({"clients": [
        {
            "token": "writer-token-012345678901234567890123456789",
            "client_id": "mistral-web", "client_role": "writer",
            "allowed_projects": ["alpha"], "model_provider": "mistral",
        },
        {
            "token": "approver-token-01234567890123456789012345678",
            "client_id": "chatgpt-web", "client_role": "approver",
            "allowed_projects": ["alpha"], "model_provider": "openai",
        },
    ]}), encoding="utf-8")
    env = os.environ.copy()
    env.update({
        "MEMORYCORE_HTTP_TOKENS_FILE": str(token_file),
        "MEMORYCORE_PUBLIC_URL": f"https://memorycore.example/mcp",
    })
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "memorycore.cli", "--db", str(tmp_path / "shared.db"),
        "serve-http", "--host", "127.0.0.1", "--port", str(port),
        env=env, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}/mcp"
    try:
        for _ in range(40):
            try:
                async with httpx.AsyncClient(timeout=0.2, trust_env=False) as anonymous:
                    response = await anonymous.post(url, content=b"{}")
                if response.status_code == 401:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.1)
        else:
            pytest.fail("authenticated HTTP MCP server did not start")

        writer_client, writer_transport, writer = await _connect(
            url, "writer-token-012345678901234567890123456789"
        )
        try:
            created = await writer.call_tool("memory_add", {
                "project_id": "alpha", "memory_type": "fact", "content": "HTTP token identity is enforced",
            })
            assert not created.isError
            record = json.loads(created.content[0].text)
            assert record["client_id"] == "mistral-web"
            assert record["status"] == "pending"
            denied = await writer.call_tool("memory_approve", {"memory_id": record["id"]})
            assert denied.isError
        finally:
            await writer.__aexit__(None, None, None)
            await writer_transport.__aexit__(None, None, None)
            await writer_client.aclose()

        approver_client, approver_transport, approver = await _connect(
            url, "approver-token-01234567890123456789012345678"
        )
        try:
            approved = await approver.call_tool("memory_approve", {"memory_id": record["id"]})
            assert not approved.isError
            assert json.loads(approved.content[0].text)["status"] == "active"
        finally:
            await approver.__aexit__(None, None, None)
            await approver_transport.__aexit__(None, None, None)
            await approver_client.aclose()
    finally:
        process.terminate()
        await process.wait()
