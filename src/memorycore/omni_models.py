from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class OmniRecordType(StrEnum):
    BEHAVIOR = "behavior"
    TRAJECTORY = "trajectory"
    CORRECTION = "correction"
    AUDIT_FINDING = "audit_finding"


class CorrectionOperation(StrEnum):
    ADD_STEP = "add_step"
    REPLACE_STEP = "replace_step"
    CHANGE_TOOL = "change_tool"
    EXPAND_SEARCH = "expand_search"
    REQUIRE_VERIFICATION = "require_verification"
    ESCALATE_APPROVAL = "escalate_approval"


class AuditFindingType(StrEnum):
    DUPLICATE = "duplicate"
    CONTRADICTION = "contradiction"
    SUPERSESSION = "supersession"
    STALE = "stale"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    SCOPE_MISMATCH = "scope_mismatch"
    PROVENANCE_GAP = "provenance_gap"
    CONSOLIDATION_CANDIDATE = "consolidation_candidate"


class TrajectoryEventType(StrEnum):
    TASK_STARTED = "task_started"
    CONTEXT_RETRIEVED = "context_retrieved"
    CORRECTION_APPLIED = "correction_applied"
    MODEL_CALLED = "model_called"
    TOOL_CALLED = "tool_called"
    TOOL_RESULT = "tool_result"
    DECISION_RECORDED = "decision_recorded"
    ARTIFACT_CREATED = "artifact_created"
    VERIFICATION_RUN = "verification_run"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"


@dataclass(slots=True)
class SourceEntrypoint:
    path: str
    symbol: str
    start_line: int
    end_line: int
    evidence_type: str = "static_analysis"
    confidence: float = 1.0


@dataclass(slots=True)
class BehaviorRecord:
    behavior_id: str
    project_id: str
    name: str
    description: str
    repository: str
    repository_path: str
    source_revision: str
    language: str
    entrypoints: list[SourceEntrypoint] = field(default_factory=list)
    configuration_sources: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    generated_by: str = "deterministic-scanner-v1"
    confidence: float = 1.0
    created_at: str = ""
    updated_at: str = ""
    status: str = "active"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Trajectory:
    trajectory_id: str
    project_id: str
    task_type: str
    task_description: str
    agent_id: str
    repository: str
    source_revision: str
    started_at: str
    completed_at: str | None = None
    outcome: str = "running"
    reward: float | None = None
    error_signature: str | None = None
    parent_trajectory_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TrajectoryEvent:
    event_id: str
    trajectory_id: str
    sequence: int
    event_type: str
    timestamp: str
    parent_event_id: str | None = None
    behavior_ids: list[str] = field(default_factory=list)
    memory_ids: list[str] = field(default_factory=list)
    correction_ids: list[str] = field(default_factory=list)
    tool_name: str | None = None
    redacted_input: Any = None
    redacted_output: Any = None
    artifact_refs: list[str] = field(default_factory=list)
    error_signature: str | None = None
    outcome: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExperienceCorrection:
    correction_id: str
    project_id: str
    task_type: str
    behavior_ids: list[str]
    repository: str
    trigger: dict[str, Any]
    error_signature: str | None
    operation: str
    instruction: str
    evidence_trajectory_ids: list[str]
    successful_trajectory_ids: list[str] = field(default_factory=list)
    confidence: float = 0.5
    status: str = "pending_review"
    approved_by: str | None = None
    supersedes: str | None = None
    use_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    created_at: str = ""
    updated_at: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AuditFinding:
    finding_id: str
    project_id: str
    finding_type: str
    affected_memory_ids: list[str]
    affected_correction_ids: list[str]
    explanation: str
    evidence: list[dict[str, Any]]
    recommended_action: str
    proposed_record: dict[str, Any]
    model: str
    prompt_version: str
    confidence: float
    requires_approval: bool
    status: str
    reviewed_by: str | None
    reviewed_at: str | None
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_correction_operation(value: str) -> str:
    try:
        return CorrectionOperation(value).value
    except ValueError as exc:
        raise ValueError("unsupported correction operation") from exc


def validate_event_type(value: str) -> str:
    try:
        return TrajectoryEventType(value).value
    except ValueError as exc:
        raise ValueError("unsupported trajectory event type") from exc


def validate_finding_type(value: str) -> str:
    try:
        return AuditFindingType(value).value
    except ValueError as exc:
        raise ValueError("unsupported audit finding type") from exc
