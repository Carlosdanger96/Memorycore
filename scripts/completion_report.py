"""Machine-readable completion report for the Memorycore base shared-memory layer.

Runs the exact completion scenarios against independent OS processes and CLI
and MCP clients, then emits a JSON report of commands, client identities,
database paths, record IDs, counts, and pass/fail results.

Usage:
    python scripts/completion_report.py [--output report.json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


def _cli(database: Path, argv: list[str], *, client: str, role: str) -> dict:
    process = subprocess.run(
        [sys.executable, "-m", "memorycore.cli", "--db", str(database),
         "--client", client, "--role", role, *argv],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if process.returncode != 0:
        raise RuntimeError(f"CLI {argv[0]} failed: {process.stderr.strip()}")
    return json.loads(process.stdout)


def _mcp_parameters(database: Path, client_id: str, role: str):
    from mcp import StdioServerParameters
    environment = os.environ.copy()
    environment.update({
        "MEMORYCORE_DB": str(database),
        "MEMORYCORE_CLIENT_ID": client_id,
        "MEMORYCORE_CLIENT_ROLE": role,
    })
    return StdioServerParameters(
        command=sys.executable, args=["-m", "memorycore.mcp_server"], env=environment,
    )


async def _mcp_call(database: Path, client_id: str, role: str, tool: str, arguments: dict):
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client
    async with stdio_client(_mcp_parameters(database, client_id, role)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
            if result.isError:
                raise RuntimeError(f"MCP {tool} failed: {result.content[0].text}")
            payload = result.structuredContent or json.loads(result.content[0].text)
            if isinstance(payload, dict) and "result" in payload:
                payload = payload["result"]
            return payload


def _scenario_a(workdir: Path, report: dict) -> None:
    database = workdir / "a-cross.db"
    created = _cli(database, ["add", "--project", "memorycore", "--type", "decision",
                              "--content", "CLI writes, MCP reads and updates",
                              "--summary", "Cross-interface decision"],
                   client="cli-writer", role="writer")
    approved = asyncio.run(_mcp_call(database, "mcp-approver", "approver",
                                     "memory_approve", {"memory_id": created["id"]}))
    updated = asyncio.run(_mcp_call(database, "mcp-approver", "approver",
                                    "memory_update", {"memory_id": created["id"],
                                                      "summary": "Approved through MCP"}))
    fresh = _cli(database, ["get", created["id"]], client="cli-reader", role="reader")
    history = _cli(database, ["history", created["id"]], client="cli-admin",
                   role="administrator")
    report["scenarios"]["A_cli_writes_mcp_reads_and_updates"] = {
        "ok": all([
            created["client_id"] == "cli-writer",
            created["status"] == "pending",
            approved["status"] == "active",
            updated["revision"] == 2,
            fresh["summary"] == "Approved through MCP",
            "memory_approved" in [e["event_type"] for e in history["events"]],
        ]),
        "database": str(database),
        "clients": ["cli-writer", "mcp-approver", "cli-reader", "cli-admin"],
        "record_id": created["id"],
        "revision": fresh["revision"],
    }


def _scenario_b(workdir: Path, report: dict) -> None:
    database = workdir / "b-cross.db"
    created = asyncio.run(_mcp_call(database, "mcp-writer", "writer", "memory_add", {
        "project_id": "alpha", "memory_type": "fact",
        "content": "MCP writes, CLI reads and updates"}))
    found = _cli(database, ["search", "CLI reads", "--project", "alpha",
                            "--status", "pending", "--limit", "5"],
                 client="cli-reader", role="reader")
    updated = _cli(database, ["update", created["id"], "--summary", "Updated by CLI",
                              "--expected-revision", "0"],
                   client="cli-admin", role="administrator")
    verified = asyncio.run(_mcp_call(database, "mcp-reviewer", "approver", "memory_get", {
        "memory_id": created["id"]}))
    report["scenarios"]["B_mcp_writes_cli_reads_and_updates"] = {
        "ok": all([
            created["client_id"] == "mcp-writer",
            found["count"] == 1,
            updated["revision"] == 1,
            verified["summary"] == "Updated by CLI",
        ]),
        "database": str(database),
        "clients": ["mcp-writer", "cli-reader", "cli-admin", "mcp-reviewer"],
        "record_id": created["id"],
        "revision": verified["revision"],
    }


def _scenario_c(workdir: Path, report: dict) -> None:
    database = workdir / "c-restart.db"
    created = _cli(database, ["add", "--project", "memorycore", "--type", "fact",
                              "--content", "Restart persistence across processes"],
                   client="cli-writer", role="writer")
    asyncio.run(_mcp_call(database, "mcp-approver", "approver", "memory_approve",
                          {"memory_id": created["id"]}))
    reopened = _cli(database, ["get", created["id"]], client="cli-reader", role="reader")
    report["scenarios"]["C_restart_persistence"] = {
        "ok": reopened["status"] == "active" and reopened["revision"] >= 1,
        "database": str(database),
        "record_id": created["id"],
        "revision": reopened["revision"],
    }


def _scenario_d(workdir: Path, report: dict) -> None:
    database = workdir / "d-race.db"
    _cli(database, ["init"], client="cli-admin", role="administrator")
    processes = [
        subprocess.Popen(
            [sys.executable, "-m", "memorycore.cli", "--db", str(database),
             "--client", f"racer-{index}", "--role", "administrator",
             "add", "--project", "race", "--type", "note",
             "--content", f"One live record only{suffix}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(REPO_ROOT))
        for index, suffix in enumerate(["", " ", "  ", "\t", "\n", " .", "..", " "])
    ]
    outcomes = []
    for process in processes:
        out, err = process.communicate(timeout=120)
        outcomes.append(json.loads(out) if process.returncode == 0 else {"error": err})
    created = [o for o in outcomes if o.get("duplicate") is False]
    duplicates = [o for o in outcomes if o.get("duplicate") is True]
    connection = sqlite3.connect(database)
    try:
        live = connection.execute(
            "SELECT COUNT(*) FROM memories WHERE status IN ('pending','active')").fetchone()[0]
        events = connection.execute(
            "SELECT COUNT(*) FROM memory_events WHERE event_type='memory_created'"
        ).fetchone()[0]
    finally:
        connection.close()
    report["scenarios"]["D_duplicate_protection_race"] = {
        "ok": len(created) == 1 and len(duplicates) == 7 and live == 1 and events == 1,
        "database": str(database),
        "clients": [f"racer-{i}" for i in range(8)],
        "record_id": created[0]["id"] if created else None,
        "created": len(created), "duplicates": len(duplicates),
    }


def _scenario_e(workdir: Path, report: dict) -> None:
    database = workdir / "e-concurrent.db"
    _cli(database, ["init"], client="cli-admin", role="administrator")
    processes = [
        subprocess.Popen(
            [sys.executable, "-m", "memorycore.cli", "--db", str(database),
             "--client", f"writer-{index}", "--role", "administrator",
             "add", "--project", "load", "--type", "note",
             "--content", f"Concurrent memory {index}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(REPO_ROOT))
        for index in range(16)
    ]
    failures = []
    for process in processes:
        out, err = process.communicate(timeout=180)
        if process.returncode != 0:
            failures.append(err.strip())
    connection = sqlite3.connect(database)
    try:
        counts = {
            "memories": connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0],
            "events": connection.execute("SELECT COUNT(*) FROM memory_events").fetchone()[0],
        }
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        fk = connection.execute("PRAGMA foreign_key_check").fetchall()
        fts = connection.execute(
            "SELECT COUNT(*) FROM memory_fts WHERE memory_fts MATCH 'concurrent'"
        ).fetchone()[0]
    finally:
        connection.close()

    base = _cli(database, ["add", "--project", "cas", "--type", "fact",
                           "--content", "Compare-and-swap target"],
                client="cli-admin", role="administrator")
    winner = subprocess.Popen(
        [sys.executable, "-m", "memorycore.cli", "--db", str(database),
         "--client", "winner", "--role", "administrator", "update", base["id"],
         "--summary", "Winner", "--expected-revision", "0"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(REPO_ROOT))
    loser = subprocess.Popen(
        [sys.executable, "-m", "memorycore.cli", "--db", str(database),
         "--client", "loser", "--role", "administrator", "update", base["id"],
         "--summary", "Loser", "--expected-revision", "0"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(REPO_ROOT))
    outputs = [winner.communicate(timeout=60), loser.communicate(timeout=60)]
    returncodes = [winner.returncode, loser.returncode]
    # Launch order does not determine which independent process wins the lock.
    conflict_detected = sorted(returncodes) == [0, 3] and "revision conflict" in outputs[returncodes.index(3)][1]
    final = _cli(database, ["get", base["id"]], client="cli-admin", role="administrator")

    report["scenarios"]["E_concurrent_write_safety"] = {
        "ok": not failures and counts["memories"] == 16 and counts["events"] == 16
              and integrity == "ok" and not fk and fts == 16
              and conflict_detected and final["revision"] == 1,
        "database": str(database),
        "clients": [f"writer-{i}" for i in range(16)] + ["winner", "loser"],
        "counts": counts, "integrity": integrity, "fts_hits": fts,
        "write_failures": failures,
        "revision_conflict_detected": conflict_detected,
        "update_returncodes": returncodes,
    }


def _scenario_f(workdir: Path, report: dict) -> None:
    database = workdir / "f-backup.db"
    first = _cli(database, ["add", "--project", "restore", "--type", "decision",
                            "--content", "Backup and restore fidelity",
                            "--summary", "Restore target"], client="cli-writer", role="writer")
    _cli(database, ["approve", first["id"]], client="approver", role="approver")
    _cli(database, ["update", first["id"], "--summary", "Updated before backup"],
         client="editor", role="administrator")
    backup = workdir / "f-backup-snapshot.db"
    _cli(database, ["backup", str(backup)], client="cli-admin", role="administrator")
    restored_path = workdir / "f-restored.db"
    _cli(restored_path, ["init"], client="cli-admin", role="administrator")
    _cli(restored_path, ["restore", str(backup)], client="cli-admin", role="administrator")
    original = _cli(database, ["get", first["id"]], client="cli-reader", role="reader")
    restored = _cli(restored_path, ["get", first["id"]], client="cli-reader", role="reader")
    original_history = _cli(database, ["history", first["id"]], client="cli-admin", role="administrator")
    restored_history = _cli(restored_path, ["history", first["id"]], client="cli-admin", role="administrator")
    check = _cli(restored_path, ["check"], client="cli-admin", role="administrator")
    mcp_view = asyncio.run(_mcp_call(restored_path, "mcp-verifier", "reader",
                                     "memory_get", {"memory_id": first["id"]}))
    report["scenarios"]["F_backup_restoration"] = {
        "ok": restored == original and restored_history == original_history
              and check["integrity"] == "ok" and check["foreign_key_violations"] == 0
              and mcp_view["id"] == first["id"],
        "database": str(database), "backup": str(backup),
        "restored": str(restored_path),
        "record_id": first["id"], "revision": restored["revision"],
        "event_count": restored_history["count"],
    }


def _scenario_g(workdir: Path, report: dict) -> None:
    database = workdir / "g-export.db"
    first = _cli(database, ["add", "--project", "fidelity", "--type", "decision",
                            "--content", "Export import fidelity",
                            "--summary", "Fidelity target"], client="cli-writer", role="writer")
    _cli(database, ["approve", first["id"]], client="approver", role="approver")
    _cli(database, ["update", first["id"], "--summary", "Updated before export"],
         client="editor", role="administrator")
    exported = workdir / "g-export.jsonl"
    _cli(database, ["export", str(exported)], client="cli-admin", role="administrator")
    imported_path = workdir / "g-imported.db"
    _cli(imported_path, ["init"], client="cli-admin", role="administrator")
    _cli(imported_path, ["import", str(exported)], client="cli-admin", role="administrator")
    original = _cli(database, ["get", first["id"]], client="cli-reader", role="reader")
    replica = _cli(imported_path, ["get", first["id"]], client="cli-reader", role="reader")
    original_history = _cli(database, ["history", first["id"]], client="cli-admin", role="administrator")
    replica_history = _cli(imported_path, ["history", first["id"]], client="cli-admin", role="administrator")
    search = _cli(imported_path, ["search", "fidelity", "--project", "fidelity"],
                  client="cli-reader", role="reader")
    report["scenarios"]["G_export_import_fidelity"] = {
        "ok": replica == original and replica_history == original_history
              and search["count"] == 1
              and replica["created_at"] == original["created_at"],
        "database": str(database), "export": str(exported),
        "imported": str(imported_path),
        "record_id": first["id"], "revision": replica["revision"],
        "event_count": replica_history["count"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=None, help="write the JSON report to this path")
    arguments = parser.parse_args()

    report = {
        "report": "memorycore-base-shared-memory-completion",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "scenarios": {},
    }
    workdir = Path(tempfile.mkdtemp(prefix="memorycore-completion-"))
    failures = []
    for scenario in (_scenario_a, _scenario_b, _scenario_c, _scenario_d, _scenario_e,
                     _scenario_f, _scenario_g):
        before = set(report["scenarios"])
        try:
            scenario(workdir, report)
        except Exception as error:  # noqa: BLE001 - report every failure
            failures.append(f"{scenario.__name__}: {error}")
            continue
        for key in set(report["scenarios"]) - before:
            if not report["scenarios"][key]["ok"]:
                failures.append(f"{key}: scenario check failed")

    report["ok"] = not failures
    report["failures"] = failures
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if arguments.output:
        Path(arguments.output).write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
