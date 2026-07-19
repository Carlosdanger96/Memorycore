from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, TYPE_CHECKING
from uuid import uuid4

from .behavior import RepositoryScanner
from .audit import AuditProvider, DeterministicAuditProvider, OpenAIResponsesAuditProvider
from .database import SQLiteDatabase
from .models import MemoryStatus
from .omni_models import (
    AuditFinding, AuditFindingType, BehaviorRecord, ExperienceCorrection,
    OmniRecordType, Trajectory, TrajectoryEvent,
    validate_correction_event_type, validate_correction_operation,
    validate_correction_outcome, validate_event_type,
)
from .omni_security import redact
from .projections import ObsidianProjection
from .experience import (
    CorrectionProvider, DeterministicCorrectionProvider, OpenAIResponsesCorrectionProvider,
)

if TYPE_CHECKING:
    from .memory_service import MemoryService


_MACHINE_PATH = re.compile(r"(?:[A-Za-z]:)?[/\\](?:[^\s:/\\]+[/\\])+[^\s:]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def error_signature(*, error_type: str, message: str, behavior_id: str | None,
                    tool_name: str | None, verification_result: str | None,
                    repository: str, metadata: dict[str, Any] | None = None) -> str:
    normalized = _MACHINE_PATH.sub("<path>", message.lower())
    normalized = re.sub(r"\b\d{4}-\d{2}-\d{2}t[^\s]+", "<timestamp>", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()[:500]
    stable = {
        "error_type": error_type.strip().lower(), "message": normalized,
        "behavior_id": behavior_id, "tool_name": tool_name,
        "verification_result": verification_result, "repository": repository,
        "metadata": redact(metadata or {}),
    }
    digest = hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()[:20]
    return f"{stable['error_type']}:{digest}"


class OmniHarnessService:
    def __init__(self, memory_service: MemoryService,
                 scanner_roots: list[str | Path] | None = None,
                 vault_roots: list[str | Path] | None = None) -> None:
        if not isinstance(memory_service.database, SQLiteDatabase):
            raise RuntimeError("Omni Memory Harness currently supports the SQLite prototype only")
        self.memory_service = memory_service
        self.database = memory_service.database
        configured = scanner_roots
        if configured is None:
            raw = os.getenv("MEMORYCORE_SCAN_ROOTS", "")
            configured = [item for item in raw.split(os.pathsep) if item]
        self.scanner_roots = [Path(item).expanduser().resolve() for item in configured]
        configured_vaults = vault_roots
        if configured_vaults is None:
            raw_vaults = os.getenv("MEMORYCORE_VAULT_ROOTS", "")
            configured_vaults = [item for item in raw_vaults.split(os.pathsep) if item]
        self.vault_roots = [Path(item).expanduser().resolve() for item in configured_vaults]

    def health(self) -> dict[str, Any]:
        counts = {}
        for record_type in OmniRecordType:
            counts[record_type.value] = self.database.count_omni_records(record_type.value)
        return {"ok": True, "component": "omni-memory-harness", "counts": counts,
                "scanner_roots": [str(path) for path in self.scanner_roots],
                "vault_roots": [str(path) for path in self.vault_roots]}

    def project_obsidian(self, vault_root: str | Path, *, project_id: str) -> dict[str, Any]:
        return ObsidianProjection(self.database, self.vault_roots).project(
            vault_root, project_id=project_id,
        )

    def scan_repository(self, repository_path: str | Path, *, project_id: str,
                        repository: str | None = None) -> list[dict[str, Any]]:
        if not self.scanner_roots:
            raise ValueError("repository scanning requires explicit MEMORYCORE_SCAN_ROOTS")
        timestamp = _now()
        scanner = RepositoryScanner(self.scanner_roots)
        records = scanner.scan(repository_path, project_id=project_id, repository=repository)
        existing = self.database.list_omni_records(
            OmniRecordType.BEHAVIOR.value, project_id, repository=repository or Path(repository_path).name,
            limit=10_000,
        )
        current_keys = {(record.behavior_id, record.source_revision) for record in records}
        for record in existing:
            key = (record["behavior_id"], record["source_revision"])
            if key not in current_keys and record.get("status") == "active":
                record["status"] = "stale"
                record["updated_at"] = timestamp
                self._put_behavior(record)
        for record in records:
            record.created_at = timestamp
            record.updated_at = timestamp
            self._put_behavior(record.to_dict())
        return [record.to_dict() for record in records]

    def _put_behavior(self, record: dict[str, Any]) -> None:
        storage_id = f"{record['behavior_id']}@{record['source_revision']}"
        self.database.put_omni_record(
            OmniRecordType.BEHAVIOR.value, storage_id, record,
            project_id=record["project_id"], status=record["status"],
            repository=record["repository"], source_revision=record["source_revision"],
            confidence=record.get("confidence"),
        )

    def search_behaviors(self, *, project_id: str, query: str = "",
                         repository: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        records = self.database.list_omni_records(
            OmniRecordType.BEHAVIOR.value, project_id, status="active",
            repository=repository, limit=10_000,
        )
        tokens = set(re.findall(r"[a-z0-9_]+", query.lower()))
        if tokens:
            records = [record for record in records if tokens <= set(re.findall(
                r"[a-z0-9_]+", " ".join((record["behavior_id"], record["name"], record["description"])).lower()
            )) or any(token in json.dumps(record).lower() for token in tokens)]
        return records[:max(1, min(limit, 100))]

    def get_behavior(self, behavior_id: str, *, project_id: str) -> dict[str, Any] | None:
        matches = [record for record in self.search_behaviors(project_id=project_id, limit=100)
                   if record["behavior_id"] == behavior_id]
        return matches[0] if matches else None

    def behavior_impact(self, behavior_id: str, *, project_id: str) -> dict[str, Any] | None:
        behavior = self.get_behavior(behavior_id, project_id=project_id)
        if behavior is None:
            return None
        return {
            "behavior_id": behavior_id, "source_revision": behavior["source_revision"],
            "entrypoints": behavior["entrypoints"], "tests": behavior["tests"],
            "dependencies": behavior["dependencies"],
            "configuration_sources": behavior["configuration_sources"],
        }

    def create_trajectory(self, *, project_id: str, task_type: str,
                          task_description: str, agent_id: str, repository: str,
                          source_revision: str, parent_trajectory_id: str | None = None,
                          metadata: dict[str, Any] | None = None,
                          provenance: dict[str, Any] | None = None,
                          trajectory_id: str | None = None) -> dict[str, Any]:
        if not all(item.strip() for item in (project_id, task_type, task_description, agent_id, repository)):
            raise ValueError("trajectory identity fields are required")
        if parent_trajectory_id:
            parent = self.database.get_omni_record(
                parent_trajectory_id, OmniRecordType.TRAJECTORY.value,
            )
            if parent is None:
                raise ValueError("parent trajectory not found")
            if parent["project_id"] != project_id or parent["repository"] != repository:
                raise ValueError("parent trajectory is outside the trajectory scope")
        record = Trajectory(
            trajectory_id=trajectory_id or f"traj_{uuid4().hex}", project_id=project_id.strip(),
            task_type=task_type.strip(), task_description=task_description.strip()[:4000],
            agent_id=agent_id.strip(), repository=repository.strip(),
            source_revision=source_revision.strip() or "unversioned", started_at=_now(),
            parent_trajectory_id=parent_trajectory_id, metadata=redact(metadata or {}),
            provenance=redact(provenance or {}),
        ).to_dict()
        self._put_trajectory(record)
        return record

    def _put_trajectory(self, record: dict[str, Any]) -> None:
        self.database.put_omni_record(
            OmniRecordType.TRAJECTORY.value, record["trajectory_id"], record,
            project_id=record["project_id"], status=record["outcome"],
            repository=record["repository"], source_revision=record["source_revision"],
            task_type=record["task_type"], error_signature=record.get("error_signature"),
        )

    def append_trajectory_event(self, trajectory_id: str, *, event_type: str,
                                sequence: int, request_id: str | None = None,
                                parent_event_id: str | None = None,
                                behavior_ids: list[str] | None = None,
                                memory_ids: list[str] | None = None,
                                correction_ids: list[str] | None = None,
                                tool_name: str | None = None,
                                input_data: Any = None, output_data: Any = None,
                                artifact_refs: list[str] | None = None,
                                error_signature_value: str | None = None,
                                outcome: str | None = None,
                                metadata: dict[str, Any] | None = None,
                                event_id: str | None = None) -> dict[str, Any]:
        validate_event_type(event_type)
        trajectory = self.database.get_omni_record(trajectory_id, OmniRecordType.TRAJECTORY.value)
        if trajectory is None:
            raise ValueError("trajectory not found")
        existing = self.database.list_omni_events(trajectory_id)
        if request_id:
            for item in existing:
                if item.get("request_id") == request_id:
                    return item
        if any(item["event_type"] in {"task_completed", "task_failed"} for item in existing):
            raise ValueError("cannot append events after a terminal trajectory event")
        if sequence != len(existing) + 1:
            raise ValueError(f"trajectory sequence must be {len(existing) + 1}")
        if parent_event_id and parent_event_id not in {item["event_id"] for item in existing}:
            raise ValueError("parent event is not part of this trajectory")
        project_id = trajectory["project_id"]
        registered_behaviors = self.database.list_omni_records(
            OmniRecordType.BEHAVIOR.value, project_id, status="active", limit=10_000,
        )
        if registered_behaviors:
            known_behaviors = {item["behavior_id"] for item in registered_behaviors}
            unknown_behaviors = set(behavior_ids or []) - known_behaviors
            if unknown_behaviors:
                raise ValueError(f"unknown behavior references: {sorted(unknown_behaviors)}")
        for memory_id in memory_ids or []:
            memory = self.memory_service.get_memory(memory_id)
            if memory is None or memory.project_id != project_id:
                raise ValueError(f"memory reference is outside the trajectory project: {memory_id}")
        for correction_id in correction_ids or []:
            correction = self.database.get_omni_record(
                correction_id, OmniRecordType.CORRECTION.value,
            )
            if correction is None or correction["project_id"] != project_id:
                raise ValueError(f"correction reference is outside the trajectory project: {correction_id}")
        redacted_input, redacted_output = redact(input_data), redact(output_data)
        if len(json.dumps([redacted_input, redacted_output], default=str)) > 65_536:
            raise ValueError("trajectory event content exceeds 65536 bytes")
        event = TrajectoryEvent(
            event_id=event_id or f"event_{uuid4().hex}", trajectory_id=trajectory_id,
            sequence=sequence, event_type=event_type, timestamp=_now(),
            parent_event_id=parent_event_id, behavior_ids=behavior_ids or [],
            memory_ids=memory_ids or [], correction_ids=correction_ids or [],
            tool_name=tool_name, redacted_input=redacted_input,
            redacted_output=redacted_output, artifact_refs=artifact_refs or [],
            error_signature=error_signature_value, outcome=outcome,
            metadata=redact(metadata or {}), request_id=request_id,
        ).to_dict()
        saved, _ = self.database.append_omni_event(event)
        if event_type == "correction_applied":
            for correction_id in sorted(set(correction_ids or [])):
                self._append_correction_event(
                    correction_id=correction_id, event_type="applied",
                    trajectory_id=trajectory_id, evidence_event_id=saved["event_id"],
                    actor=str(event["metadata"].get("client_id") or trajectory["agent_id"]),
                    request_id=f"trajectory-event:{saved['event_id']}:{correction_id}",
                    details={"trajectory_sequence": sequence},
                )
        if event_type in {"task_completed", "task_failed"}:
            trajectory["completed_at"] = event["timestamp"]
            trajectory["outcome"] = "success" if event_type == "task_completed" else "failed"
            trajectory["error_signature"] = error_signature_value
            trajectory["reward"] = 1.0 if event_type == "task_completed" else 0.0
            self._put_trajectory(trajectory)
        return saved

    def get_trajectory(self, trajectory_id: str) -> dict[str, Any] | None:
        record = self.database.get_omni_record(trajectory_id, OmniRecordType.TRAJECTORY.value)
        if record is None:
            return None
        return {**record, "events": self.database.list_omni_events(trajectory_id)}

    def propose_correction(self, *, project_id: str, task_type: str,
                           behavior_ids: list[str], repository: str,
                           operation: str, instruction: str,
                           evidence_trajectory_ids: list[str],
                           error_signature_value: str | None = None,
                           trigger: dict[str, Any] | None = None,
                           confidence: float = 0.7,
                           provenance: dict[str, Any] | None = None,
                           deterministic_demo: bool = False) -> dict[str, Any]:
        operation = validate_correction_operation(operation)
        if not instruction.strip() or not evidence_trajectory_ids:
            raise ValueError("correction instruction and evidence are required")
        for trajectory_id in evidence_trajectory_ids:
            evidence = self.database.get_omni_record(
                trajectory_id, OmniRecordType.TRAJECTORY.value,
            )
            if evidence is None:
                raise ValueError(f"evidence trajectory not found: {trajectory_id}")
            if evidence["project_id"] != project_id or evidence["repository"] != repository:
                raise ValueError("evidence trajectory is outside the correction scope")
        timestamp = _now()
        record = ExperienceCorrection(
            correction_id=f"corr_{uuid4().hex}", project_id=project_id,
            task_type=task_type, behavior_ids=sorted(set(behavior_ids)),
            repository=repository, trigger=redact(trigger or {}),
            error_signature=error_signature_value, operation=operation,
            instruction=instruction.strip(), evidence_trajectory_ids=evidence_trajectory_ids,
            confidence=max(0.0, min(float(confidence), 1.0)),
            status="active" if deterministic_demo else "pending_review",
            approved_by="demo-approver" if deterministic_demo else None,
            created_at=timestamp, updated_at=timestamp,
            provenance=redact(provenance or {"extractor": "deterministic-v1"}),
        ).to_dict()
        self._put_correction(record)
        actor = str(record["approved_by"] or record["provenance"].get("client_id") or
                    record["provenance"].get("extractor") or "system")
        self._append_correction_event(
            correction_id=record["correction_id"], event_type="proposed", actor=actor,
            details={"evidence_trajectory_ids": evidence_trajectory_ids},
        )
        if deterministic_demo:
            self._append_correction_event(
                correction_id=record["correction_id"], event_type="approved",
                actor=record["approved_by"] or "demo-approver",
                details={"deterministic_demo": True},
            )
        return record

    def extract_correction(self, failed_trajectory_id: str, *,
                           successful_trajectory_id: str | None = None,
                           provider: CorrectionProvider | None = None) -> dict[str, Any]:
        failed = self.get_trajectory(failed_trajectory_id)
        if failed is None or failed.get("outcome") != "failed":
            raise ValueError("a failed trajectory is required for correction extraction")
        successful = self.get_trajectory(successful_trajectory_id) if successful_trajectory_id else None
        if successful_trajectory_id and successful is None:
            raise ValueError("successful comparison trajectory not found")
        if provider is None:
            use_live = os.getenv("MEMORYCORE_USE_LIVE_GPT56", "").lower() in {"1", "true", "yes"}
            provider = OpenAIResponsesCorrectionProvider.from_environment() if use_live else DeterministicCorrectionProvider()
        proposal = provider.extract(failed, successful)
        event_ids = {event["event_id"] for event in failed["events"]}
        cited_ids = set(proposal.get("evidence_event_ids") or [])
        if not cited_ids or not cited_ids <= event_ids:
            raise ValueError("correction provider cited unknown trajectory events")
        return self.propose_correction(
            project_id=failed["project_id"], task_type=proposal["task_type"],
            behavior_ids=proposal["behavior_ids"], repository=proposal["repository"],
            operation=proposal["operation"], instruction=proposal["instruction"],
            evidence_trajectory_ids=[failed_trajectory_id],
            error_signature_value=proposal.get("error_signature"),
            trigger=proposal.get("trigger"), confidence=proposal.get("confidence", 0.5),
            provenance={"extractor": provider.model, "prompt_version": provider.prompt_version,
                        "evidence_event_ids": sorted(cited_ids)},
        )

    def _put_correction(self, record: dict[str, Any]) -> None:
        self.database.put_omni_record(
            OmniRecordType.CORRECTION.value, record["correction_id"], record,
            project_id=record["project_id"], status=record["status"],
            repository=record["repository"], task_type=record["task_type"],
            error_signature=record.get("error_signature"), behavior_ids=record["behavior_ids"],
            confidence=record["confidence"],
        )

    def approve_correction(self, correction_id: str, *, approved_by: str) -> dict[str, Any]:
        record = self.database.get_omni_record(correction_id, OmniRecordType.CORRECTION.value)
        if record is None:
            raise ValueError("correction not found")
        if record["status"] != "pending_review":
            raise ValueError("only pending corrections may be approved")
        record["status"], record["approved_by"], record["updated_at"] = "active", approved_by, _now()
        self._put_correction(record)
        self._append_correction_event(
            correction_id=correction_id, event_type="approved", actor=approved_by,
            details={"previous_status": "pending_review", "new_status": "active"},
        )
        return record

    def _append_correction_event(
        self, *, correction_id: str, event_type: str, actor: str,
        trajectory_id: str | None = None, outcome: str | None = None,
        evidence_event_id: str | None = None, request_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        validate_correction_event_type(event_type)
        event = {
            "event_id": f"correction_event_{uuid4().hex}",
            "correction_id": correction_id,
            "trajectory_id": trajectory_id,
            "event_type": event_type,
            "outcome": outcome,
            "evidence_event_id": evidence_event_id,
            "actor": actor.strip() or "system",
            "request_id": request_id,
            "details": redact(details or {}),
            "created_at": _now(),
        }
        saved, _ = self.database.add_omni_correction_event(event)
        return saved

    def list_correction_events(self, correction_id: str) -> list[dict[str, Any]]:
        correction = self.database.get_omni_record(
            correction_id, OmniRecordType.CORRECTION.value,
        )
        if correction is None:
            raise ValueError("correction not found")
        return self.database.list_omni_correction_events(correction_id)

    def record_correction_outcome(
        self, correction_id: str, *, trajectory_id: str, outcome: str,
        evidence_event_id: str, actor: str, request_id: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        outcome = validate_correction_outcome(outcome)
        if not actor.strip() or not request_id.strip() or not evidence_event_id.strip():
            raise ValueError("actor, request_id, and evidence_event_id are required")
        prior = next((
            event for event in self.database.list_omni_correction_events(correction_id)
            if event.get("request_id") == request_id
        ), None)
        if prior is not None:
            correction = self.database.get_omni_record(
                correction_id, OmniRecordType.CORRECTION.value,
            )
            return {"correction": correction, "event": prior, "created": False}
        correction = self.database.get_omni_record(
            correction_id, OmniRecordType.CORRECTION.value,
        )
        if correction is None:
            raise ValueError("correction not found")
        if correction["status"] != "active":
            raise ValueError("only active corrections may record outcomes")
        trajectory = self.get_trajectory(trajectory_id)
        if trajectory is None:
            raise ValueError("trajectory not found")
        if (trajectory["project_id"] != correction["project_id"] or
                trajectory["repository"] != correction["repository"]):
            raise ValueError("trajectory is outside the correction scope")
        events = trajectory["events"]
        applied = any(
            event["event_type"] == "correction_applied" and
            correction_id in event.get("correction_ids", [])
            for event in events
        )
        if not applied:
            raise ValueError("trajectory did not apply this correction")
        evidence = next((event for event in events if event["event_id"] == evidence_event_id), None)
        if evidence is None:
            raise ValueError("outcome evidence event is not part of the trajectory")
        if outcome == "succeeded" and evidence["event_type"] != "task_completed":
            raise ValueError("successful correction outcome requires task_completed evidence")
        if outcome == "failed" and evidence["event_type"] != "task_failed":
            raise ValueError("failed correction outcome requires task_failed evidence")
        correction = dict(correction)
        correction["use_count"] = int(correction.get("use_count", 0)) + 1
        if outcome == "succeeded":
            correction["success_count"] = int(correction.get("success_count", 0)) + 1
            correction["successful_trajectory_ids"] = sorted(set(
                correction.get("successful_trajectory_ids", []) + [trajectory_id]
            ))
        elif outcome == "failed":
            correction["failure_count"] = int(correction.get("failure_count", 0)) + 1
        correction["updated_at"] = _now()
        event = {
            "event_id": f"correction_event_{uuid4().hex}",
            "correction_id": correction_id,
            "trajectory_id": trajectory_id,
            "event_type": outcome,
            "outcome": outcome,
            "evidence_event_id": evidence_event_id,
            "actor": actor.strip(),
            "request_id": request_id.strip(),
            "details": redact(details or {}),
            "created_at": correction["updated_at"],
        }
        saved, created = self.database.record_omni_correction_outcome(correction, event)
        current = self.database.get_omni_record(
            correction_id, OmniRecordType.CORRECTION.value,
        )
        return {"correction": current, "event": saved, "created": created}

    def search_corrections(self, *, project_id: str, task_type: str,
                           behavior_ids: list[str] | None = None,
                           repository: str | None = None,
                           error_signature_value: str | None = None,
                           tool_name: str | None = None,
                           limit: int = 10) -> list[dict[str, Any]]:
        records = self.database.list_omni_records(
            OmniRecordType.CORRECTION.value, project_id, status="active", limit=1000,
        )
        requested_behaviors = set(behavior_ids or [])
        ranked = []
        for record in records:
            score, reasons = 0.0, []
            if record["task_type"] == task_type:
                score += 3.0; reasons.append("exact task type")
            if repository and record["repository"] == repository:
                score += 2.0; reasons.append("repository match")
            overlap = requested_behaviors & set(record["behavior_ids"])
            if overlap:
                score += 2.0 * len(overlap); reasons.append("behavior overlap")
            if error_signature_value and record.get("error_signature") == error_signature_value:
                score += 5.0; reasons.append("exact error signature")
            if tool_name and record.get("trigger", {}).get("tool_name") == tool_name:
                score += 1.0; reasons.append("tool match")
            uses = record.get("use_count", 0)
            if uses:
                score += record.get("success_count", 0) / uses
            score += float(record.get("confidence", 0.0))
            ranked.append({"correction": record, "score": round(score, 4), "why_matched": reasons,
                           "supporting_evidence": record["evidence_trajectory_ids"],
                           "known_limitations": []})
        ranked.sort(key=lambda item: (-item["score"], item["correction"]["correction_id"]))
        return ranked[:max(1, min(limit, 100))]

    def build_context_pack(self, *, project_id: str, query: str, task_type: str,
                           behavior_ids: list[str] | None = None,
                           repository: str | None = None, limit: int = 10) -> dict[str, Any]:
        memory_context = self.memory_service.retrieve_context(
            query=query, project_id=project_id, limit=limit,
        )
        corrections = self.search_corrections(
            project_id=project_id, task_type=task_type, behavior_ids=behavior_ids,
            repository=repository, limit=limit,
        )
        return {
            "project_id": project_id, "query": query, "task_type": task_type,
            "memories": memory_context["memories"], "corrections": corrections,
            "context_text": memory_context["context_text"] + "\n\n" + "\n".join(
                f"Correction [{item['correction']['operation']}]: {item['correction']['instruction']}"
                for item in corrections
            ),
        }

    def audit_memories(self, *, project_id: str, provider: AuditProvider | None = None,
                       model: str | None = None) -> list[dict[str, Any]]:
        memories = self.memory_service.search_memory(
            query="", project_id=project_id, limit=100, status=MemoryStatus.ACTIVE.value,
        )
        if provider is None:
            use_live = os.getenv("MEMORYCORE_USE_LIVE_GPT56", "").lower() in {"1", "true", "yes"}
            provider = OpenAIResponsesAuditProvider.from_environment() if use_live else DeterministicAuditProvider()
        memory_dicts = [memory.to_dict() for memory in memories]
        memory_ids = {memory["id"] for memory in memory_dicts}
        findings: list[dict[str, Any]] = []
        for proposal in provider.find(memory_dicts):
            affected_ids = proposal.get("affected_memory_ids") or []
            if not affected_ids or not set(affected_ids) <= memory_ids:
                raise ValueError("audit provider referenced an unknown memory")
            finding_type = str(proposal.get("finding_type"))
            if finding_type not in {item.value for item in AuditFindingType}:
                raise ValueError("audit provider returned an unsupported finding type")
            proposed = proposal.get("proposed_record") or {}
            if not isinstance(proposed.get("content"), str) or not proposed["content"].strip():
                raise ValueError("audit provider returned an invalid proposed record")
            timestamp = _now()
            finding = AuditFinding(
                finding_id=f"finding_{uuid4().hex}", project_id=project_id,
                finding_type=finding_type, affected_memory_ids=affected_ids,
                affected_correction_ids=proposal.get("affected_correction_ids") or [],
                explanation=str(proposal.get("explanation") or ""),
                evidence=proposal.get("evidence") or [],
                recommended_action=str(proposal.get("recommended_action") or "review"),
                proposed_record=proposed, model=provider.model,
                prompt_version=provider.prompt_version,
                confidence=max(0.0, min(float(proposal.get("confidence", 0.5)), 1.0)),
                requires_approval=True, status="pending_review", reviewed_by=None,
                reviewed_at=None, created_at=timestamp,
            ).to_dict()
            self._put_finding(finding)
            findings.append(finding)
        return findings

    def _put_finding(self, record: dict[str, Any]) -> None:
        self.database.put_omni_record(
            OmniRecordType.AUDIT_FINDING.value, record["finding_id"], record,
            project_id=record["project_id"], status=record["status"],
            confidence=record["confidence"],
        )

    def approve_revision(self, finding_id: str, *, approved_by: str) -> dict[str, Any]:
        finding = self.database.get_omni_record(finding_id, OmniRecordType.AUDIT_FINDING.value)
        if finding is None:
            raise ValueError("audit finding not found")
        if finding["status"] != "pending_review" or not finding["requires_approval"]:
            raise ValueError("finding is not awaiting approval")
        memory_ids = finding["affected_memory_ids"]
        if not memory_ids:
            raise ValueError("finding has no affected memories")
        original = self.memory_service.get_memory(memory_ids[0])
        if original is None or original.status != MemoryStatus.ACTIVE.value:
            raise ValueError("original active memory is unavailable")
        proposed = finding["proposed_record"]
        replacement = self.memory_service.supersede_memory(
            original.id, content=proposed["content"], summary=proposed.get("summary"),
            tags=proposed.get("tags"), updated_by=approved_by,
        )
        for memory_id in memory_ids[1:]:
            memory = self.memory_service.get_memory(memory_id)
            if memory is not None and memory.status == MemoryStatus.ACTIVE.value:
                self.memory_service.update_memory(
                    memory_id, status=MemoryStatus.ARCHIVED.value, updated_by=approved_by,
                )
        finding["status"], finding["reviewed_by"], finding["reviewed_at"] = "approved", approved_by, _now()
        finding["proposed_record"]["created_memory_id"] = replacement.id
        self._put_finding(finding)
        self.database.add_omni_revision_event({
            "event_id": f"revision_{uuid4().hex}", "finding_id": finding_id,
            "event_type": "revision_approved", "reviewer": approved_by,
            "details": {"replacement_memory_id": replacement.id, "preserved_memory_ids": memory_ids},
            "created_at": finding["reviewed_at"],
        })
        return finding

    def list_findings(self, *, project_id: str, status: str | None = None) -> list[dict[str, Any]]:
        return self.database.list_omni_records(
            OmniRecordType.AUDIT_FINDING.value, project_id, status=status, limit=100,
        )
