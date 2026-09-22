"""Process-level completion tests for the shared Memorycore base layer.

These tests spawn real, independent OS processes: CLI subprocesses and MCP
stdio server subprocesses with separate identities, proving CLI↔MCP
interoperability, restart durability, atomic duplicate prevention,
multi-process write safety, update-conflict detection, backup restoration,
and full-fidelity export/import.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parent.parent


def _cli(database: Path, argv: list[str], *, client: str = "cli-admin",
         role: str = "administrator", check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "memorycore.cli", "--db", str(database),
         "--client", client, "--role", role, *argv],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )


def _cli_json(result: subprocess.CompletedProcess) -> dict:
    assert result.returncode == 0, f"CLI failed: {result.stdout} {result.stderr}"
    return json.loads(result.stdout)


def _mcp_parameters(database: Path, client_id: str, role: str) -> StdioServerParameters:
    environment = os.environ.copy()
    environment.update({
        "MEMORYCORE_DB": str(database),
        "MEMORYCORE_CLIENT_ID": client_id,
        "MEMORYCORE_CLIENT_ROLE": role,
        "MEMORYCORE_MODEL_PROVIDER": client_id,
    })
    return StdioServerParameters(
        command=sys.executable, args=["-m", "memorycore.mcp_server"], env=environment,
    )


def _data(result) -> dict:
    """Parse a single-record result, preferring the structured content."""
    assert not result.isError, result.content
    if result.structuredContent is not None:
        payload = result.structuredContent
        if isinstance(payload, dict) and "result" in payload:
            payload = payload["result"]
        return payload
    return json.loads(result.content[0].text)


def _data_list(result) -> list:
    """Parse a list result; FastMCP may auto-unwrap single-element lists."""
    assert not result.isError, result.content
    if result.structuredContent is not None:
        payload = result.structuredContent
        if isinstance(payload, dict) and "result" in payload:
            payload = payload["result"]
        return payload if isinstance(payload, list) else [payload]
    payload = json.loads(result.content[0].text)
    if isinstance(payload, dict):
        return [payload]
    return payload


@pytest.mark.asyncio
async def test_a_cli_writes_mcp_reads_and_updates(tmp_path):
    database = tmp_path / "cross.db"

    created = _cli_json(_cli(database, [
        "add", "--project", "memorycore", "--type", "decision",
        "--content", "CLI and MCP share one governed memory service",
        "--summary", "Shared service", "--tag", "architecture",
        "--source", "system_event", "--confidence", "0.9",
    ], client="cli-writer", role="writer"))
    assert created["status"] == "pending"
    assert created["client_id"] == "cli-writer"
    assert created["source_type"] == "system_event"

    async with stdio_client(_mcp_parameters(database, "mcp-approver", "approver")) as (read, write):
        async with ClientSession(read, write) as mcp:
            await mcp.initialize()
            by_id = _data(await mcp.call_tool("memory_get", {"memory_id": created["id"]}))
            assert by_id["content"] == "CLI and MCP share one governed memory service"
            assert by_id["project_id"] == "memorycore"
            assert by_id["status"] == "pending"
            assert by_id["client_id"] == "cli-writer"
            by_search = _data_list(await mcp.call_tool("memory_search", {
                "project_id": "memorycore", "query": "governed memory",
                "status": "pending"}))
            assert any(m["id"] == created["id"] for m in by_search)
            approved = _data(await mcp.call_tool("memory_approve", {"memory_id": created["id"]}))
            assert approved["status"] == "active"
            assert approved["revision"] == 1
            updated = _data(await mcp.call_tool("memory_update", {
                "memory_id": created["id"], "summary": "Approved through MCP"}))
            assert updated["revision"] == 2

    fresh = _cli_json(_cli(database, ["get", created["id"]], client="cli-reader", role="reader"))
    assert fresh["status"] == "active"
    assert fresh["summary"] == "Approved through MCP"
    assert fresh["revision"] == 2
    history = _cli_json(_cli(database, ["history", created["id"]]))
    event_types = [event["event_type"] for event in history["events"]]
    assert "memory_created" in event_types and "memory_approved" in event_types


@pytest.mark.asyncio
async def test_b_mcp_writes_cli_reads_and_updates(tmp_path):
    database = tmp_path / "cross2.db"

    async with stdio_client(_mcp_parameters(database, "mcp-writer", "writer")) as (read, write):
        async with ClientSession(read, write) as mcp:
            await mcp.initialize()
            created = _data(await mcp.call_tool("memory_add", {
                "project_id": "alpha", "memory_type": "fact",
                "content": "MCP writes are visible to the CLI",
                "source_type": "conversation", "session_id": "sess-1"}))
            assert created["status"] == "pending" and created["client_id"] == "mcp-writer"

    found = _cli_json(_cli(database, ["search", "visible to the CLI",
                                      "--project", "alpha", "--status", "pending"],
                           client="cli-reader", role="reader"))
    assert found["count"] == 1 and found["memories"][0]["id"] == created["id"]

    updated = _cli_json(_cli(database, [
        "update", created["id"], "--summary", "Updated through CLI",
        "--expected-revision", "0"], client="cli-admin", role="administrator"))
    assert updated["revision"] == 1
    assert updated["updated_by"] == "cli-admin"

    async with stdio_client(_mcp_parameters(database, "mcp-reviewer", "approver")) as (read, write):
        async with ClientSession(read, write) as mcp:
            await mcp.initialize()
            fetched = _data(await mcp.call_tool("memory_get", {"memory_id": created["id"]}))
            assert fetched["summary"] == "Updated through CLI"
            assert fetched["revision"] == 1
            history = _data_list(await mcp.call_tool("memory_history", {"memory_id": created["id"]}))
            assert [e["event_type"] for e in history] == ["memory_created", "memory_updated"]
            assert history[1]["client_id"] == "cli-admin"


@pytest.mark.asyncio
async def test_c_restart_persistence_across_interfaces(tmp_path):
    database = tmp_path / "restart.db"
    first = _cli_json(_cli(database, [
        "add", "--project", "memorycore", "--type", "fact",
        "--content", "Restart persistence across CLI and MCP",
    ], client="cli-writer", role="writer"))

    async with stdio_client(_mcp_parameters(database, "mcp-approver", "approver")) as (read, write):
        async with ClientSession(read, write) as mcp:
            await mcp.initialize()
            await mcp.call_tool("memory_approve", {"memory_id": first["id"]})
            await mcp.call_tool("memory_update", {
                "memory_id": first["id"], "content": "Restart persistence across CLI and MCP v2"})

    reopened = _cli_json(_cli(database, ["get", first["id"]]))
    assert reopened["revision"] == 2
    assert reopened["status"] == "active"

    async with stdio_client(_mcp_parameters(database, "mcp-reader", "reader")) as (read, write):
        async with ClientSession(read, write) as mcp:
            await mcp.initialize()
            found = _data_list(await mcp.call_tool("memory_search", {
                "project_id": "memorycore", "query": "restart persistence"}))
            assert found and found[0]["id"] == first["id"]
            assert found[0]["revision"] == 2


@pytest.mark.asyncio
async def test_d_duplicate_protection_sequential_and_raced(tmp_path):
    database = tmp_path / "duplicates.db"
    first = _cli_json(_cli(database, [
        "add", "--project", "dup", "--type", "fact",
        "--content", "Exactly one live record may exist",
    ], client="cli-writer", role="writer"))

    async with stdio_client(_mcp_parameters(database, "mcp-writer", "writer")) as (read, write):
        async with ClientSession(read, write) as mcp:
            await mcp.initialize()
            duplicate = _data(await mcp.call_tool("memory_add", {
                "project_id": "dup", "memory_type": "fact",
                "content": "  EXACTLY one live record   MAY exist  "}))
            assert duplicate["duplicate"] is True
            assert duplicate["duplicate_of"] == first["id"]

    assert _cli_json(_cli(database, ["projects"]))["projects"] == ["dup"]

    race_db = tmp_path / "race.db"
    _cli(race_db, ["init"])
    whitespace = ["", " ", "  ", "\t", "\n", " .", "..", " "]
    processes = [
        subprocess.Popen(
            [sys.executable, "-m", "memorycore.cli", "--db", str(race_db),
             "--client", f"racer-{index}", "--role", "administrator",
             "add", "--project", "race", "--type", "note",
             "--content", f"All racers submit equivalent {suffix}content"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=str(REPO_ROOT))
        for index, suffix in enumerate(whitespace)
    ]
    results = []
    for process in processes:
        out, err = process.communicate(timeout=120)
        assert process.returncode == 0, err
        results.append(json.loads(out))
    created = [r for r in results if not r["duplicate"]]
    duplicates = [r for r in results if r["duplicate"]]
    assert len(created) == 1
    assert len(duplicates) == 7
    assert all(r["duplicate_of"] == created[0]["id"] for r in duplicates)

    connection = sqlite3.connect(race_db)
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM memories WHERE content_fingerprint IS NOT NULL"
        ).fetchone()[0]
        events = connection.execute(
            "SELECT COUNT(*) FROM memory_events WHERE event_type = 'memory_created'"
        ).fetchone()[0]
        assert count == 1
        assert events == 1
    finally:
        connection.close()


def test_e_concurrent_writes_from_sixteen_processes(tmp_path):
    database = tmp_path / "concurrent.db"
    _cli(database, ["init"])
    processes = []
    for index in range(16):
        processes.append(subprocess.Popen(
            [sys.executable, "-m", "memorycore.cli", "--db", str(database),
             "--client", f"writer-{index}", "--role", "administrator",
             "add", "--project", "load", "--type", "note",
             "--content", f"Distinct concurrent memory number {index}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=str(REPO_ROOT)))
    for process in processes:
        out, err = process.communicate(timeout=180)
        assert process.returncode == 0, err
        record = json.loads(out)
        assert record["duplicate"] is False

    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 16
        assert connection.execute(
            "SELECT COUNT(*) FROM memory_events").fetchone()[0] == 16
        fts_hits = connection.execute(
            "SELECT COUNT(*) FROM memory_fts WHERE memory_fts MATCH 'concurrent'").fetchone()[0]
        assert fts_hits == 16
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()

    results = _cli_json(_cli(database, ["search", "concurrent", "--project", "load",
                                       "--limit", "50"]))
    assert results["count"] == 16


def test_e_revision_conflict_for_concurrent_updates(tmp_path):
    database = tmp_path / "conflict.db"
    created = _cli_json(_cli(database, [
        "add", "--project", "conflict", "--type", "fact",
        "--content", "Two clients race to update this memory"]))

    winner = subprocess.Popen(
        [sys.executable, "-m", "memorycore.cli", "--db", str(database),
         "--client", "winner", "--role", "administrator",
         "update", created["id"], "--summary", "Winner summary",
         "--expected-revision", "0"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(REPO_ROOT))
    loser = subprocess.Popen(
        [sys.executable, "-m", "memorycore.cli", "--db", str(database),
         "--client", "loser", "--role", "administrator",
         "update", created["id"], "--summary", "Loser summary",
         "--expected-revision", "0"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(REPO_ROOT))
    outputs = [winner.communicate(timeout=60), loser.communicate(timeout=60)]
    returncodes = [winner.returncode, loser.returncode]
    assert sorted(returncodes) == [0, 3]
    conflict = outputs[returncodes.index(3)][1]
    assert "revision conflict" in conflict
    final = _cli_json(_cli(database, ["get", created["id"]]))
    assert final["revision"] == 1


def test_f_backup_restore_roundtrip(tmp_path):
    database = tmp_path / "live.db"
    first = _cli_json(_cli(database, [
        "add", "--project", "restore", "--type", "decision",
        "--content", "Restore must preserve every logical record",
        "--summary", "Restore decision", "--tag", "recovery"],
        client="cli-writer", role="writer"))
    second = _cli_json(_cli(database, [
        "add", "--project", "restore", "--type", "note",
        "--content", "A second record with links and history"]))
    _cli(database, ["approve", first["id"]], client="approver", role="approver")
    _cli(database, ["update", first["id"], "--summary", "Approved and updated"],
         client="editor", role="administrator")

    backup = tmp_path / "backup.db"
    _cli(database, ["backup", str(backup)])

    restored_path = tmp_path / "restored.db"
    _cli(restored_path, ["init"])
    _cli(restored_path, ["restore", str(backup)])

    original = _cli_json(_cli(database, ["get", first["id"]]))
    restored = _cli_json(_cli(restored_path, ["get", first["id"]]))
    assert restored == original
    assert restored["revision"] == original["revision"]
    assert restored["updated_by"] == "editor"
    history_original = _cli_json(_cli(database, ["history", first["id"]]))
    history_restored = _cli_json(_cli(restored_path, ["history", first["id"]]))
    assert history_restored["events"] == history_original["events"]
    check = _cli_json(_cli(restored_path, ["check"]))
    assert check["integrity"] == "ok" and check["foreign_key_violations"] == 0
    search = _cli_json(_cli(restored_path, ["search", "logical record", "--project", "restore"]))
    assert search["count"] == 1
    assert _cli_json(_cli(restored_path, ["get", second["id"]]))["id"] == second["id"]


def test_g_export_import_full_fidelity(tmp_path):
    database = tmp_path / "source.db"
    first = _cli_json(_cli(database, [
        "add", "--project", "fidelity", "--type", "decision",
        "--content", "Export must carry full history",
        "--summary", "Fidelity decision", "--tag", "export"],
        client="cli-writer", role="writer"))
    assert first["status"] == "pending"
    _cli(database, ["approve", first["id"]], client="approver", role="approver")
    _cli(database, ["update", first["id"], "--summary", "Updated before export"],
         client="editor", role="administrator")

    exported = tmp_path / "snapshot.jsonl"
    _cli(database, ["export", str(exported)])

    imported_path = tmp_path / "imported.db"
    _cli(imported_path, ["init"])
    imported = _cli_json(_cli(imported_path, ["import", str(exported)]))
    assert imported["memory_count"] == 1

    original = _cli_json(_cli(database, ["get", first["id"]]))
    replica = _cli_json(_cli(imported_path, ["get", first["id"]]))
    assert replica == original
    assert replica["created_at"] == original["created_at"]
    assert replica["updated_at"] == original["updated_at"]
    assert replica["revision"] == original["revision"]

    history_original = _cli_json(_cli(database, ["history", first["id"]]))["events"]
    history_replica = _cli_json(_cli(imported_path, ["history", first["id"]]))["events"]
    assert history_replica == history_original
    assert [e["event_type"] for e in history_replica] == [
        "memory_created", "memory_approved", "memory_updated"]

    search = _cli_json(_cli(imported_path, ["search", "full history", "--project", "fidelity"]))
    assert search["count"] == 1 and search["memories"][0]["id"] == first["id"]
    check = _cli_json(_cli(imported_path, ["check"]))
    assert check["integrity"] == "ok" and check["foreign_key_violations"] == 0


def test_g_import_with_links_and_multiple_memories(tmp_path):
    database = tmp_path / "links.db"
    first = _cli_json(_cli(database, [
        "add", "--project", "links", "--type", "fact",
        "--content", "Original fact that will be corrected"]))
    replacement = _cli_json(_cli(database, [
        "add", "--project", "links", "--type", "fact",
        "--content", "Corrected replacement fact"]))

    from memorycore.memory_service import MemoryService
    service = MemoryService(database)
    service.supersede_memory(first["id"], content="Superseding content",
                             updated_by="approver")
    exported = tmp_path / "links.jsonl"
    service.export_jsonl(exported)
    service.close()

    imported_path = tmp_path / "links-imported.db"
    _cli(imported_path, ["init"])
    _cli(imported_path, ["import", str(exported)])

    replica = MemoryService(imported_path)
    links = replica.database.all_links()
    assert len(links) == 1
    assert links[0]["relation_type"] == "supersedes"
    statuses = {m.id: m.status for m in replica.database.all_memories()}
    assert statuses[first["id"]] == "superseded"
    assert replica.integrity_check()["foreign_key_violations"] == 0
    replica.close()


@pytest.mark.asyncio
async def test_duplicate_and_conflict_over_mcp(tmp_path):
    database = tmp_path / "mcp-dup.db"
    async with stdio_client(_mcp_parameters(database, "mcp-admin", "administrator")) as (read, write):
        async with ClientSession(read, write) as mcp:
            await mcp.initialize()
            created = _data(await mcp.call_tool("memory_add", {
                "project_id": "p", "memory_type": "note", "content": "Unique MCP content"}))
            assert created["duplicate"] is False
            duplicate = _data(await mcp.call_tool("memory_add", {
                "project_id": "p", "memory_type": "note", "content": "unique   mcp CONTENT"}))
            assert duplicate["duplicate"] is True
            assert duplicate["duplicate_of"] == created["id"]
            updated = _data(await mcp.call_tool("memory_update", {
                "memory_id": created["id"], "summary": "First", "expected_revision": 0}))
            assert updated["revision"] == 1
            conflicted = await mcp.call_tool("memory_update", {
                "memory_id": created["id"], "summary": "Second", "expected_revision": 0})
            assert conflicted.isError
            assert "revision conflict" in conflicted.content[0].text
