"""MCP-process duplicate race and multi-process MCP write safety.

Complements the CLI races in test_cross_interface.py: these tests spawn many
independent MCP server processes over real stdio, so duplicate prevention and
concurrent writes are proven across both interfaces at the process level.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parent.parent


def _parameters(database: Path, client_id: str, role: str = "administrator") -> StdioServerParameters:
    environment = os.environ.copy()
    environment.update({
        "MEMORYCORE_DB": str(database),
        "MEMORYCORE_CLIENT_ID": client_id,
        "MEMORYCORE_CLIENT_ROLE": role,
    })
    return StdioServerParameters(
        command=sys.executable, args=["-m", "memorycore.mcp_server"], env=environment,
    )


async def _add_memory(database: Path, client_id: str, content: str) -> dict:
    async with stdio_client(_parameters(database, client_id)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("memory_add", {
                "project_id": "race", "memory_type": "note", "content": content,
            })
            assert not result.isError, result.content
            payload = result.structuredContent or json.loads(result.content[0].text)
            if isinstance(payload, dict) and "result" in payload:
                payload = payload["result"]
            return payload


@pytest.mark.asyncio
async def test_eight_mcp_processes_race_one_memory(tmp_path):
    database = tmp_path / "mcp-race.db"
    contents = ["", " ", "  ", "\t", "\n", " .", "..", " "]
    results = await asyncio.gather(*(
        _add_memory(database, f"mcp-racer-{index}",
                    f"Raced MCP content{suffix}")
        for index, suffix in enumerate(contents)))

    created = [r for r in results if not r["duplicate"]]
    duplicates = [r for r in results if r["duplicate"]]
    assert len(created) == 1
    assert len(duplicates) == 7
    assert all(r["duplicate_of"] == created[0]["id"] for r in duplicates)

    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM memories WHERE status IN ('pending','active')"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM memory_events WHERE event_type = 'memory_created'"
        ).fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_sixteen_mcp_processes_write_distinct_memories(tmp_path):
    database = tmp_path / "mcp-load.db"
    results = await asyncio.gather(*(
        _add_memory(database, f"mcp-writer-{index}",
                    f"Distinct MCP memory {index}")
        for index in range(16)))

    assert all(not r["duplicate"] for r in results)
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 16
        assert connection.execute("SELECT COUNT(*) FROM memory_events").fetchone()[0] == 16
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()
