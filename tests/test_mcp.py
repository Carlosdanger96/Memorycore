import pytest

pytest.importorskip("mcp")

from memorycore.mcp_server import MemoryMCPAdapter, create_server
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
