import json
import os
import sys

import pytest

pytest.importorskip("mcp")

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from memorycore.memory_service import MemoryService


def _parameters(database, client_id, role):
    environment = os.environ.copy()
    environment.update({"MEMORYCORE_DB": str(database), "MEMORYCORE_CLIENT_ID": client_id,
                        "MEMORYCORE_CLIENT_ROLE": role, "MEMORYCORE_MODEL_PROVIDER": client_id})
    return StdioServerParameters(command=sys.executable, args=["-m", "memorycore.mcp_server"], env=environment)


def _data(result):
    return json.loads(result.content[0].text)


@pytest.mark.asyncio
async def test_mistral_and_hermes_share_memory_through_mcp(tmp_path):
    database = tmp_path / "shared.db"
    async with stdio_client(_parameters(database, "mistral-vibe", "writer")) as (read, write):
        async with ClientSession(read, write) as mistral:
            await mistral.initialize()
            created = _data(await mistral.call_tool("memory_add", {"project_id": "memorycore", "memory_type": "decision", "content": "Use one shared memory service", "source_type": "conversation"}))
            assert created["status"] == "pending" and created["client_id"] == "mistral-vibe"
    async with stdio_client(_parameters(database, "hermes", "approver")) as (read, write):
        async with ClientSession(read, write) as hermes:
            await hermes.initialize()
            pending = await hermes.call_tool("memory_search", {"project_id": "memorycore", "query": "shared memory", "status": "pending"})
            assert not pending.isError
            await hermes.call_tool("memory_approve", {"memory_id": created["id"]})
            corrected = _data(await hermes.call_tool("memory_correct", {"memory_id": created["id"], "content": "Use one durable shared memory service for multiple LLMs"}))
    reopened = MemoryService(database)
    active = reopened.search_memory(query="durable shared memory", project_id="memorycore")
    assert active[0].id == corrected["id"]
    assert reopened.get_memory(created["id"]).status == "superseded"
    assert len(reopened.get_memory_history(created["id"])) >= 2
    reopened.close()
