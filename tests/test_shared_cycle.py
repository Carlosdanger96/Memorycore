"""Six-step contract proof using real CLI/MCP processes and synthetic decisions.

Hermes/Vibe are protocol client identities here, not desktop applications.
Set MEMORYCORE_CYCLE_REPORT to retain the machine-readable evidence in CI.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from memorycore.review import content_sha256


def _environment(database, sources, client, role):
    environment = {k: v for k, v in os.environ.items() if not k.startswith("MEMORYCORE_")}
    environment.update(MEMORYCORE_DB=str(database), MEMORYCORE_REVIEW_SOURCES_FILE=str(sources),
                       MEMORYCORE_CLIENT_ID=client, MEMORYCORE_CLIENT_ROLE=role,
                       MEMORYCORE_ALLOWED_PROJECTS="hermesbag")
    return environment


@asynccontextmanager
async def _client(database, sources, client, role):
    params = StdioServerParameters(command=sys.executable, args=["-m", "memorycore.mcp_server"],
                                  env=_environment(database, sources, client, role))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def _call(session, tool, **arguments):
    result = await session.call_tool(tool, arguments)
    assert not result.isError, result.content
    if result.structuredContent is not None:
        payload = result.structuredContent
        return payload.get("result", payload)
    return json.loads(result.content[0].text)


def _cli(database, sources, client, role, *args):
    result = subprocess.run([sys.executable, "-m", "memorycore.cli", *args],
        env=_environment(database, sources, client, role), capture_output=True, text=True,
        encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _review_args(candidate):
    return {"memory_id": candidate["id"], "expected_revision": candidate["revision"],
            "expected_content_sha256": content_sha256(candidate["content"])}


@pytest.mark.asyncio
async def test_six_step_shared_memory_cycle(tmp_path):
    database, sources = tmp_path / "shared.db", tmp_path / "decisions.json"
    common = {"project_id": "hermesbag", "memory_type": "decision",
              "source_type": "document", "source_uri": sources.as_uri()}
    initial = {**common, "source_id": "storage-v1", "content": "SQLite is the canonical project memory."}
    proposed = {**common, "source_id": "backup-v1", "content": "Backup policy: retain one verified snapshot."}
    correction = {**common, "source_id": "backup-v2", "content": "Backup policy: retain two verified snapshots."}
    report = {"schema_version": 1, "scope": "synthetic CLI/MCP contract; no desktop app or production vault",
              "database": str(database), "steps": [], "ok": False}

    def evidence(step, memory, **extra):
        report["steps"].append({"step": step, "ok": True, "memory_id": memory["id"],
            "revision": memory["revision"], "source_uri": memory["source_uri"],
            "source_id": memory["source_id"], **extra})

    try:
        sources.write_text(json.dumps({"schema_version": 1, "decisions": [initial, proposed]}), encoding="utf-8")
        seeded = _cli(database, sources, "fixture-operator", "administrator", "add",
            "--project", "hermesbag", "--type", "decision", "--content", initial["content"],
            "--source", "document", "--source-uri", initial["source_uri"], "--source-id", initial["source_id"])
        async with asyncio.timeout(120):
            async with _client(database, sources, "hermes", "reader") as hermes:
                async with _client(database, sources, "mistral-vibe", "writer") as vibe:
                    found = await _call(hermes, "memory_retrieve_context", query="canonical", project_id="hermesbag")
                    assert found["count"] == 1 and found["memories"][0]["id"] == seeded["id"]
                    assert found["memories"][0]["source_uri"] == initial["source_uri"]
                    evidence(1, found["memories"][0], client="hermes")

                    pending = await _call(vibe, "memory_add", **proposed)
                    assert pending["status"] == "pending" and pending["client_id"] == "mistral-vibe"
                    hidden = await _call(hermes, "memory_retrieve_context", query="backup policy", project_id="hermesbag")
                    assert hidden["count"] == 0
                    evidence(2, pending, client="mistral-vibe", excluded_from_normal_retrieval=True)

                    result = _cli(database, sources, "automated-reviewer", "approver", "review", pending["id"],
                        "--expected-revision", str(pending["revision"]),
                        "--content-sha256", content_sha256(pending["content"]))
                    approved = result["memory"]
                    assert result["verdict"] == "confirmed" and approved["status"] == "active"
                    evidence(3, approved, client="automated-reviewer", verdict=result["verdict"],
                             source_manifest_sha256=result["source_manifest_sha256"])

                    found = await _call(hermes, "memory_retrieve_context", query="backup policy", project_id="hermesbag")
                    assert found["memories"] == [approved]
                    evidence(4, found["memories"][0], client="hermes")

                    replacement = await _call(vibe, "memory_add", **correction)
                    correction_source = {**correction, "supersedes": {
                        "memory_id": approved["id"], "revision": approved["revision"]}}
                    sources.write_text(json.dumps({"schema_version": 1, "decisions": [initial, correction_source]}), encoding="utf-8")
                    async with _client(database, sources, "automated-reviewer", "approver") as reviewer:
                        result = await _call(reviewer, "memory_review", **_review_args(replacement))
                    corrected = result["memory"]
                    assert result["verdict"] == "confirmed" and corrected["status"] == "active"
                    old = await _call(hermes, "memory_get", memory_id=approved["id"])
                    assert old["status"] == "superseded"
                    found = await _call(hermes, "memory_retrieve_context", query="backup policy", project_id="hermesbag")
                    assert found["memories"] == [corrected]
                    assert corrected["source_id"] == "backup-v2"
                    history_before = await _call(hermes, "memory_history", memory_id=corrected["id"])
                    evidence(5, corrected, superseded_id=old["id"], normal_retrieval_count=1)

            # All service processes above have exited. Open fresh processes.
            async with _client(database, sources, "mistral-vibe", "writer") as vibe:
                duplicate = await _call(vibe, "memory_add", **correction)
                assert duplicate["duplicate"] and duplicate["id"] == corrected["id"]
            async with _client(database, sources, "automated-reviewer", "approver") as reviewer:
                replay = await _call(reviewer, "memory_review", **_review_args(replacement))
                assert replay["replayed"] and replay["memory"] == corrected
            async with _client(database, sources, "hermes", "reader") as hermes:
                found = await _call(hermes, "memory_retrieve_context", query="backup policy", project_id="hermesbag")
                assert found["memories"] == [corrected]
                assert await _call(hermes, "memory_history", memory_id=corrected["id"]) == history_before
            with sqlite3.connect(database) as connection:
                assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
                assert connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 3
                assert connection.execute("SELECT COUNT(*) FROM memory_links").fetchone()[0] == 1
                assert connection.execute("SELECT COUNT(*) FROM memory_events WHERE event_type='memory_reviewed'").fetchone()[0] == 2
            evidence(6, found["memories"][0], restarted_clients=["hermes", "mistral-vibe", "automated-reviewer"],
                     record_count=3, supersession_links=1, review_receipts=2, duplicate_submission=True,
                     duplicate_review=True, audit_unchanged=True)
            report["ok"] = True
    finally:
        report_path = os.getenv("MEMORYCORE_CYCLE_REPORT")
        if report_path:
            Path(report_path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
