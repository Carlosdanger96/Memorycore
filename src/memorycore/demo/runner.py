from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from time import perf_counter
from typing import Any, Sequence

from ..memory_service import MemoryService
from ..omni_service import error_signature


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _synthetic_repository() -> Path:
    source_fixture = _repository_root() / "demo" / "synthetic-agent"
    if source_fixture.is_dir():
        return source_fixture
    packaged_fixture = Path(__file__).resolve().parent / "fixtures" / "synthetic-agent"
    if packaged_fixture.is_dir():
        return packaged_fixture
    raise RuntimeError("synthetic agent fixture is missing from this installation")


def run_demo(workspace: str | Path | None = None) -> dict[str, Any]:
    started = perf_counter()
    synthetic_repo = _synthetic_repository()
    output_root = Path(workspace).expanduser().resolve() if workspace else Path(
        tempfile.mkdtemp(prefix="omni-memory-harness-")
    )
    output_root.mkdir(parents=True, exist_ok=True)
    database = output_root / "omni-demo.db"
    vault = output_root / "synthetic-vault"
    vault.mkdir(parents=True, exist_ok=True)
    service = MemoryService(database, scanner_roots=[synthetic_repo], vault_roots=[vault])
    try:
        if service.omni is None:
            raise RuntimeError("Omni Memory Harness did not initialize")
        omni = service.omni
        behaviors = omni.scan_repository(
            synthetic_repo, project_id="omni-demo", repository="synthetic-agent",
        )
        behavior_ids = {item["behavior_id"] for item in behaviors}
        required = {
            "agent.task.plan", "agent.tool.select", "agent.tool.execute",
            "agent.output.verify", "agent.memory.write_request", "agent.loop.terminate",
        }
        if not required <= behavior_ids:
            raise RuntimeError(f"synthetic behavior scan is incomplete: {sorted(required - behavior_ids)}")

        old_memory = service.add_memory(
            project_id="omni-demo", memory_type="procedure",
            content="Tool output verification is optional before execution continues.",
            summary="Old verification policy", tags=["verification", "policy"],
            created_by="demo-seed", source_type="system_event", confidence=0.8,
            metadata={"claim_key": "agent.output.verification_policy"},
        )
        new_memory = service.add_memory(
            project_id="omni-demo", memory_type="procedure",
            content="Tool output must be verified before execution continues.",
            summary="Current verification policy", tags=["verification", "policy"],
            created_by="demo-seed", source_type="system_event", confidence=0.99,
            metadata={"claim_key": "agent.output.verification_policy"},
        )

        signature = error_signature(
            error_type="invalid_tool_output", message="Tool returned ok=false at C:\\demo\\agent.py",
            behavior_id="agent.output.verify", tool_name="synthetic_lookup",
            verification_result="false", repository="synthetic-agent",
            metadata={"phase": "verification"},
        )
        failed = omni.create_trajectory(
            project_id="omni-demo", task_type="repository_modification",
            task_description="Use a tool result without validating its success flag",
            agent_id="synthetic-agent-v1", repository="synthetic-agent",
            source_revision=behaviors[0]["source_revision"],
            provenance={"provider": "deterministic-demo", "run": "failed"},
        )
        failed_events = [
            ("task_started", ["agent.task.plan"], None, {"task": "modify repository"}, None),
            ("tool_called", ["agent.tool.execute"], "synthetic_lookup", {"query": "target"}, None),
            ("tool_result", ["agent.tool.execute"], "synthetic_lookup", None, {"ok": False, "value": "stale"}),
            ("task_failed", ["agent.output.verify"], None, None, {"reason": "unverified tool failure"}),
        ]
        for sequence, (event_type, event_behaviors, tool, input_data, output_data) in enumerate(failed_events, 1):
            omni.append_trajectory_event(
                failed["trajectory_id"], event_type=event_type, sequence=sequence,
                request_id=f"failed-{sequence}", behavior_ids=event_behaviors,
                tool_name=tool, input_data=input_data, output_data=output_data,
                error_signature_value=signature if event_type == "task_failed" else None,
                outcome="failed" if event_type == "task_failed" else None,
            )

        correction = omni.extract_correction(failed["trajectory_id"])
        correction = omni.approve_correction(correction["correction_id"], approved_by="demo-approver")
        context_pack = omni.build_context_pack(
            project_id="omni-demo", query="tool output verification",
            task_type="repository_modification", behavior_ids=["agent.output.verify"],
            repository="synthetic-agent",
        )
        retrieved_ids = [item["correction"]["correction_id"] for item in context_pack["corrections"]]
        if correction["correction_id"] not in retrieved_ids:
            raise RuntimeError("approved correction was not retrieved before the second run")

        successful = omni.create_trajectory(
            project_id="omni-demo", task_type="repository_modification",
            task_description="Validate a tool result before continuing execution",
            agent_id="synthetic-agent-v1", repository="synthetic-agent",
            source_revision=behaviors[0]["source_revision"],
            parent_trajectory_id=failed["trajectory_id"],
            provenance={"provider": "deterministic-demo", "run": "corrected"},
        )
        success_events = [
            ("task_started", ["agent.task.plan"], [], None),
            ("context_retrieved", ["agent.output.verify"], [correction["correction_id"]], None),
            ("correction_applied", ["agent.output.verify"], [correction["correction_id"]], None),
            ("tool_called", ["agent.tool.execute"], [], "synthetic_lookup"),
            ("tool_result", ["agent.tool.execute"], [], "synthetic_lookup"),
            ("verification_run", ["agent.output.verify"], [correction["correction_id"]], None),
            ("task_completed", ["agent.loop.terminate"], [correction["correction_id"]], None),
        ]
        completed_event_id = ""
        for sequence, (event_type, event_behaviors, correction_ids, tool) in enumerate(success_events, 1):
            saved_event = omni.append_trajectory_event(
                successful["trajectory_id"], event_type=event_type, sequence=sequence,
                request_id=f"success-{sequence}", behavior_ids=event_behaviors,
                correction_ids=correction_ids, tool_name=tool,
                output_data={"ok": True, "verified": event_type == "verification_run"}
                if event_type in {"tool_result", "verification_run"} else None,
                outcome="success" if event_type == "task_completed" else None,
            )
            if event_type == "task_completed":
                completed_event_id = saved_event["event_id"]

        outcome_record = omni.record_correction_outcome(
            correction["correction_id"], trajectory_id=successful["trajectory_id"],
            outcome="succeeded", evidence_event_id=completed_event_id,
            actor="synthetic-agent-v1", request_id="demo-correction-outcome-success",
            details={"verification": "passed"},
        )
        if outcome_record["correction"]["success_count"] != 1:
            raise RuntimeError("successful correction reuse was not materialized")

        findings = omni.audit_memories(project_id="omni-demo")
        conflicts = [item for item in findings if item["finding_type"] == "contradiction"]
        if not conflicts:
            raise RuntimeError("deterministic auditor did not identify the seeded contradiction")
        approved_finding = omni.approve_revision(conflicts[0]["finding_id"], approved_by="demo-approver")
        revision_events = service.database.list_omni_revision_events(approved_finding["finding_id"])
        if not revision_events:
            raise RuntimeError("approved revision did not create an immutable decision event")
        if service.get_memory(old_memory.id) is None or service.get_memory(new_memory.id) is None:
            raise RuntimeError("audit revision destroyed an original memory")

        projection = omni.project_obsidian(vault, project_id="omni-demo")
        second_projection = omni.project_obsidian(vault, project_id="omni-demo")
        if second_projection["written"]:
            raise RuntimeError("Obsidian projection is not idempotent")
        successful_record = omni.get_trajectory(successful["trajectory_id"])
        if not successful_record or not any(item["event_type"] == "verification_run" for item in successful_record["events"]):
            raise RuntimeError("corrected trajectory did not perform verification")

        report = {
            "ok": True, "generated_at": _now(), "mode": "offline-deterministic",
            "duration_seconds": round(perf_counter() - started, 4),
            "workspace": str(output_root), "database": str(database),
            "vault": str(vault), "behavior_count": len(behaviors),
            "repository_revision": behaviors[0]["source_revision"],
            "failed_trajectory_id": failed["trajectory_id"],
            "successful_trajectory_id": successful["trajectory_id"],
            "error_signature": signature, "correction_id": correction["correction_id"],
            "retrieved_correction_ids": retrieved_ids,
            "correction_use_count": outcome_record["correction"]["use_count"],
            "correction_success_count": outcome_record["correction"]["success_count"],
            "correction_outcome_event_id": outcome_record["event"]["event_id"],
            "finding_id": approved_finding["finding_id"],
            "revision_decision_id": revision_events[-1]["event_id"],
            "replacement_memory_id": approved_finding["proposed_record"]["created_memory_id"],
            "original_memory_ids_preserved": [old_memory.id, new_memory.id],
            "projection_root": projection["root"],
            "projected_file_count": len(projection["written"]),
        }
        report_path = output_root / "demo-report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["report"] = str(report_path)
        return report
    finally:
        service.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the offline Omni Memory Harness demonstration")
    parser.add_argument("--workspace", type=Path, help="isolated demo output directory")
    args = parser.parse_args(argv)
    report = run_demo(args.workspace)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
