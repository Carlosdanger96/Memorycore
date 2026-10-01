"""Unit coverage for the shared policy layer, CLI commands, and projection."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from memorycore.memory_service import MemoryService
from memorycore.models import ClientRole
from memorycore.policy import (
    ClientPolicy, MemoryAccessError, RevisionConflictError, policy_from_environment,
)
from memorycore.projections.obsidian import ObsidianProjection

REPO_ROOT = Path(__file__).resolve().parent.parent


def _cli(database: Path, argv: list[str], *, client="cli-admin",
         role="administrator", env: dict | None = None) -> subprocess.CompletedProcess:
    environment = os.environ.copy()
    if env:
        environment.update(env)
    return subprocess.run(
        [sys.executable, "-m", "memorycore.cli", "--db", str(database),
         "--client", client, "--role", role, *argv],
        capture_output=True, text=True, cwd=str(REPO_ROOT), env=environment,
    )


def test_policy_contract_is_shared_between_interfaces():
    from memorycore.mcp_server import MemoryMCPPolicy
    base = ClientPolicy(client_id="x", client_role="writer")
    mcp = MemoryMCPPolicy(client_id="x", client_role="writer")
    assert base.creation_status() == mcp.creation_status() == "pending"
    assert base.allowed_projects == mcp.allowed_projects is None
    administrator = ClientPolicy(client_id="y", client_role="administrator")
    assert administrator.creation_status() == "active"
    with pytest.raises(MemoryAccessError):
        base.require_role(ClientRole.APPROVER)
    with pytest.raises(MemoryAccessError):
        ClientPolicy(client_id="z", client_role="reader").check_mutation() if False else \
            ClientPolicy(client_id="z", client_role="reader", read_only=True).check_mutation()


def test_policy_from_environment_reads_all_flags():
    policy = policy_from_environment({
        "MEMORYCORE_CLIENT_ID": "  cli-identity  ",
        "MEMORYCORE_CLIENT_ROLE": "approver",
        "MEMORYCORE_ALLOWED_PROJECTS": "alpha, beta ,",
        "MEMORYCORE_READ_ONLY": "true",
        "MEMORYCORE_REQUIRE_APPROVAL": "1",
        "MEMORYCORE_MODEL_PROVIDER": "mistral",
        "MEMORYCORE_MODEL_NAME": "vibe",
    })
    assert policy.client_id == "cli-identity"
    assert policy.client_role == "approver"
    assert policy.allowed_projects == frozenset({"alpha", "beta"})
    assert policy.read_only and policy.require_approval
    assert policy.model_provider == "mistral" and policy.model_name == "vibe"


def test_policy_from_environment_defaults():
    policy = policy_from_environment({})
    assert policy.client_id == "memorycore-client"
    assert policy.client_role == "administrator"
    assert policy.allowed_projects is None
    assert not policy.read_only and not policy.require_approval


def test_cli_add_get_search_update_archive(tmp_path):
    database = tmp_path / "unit.db"
    created = json.loads(_cli(database, [
        "add", "--project", "alpha", "--type", "decision",
        "--content", "CLI unit test memory", "--summary", "Unit summary",
        "--tag", "cli", "--tag", "test", "--metadata", '{"origin": "pytest"}',
        "--source", "system_event", "--confidence", "0.8"], client="unit-writer",
        role="writer").stdout)
    assert created["status"] == "pending"
    assert created["tags"] == ["cli", "test"]
    assert created["metadata"] == {"origin": "pytest"}
    assert created["client_id"] == "unit-writer"

    got = json.loads(_cli(database, ["get", created["id"]]).stdout)
    assert got["id"] == created["id"]

    found = json.loads(_cli(database, [
        "search", "unit test", "--project", "alpha", "--status", "pending"],
        client="reader", role="reader").stdout)
    assert found["count"] == 1

    updated = json.loads(_cli(database, [
        "update", created["id"], "--summary", "Approved summary",
        "--expected-revision", "0"], client="approver", role="approver").stdout)
    assert updated["revision"] == 1

    approved = json.loads(_cli(database, ["approve", created["id"]],
                               client="approver", role="approver").stdout)
    assert approved["status"] == "active"

    archived = json.loads(_cli(database, ["archive", created["id"]],
                               client="approver", role="approver").stdout)
    assert archived["status"] == "archived"

    history = json.loads(_cli(database, ["history", created["id"]]).stdout)
    assert [e["event_type"] for e in history["events"]] == [
        "memory_created", "memory_updated", "memory_approved", "memory_archived"]


def test_cli_enforces_roles_and_projects(tmp_path):
    database = tmp_path / "roles.db"
    denied = _cli(database, ["add", "--project", "alpha", "--type", "note",
                             "--content", "Denied"], client="reader", role="reader")
    assert denied.returncode == 4
    assert "cannot perform this operation" in denied.stderr

    scoped = _cli(database, ["add", "--project", "beta", "--type", "note",
                             "--content", "Scoped"], client="scoped",
                  role="writer", env={"MEMORYCORE_ALLOWED_PROJECTS": "alpha"})
    assert scoped.returncode == 4
    assert "not allowed" in scoped.stderr

    created = json.loads(_cli(database, ["add", "--project", "alpha", "--type", "note",
                                        "--content", "Allowed"], client="w",
                             role="writer").stdout)
    self_approve = _cli(database, ["approve", created["id"]], client="w", role="writer")
    assert self_approve.returncode == 4
    read_only = _cli(database, ["archive", created["id"]],
                     env={"MEMORYCORE_READ_ONLY": "true"})
    assert read_only.returncode == 4


def test_cli_writer_can_only_update_own_pending(tmp_path):
    database = tmp_path / "writer-scope.db"
    created = json.loads(_cli(database, [
        "add", "--project", "p", "--type", "note", "--content", "Writer memory"],
        client="writer-a", role="writer").stdout)
    denied = _cli(database, ["update", created["id"], "--summary", "Nope"],
                  client="writer-b", role="writer")
    assert denied.returncode == 1
    assert "writers may only update their own pending memories" in denied.stderr
    allowed = _cli(database, ["update", created["id"], "--summary", "Mine"],
                   client="writer-a", role="writer")
    assert allowed.returncode == 0


def test_cli_revision_conflict_exit_code(tmp_path):
    database = tmp_path / "cas.db"
    created = json.loads(_cli(database, [
        "add", "--project", "p", "--type", "note", "--content", "CAS memory"]).stdout)
    conflict = _cli(database, ["update", created["id"], "--summary", "Stale",
                              "--expected-revision", "5"])
    assert conflict.returncode == 3
    assert "revision conflict" in conflict.stderr


def test_cli_duplicate_result_is_deterministic(tmp_path):
    database = tmp_path / "dup.db"
    first = json.loads(_cli(database, [
        "add", "--project", "d", "--type", "fact", "--content", "Same normalized"]).stdout)
    second = json.loads(_cli(database, [
        "add", "--project", "d", "--type", "fact", "--content", "  SAME   Normalized  "],
        client="other", role="administrator").stdout)
    assert second["duplicate"] is True
    assert second["duplicate_of"] == first["id"]
    assert second["id"] == first["id"]


def test_service_duplicate_and_conflict_semantics(tmp_path):
    service = MemoryService(tmp_path / "svc.db")
    created = service.add_memory(project_id="p", memory_type="note",
                                 content="Service memory")
    duplicate = service.add_memory_or_duplicate(
        project_id="p", memory_type="note", content="service   MEMORY")
    assert duplicate["duplicate"] is True
    assert duplicate["memory"]["id"] == created.id

    updated = service.update_memory(created.id, summary="v2", expected_revision=0)
    assert updated.revision == 1
    with pytest.raises(RevisionConflictError):
        service.update_memory(created.id, summary="v3", expected_revision=0)

    service.update_memory(created.id, status="archived", expected_revision=1)
    recreated = service.add_memory_or_duplicate(
        project_id="p", memory_type="note", content="service memory")
    assert recreated["duplicate"] is False
    service.close()


def test_obsidian_projection_is_idempotent_and_root_checked(tmp_path):
    service = MemoryService(tmp_path / "proj.db")
    first = service.add_memory(project_id="alpha", memory_type="decision",
                               content="Projection decision", summary="Decision",
                               tags=["proj"], client_id="writer", status="pending")
    service.approve_memory(first.id, approved_by="approver")
    second = service.add_memory(project_id="alpha", memory_type="note",
                                content="Pending note in projection", client_id="writer",
                                status="pending")
    vault = tmp_path / "vault"
    allowed = str(tmp_path)
    projection = ObsidianProjection(service.database, [allowed])
    result = projection.project(vault, project_id="alpha")
    assert result["memory_count"] == 2
    assert len(result["written"]) >= 3
    assert len(result["unchanged"]) == 0

    second_result = projection.project(vault, project_id="alpha")
    assert second_result["written"] == []
    assert sorted(second_result["unchanged"]) == sorted(result["written"])

    root = Path(result["root"])
    assert (root / "Active" / f"{first.id}.md").exists()
    assert (root / "Pending" / f"{second.id}.md").exists()
    manifest = (root / "Provenance" / "projection-manifest.md").read_text()
    assert "Generated projection" in manifest

    outside = ObsidianProjection(service.database, [str(tmp_path / "elsewhere")])
    with pytest.raises(ValueError, match="outside the configured allowed roots"):
        outside.project(tmp_path / "vault2", project_id="alpha")
    service.close()


def test_memory_only_import_is_rejected(tmp_path):
    service = MemoryService(tmp_path / "source.db")
    memory = service.add_memory(project_id="p", memory_type="fact",
                                content="Full history required")
    full_export = tmp_path / "full.jsonl"
    service.export_jsonl(full_export)
    service.close()

    memory_only = tmp_path / "memory-only.jsonl"
    memory_only.write_text(
        json.dumps({"record_type": "memory", **memory.to_dict()}) + "\n",
        encoding="utf-8")
    importer = MemoryService(tmp_path / "imported.db")
    with pytest.raises(ValueError, match="full-fidelity"):
        importer.import_jsonl(memory_only)
    assert importer.import_jsonl(full_export) == 1
    replica = importer.get_memory(memory.id)
    assert replica is not None and replica.revision == memory.revision
    assert len(importer.get_memory_history(memory.id)) == 1
    importer.close()


def test_cli_project_command_writes_projection(tmp_path):
    database = tmp_path / "proj-cli.db"
    _cli(database, ["add", "--project", "alpha", "--type", "note",
                    "--content", "Projected through CLI"], client="w", role="writer")
    vault = tmp_path / "vault"
    result = subprocess.run(
        [sys.executable, "-m", "memorycore.cli", "--db", str(database),
         "--client", "cli-admin", "--role", "administrator",
         "project", "alpha", "--vault", str(vault)],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
        env={**os.environ, "MEMORYCORE_ALLOWED_VAULT_ROOTS": str(tmp_path)},
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True and payload["memory_count"] == 1

    denied = subprocess.run(
        [sys.executable, "-m", "memorycore.cli", "--db", str(database),
         "--client", "cli-admin", "--role", "administrator",
         "project", "alpha", "--vault", str(vault)],
        capture_output=True, text=True, cwd=str(REPO_ROOT), env=os.environ.copy(),
    )
    assert denied.returncode != 0
