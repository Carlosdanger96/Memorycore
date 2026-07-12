import pytest
import os
import sys

pytest.importorskip("mcp")

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from memorycore.mcp_server import MemoryAccessError, MemoryMCPAdapter, MemoryMCPPolicy, create_server
from memorycore.memory_service import MemoryService


@pytest.mark.asyncio
async def test_mcp_adapter_uses_persistent_service(tmp_path):
    path = tmp_path / "mcp.db"
    service = MemoryService(path)
    adapter = MemoryMCPAdapter(service)
    created = await adapter.memory_add(project_id="alpha", memory_type="note",
        content="Stored through the MCP adapter")
    fetched = await adapter.memory_get(created["id"])
    assert fetched is not None and fetched["content"] == "Stored through the MCP adapter"
    results = await adapter.memory_search("MCP adapter", "alpha")
    assert results[0]["id"] == created["id"]
    assert create_server(service) is not None
    service.close()
    reopened = MemoryService(path)
    assert reopened.get_memory(created["id"]) is not None
    reopened.close()


@pytest.mark.asyncio
async def test_mcp_enforces_project_scope_read_only_and_provenance(tmp_path):
    service = MemoryService(tmp_path / "mcp-policy.db")
    policy = MemoryMCPPolicy(allowed_projects={"memorycore"})
    adapter = MemoryMCPAdapter(service, policy)
    created = await adapter.memory_add(
        project_id="memorycore", memory_type="decision", content="Use one MCP contract",
        created_by="chatgpt", client_id="work", model_provider="openai",
        model_name="gpt-5", session_id="abc", source_type="conversation",
        source_uri="chat://memorycore", confidence=0.9,
    )
    assert created["client_id"] == "work"
    assert created["source_type"] == "conversation"
    assert created["confidence"] == 0.9
    with pytest.raises(MemoryAccessError):
        await adapter.memory_search("contract", "career")
    readonly = MemoryMCPAdapter(service, MemoryMCPPolicy(read_only=True))
    with pytest.raises(MemoryAccessError):
        await readonly.memory_archive(created["id"])
    service.close()


@pytest.mark.asyncio
async def test_mcp_approval_mode_creates_pending_memory(tmp_path):
    service = MemoryService(tmp_path / "mcp-approval.db")
    adapter = MemoryMCPAdapter(service, MemoryMCPPolicy(require_approval=True))
    created = await adapter.memory_add(project_id="alpha", memory_type="note", content="Review me")
    assert created["status"] == "pending"
    activated = await adapter.memory_update(created["id"], status="active", updated_by="reviewer")
    assert activated is not None and activated["status"] == "active"
    assert activated["updated_by"] == "reviewer"
    service.close()


@pytest.mark.asyncio
async def test_real_mcp_client_can_use_stdio_server(tmp_path):
    """Validate the actual MCP protocol, not only the adapter methods."""
    environment = os.environ.copy()
    environment["MEMORYCORE_DB"] = str(tmp_path / "stdio.db")
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "memorycore.mcp_server"],
        env=environment,
    )
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tool_names = {tool.name for tool in (await session.list_tools()).tools}
            assert {"memory_add", "memory_retrieve_context", "memory_health"} <= tool_names
            result = await session.call_tool("memory_add", {
                "project_id": "alpha",
                "memory_type": "decision",
                "content": "The server accepts real MCP client requests",
                "client_id": "integration-test",
                "source_type": "system_event",
            })
            assert not result.isError
            context = await session.call_tool("memory_retrieve_context", {
                "project_id": "alpha", "query": "real MCP requests",
            })
            assert not context.isError
