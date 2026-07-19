from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable

from .memory_service import MemoryService
from .models import Memory, MemoryStatus, MemoryType, SourceType


class CorrectionOperation(StrEnum):
    ADD_STEP = "add_step"
    REMOVE_STEP = "remove_step"
    REPLACE_STEP = "replace_step"
    REORDER_STEPS = "reorder_steps"
    ADD_CONSTRAINT = "add_constraint"
    CHANGE_TOOL = "change_tool"
    NARROW_SCOPE = "narrow_scope"
    EXPAND_SEARCH = "expand_search"
    REQUIRE_VERIFICATION = "require_verification"
    ESCALATE_APPROVAL = "escalate_approval"


class CorrectionOutcome(StrEnum):
    UNTESTED = "untested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass(slots=True, frozen=True)
class ExperienceCorrection:
    task_type: str
    trigger: str
    failed_behavior: str
    operation: str
    instruction: str
    tools: tuple[str, ...] = ()
    repositories: tuple[str, ...] = ()
    applicability: tuple[str, ...] = ()
    evidence: str | None = None

    def validate(self) -> None:
        required = {
            "task_type": self.task_type,
            "trigger": self.trigger,
            "failed_behavior": self.failed_behavior,
            "instruction": self.instruction,
        }
        for field, value in required.items():
            if not value.strip():
                raise ValueError(f"{field} is required")
        try:
            CorrectionOperation(self.operation)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in CorrectionOperation)
            raise ValueError(f"operation must be one of: {allowed}") from exc

    def metadata(self) -> dict[str, Any]:
        return {
            "schema": "memorycore.experience_correction.v1",
            "task_type": self.task_type.strip(),
            "trigger": self.trigger.strip(),
            "failed_behavior": self.failed_behavior.strip(),
            "operation": CorrectionOperation(self.operation).value,
            "instruction": self.instruction.strip(),
            "tools": _normalized(self.tools),
            "repositories": _normalized(self.repositories),
            "applicability": _normalized(self.applicability),
            "evidence": self.evidence.strip() if self.evidence else None,
            "reuse": {"attempts": 0, "successes": 0, "failures": 0, "last_outcome": "untested"},
        }

    def searchable_content(self) -> str:
        fields = [
            f"Task type: {self.task_type.strip()}",
            f"Trigger: {self.trigger.strip()}",
            f"Failed behavior: {self.failed_behavior.strip()}",
            f"Correction operation: {CorrectionOperation(self.operation).value}",
            f"Instruction: {self.instruction.strip()}",
        ]
        if self.tools:
            fields.append(f"Tools: {', '.join(_normalized(self.tools))}")
        if self.repositories:
            fields.append(f"Repositories: {', '.join(_normalized(self.repositories))}")
        if self.applicability:
            fields.append(f"Applicability: {', '.join(_normalized(self.applicability))}")
        if self.evidence:
            fields.append(f"Evidence: {self.evidence.strip()}")
        return "\n".join(fields)


class ExperienceCorrectionLedger:
    """Typed correction records backed by the normal Memorycore lifecycle.

    This deliberately reuses MemoryService storage, provenance, audit, approval,
    export and retrieval instead of introducing a second correction database.
    """

    def __init__(self, service: MemoryService) -> None:
        self.service = service

    def capture(
        self,
        *,
        project_id: str,
        correction: ExperienceCorrection,
        created_by: str | None = None,
        client_id: str | None = None,
        model_provider: str | None = None,
        model_name: str | None = None,
        session_id: str | None = None,
        source_type: str = SourceType.SYSTEM_EVENT.value,
        source_uri: str | None = None,
        source_id: str | None = None,
        confidence: float | None = None,
        status: str = MemoryStatus.PENDING.value,
    ) -> Memory:
        correction.validate()
        tags = [
            "experience-correction",
            f"task:{_tag(correction.task_type)}",
            f"operation:{CorrectionOperation(correction.operation).value}",
            *[f"tool:{_tag(tool)}" for tool in correction.tools],
            *[f"repo:{_tag(repo)}" for repo in correction.repositories],
        ]
        return self.service.add_memory(
            project_id=project_id,
            memory_type=MemoryType.EXPERIENCE_CORRECTION.value,
            content=correction.searchable_content(),
            summary=correction.instruction.strip(),
            tags=tags,
            created_by=created_by,
            client_id=client_id,
            model_provider=model_provider,
            model_name=model_name,
            session_id=session_id,
            source_type=source_type,
            source_uri=source_uri,
            source_id=source_id,
            confidence=confidence,
            status=status,
            metadata=correction.metadata(),
        )

    def retrieve(
        self,
        *,
        project_id: str,
        task_type: str,
        query: str = "",
        tools: Iterable[str] = (),
        repositories: Iterable[str] = (),
        limit: int = 5,
        minimum_confidence: float = 0.0,
        status: str = MemoryStatus.ACTIVE.value,
    ) -> list[Memory]:
        if not 0 <= minimum_confidence <= 1:
            raise ValueError("minimum_confidence must be between 0 and 1")
        search_terms = " ".join(
            item for item in [task_type, query, *tools, *repositories] if item and item.strip()
        )
        candidates = self.service.search_memory(
            query=search_terms,
            project_id=project_id,
            memory_type=MemoryType.EXPERIENCE_CORRECTION.value,
            status=status,
            limit=min(100, max(limit * 5, 25)),
        )
        requested_tools = set(_normalized(tools))
        requested_repositories = set(_normalized(repositories))
        matches: list[Memory] = []
        for memory in candidates:
            metadata = memory.metadata
            if metadata.get("schema") != "memorycore.experience_correction.v1":
                continue
            if metadata.get("task_type") != task_type.strip():
                continue
            if memory.confidence is not None and memory.confidence < minimum_confidence:
                continue
            correction_tools = set(metadata.get("tools") or [])
            correction_repositories = set(metadata.get("repositories") or [])
            if requested_tools and correction_tools and not requested_tools.intersection(correction_tools):
                continue
            if requested_repositories and correction_repositories and not requested_repositories.intersection(correction_repositories):
                continue
            matches.append(memory)
            if len(matches) >= limit:
                break
        return matches

    def record_outcome(
        self,
        memory_id: str,
        *,
        outcome: str,
        updated_by: str,
        evidence: str | None = None,
    ) -> Memory:
        try:
            normalized_outcome = CorrectionOutcome(outcome)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in CorrectionOutcome)
            raise ValueError(f"outcome must be one of: {allowed}") from exc
        memory = self.service.get_memory(memory_id)
        if memory is None:
            raise ValueError("experience correction not found")
        if memory.memory_type != MemoryType.EXPERIENCE_CORRECTION.value:
            raise ValueError("memory is not an experience correction")
        metadata = dict(memory.metadata)
        reuse = dict(metadata.get("reuse") or {})
        reuse["attempts"] = int(reuse.get("attempts", 0)) + 1
        reuse["successes"] = int(reuse.get("successes", 0))
        reuse["failures"] = int(reuse.get("failures", 0))
        if normalized_outcome == CorrectionOutcome.SUCCEEDED:
            reuse["successes"] += 1
        elif normalized_outcome == CorrectionOutcome.FAILED:
            reuse["failures"] += 1
        reuse["last_outcome"] = normalized_outcome.value
        if evidence:
            reuse["last_evidence"] = evidence.strip()
        metadata["reuse"] = reuse
        updated = self.service.update_memory(memory_id, metadata=metadata, updated_by=updated_by)
        if updated is None:  # Defensive; the record existed above.
            raise RuntimeError("experience correction disappeared during update")
        return updated


def _normalized(values: Iterable[str]) -> list[str]:
    return sorted({value.strip() for value in values if value and value.strip()})


def _tag(value: str) -> str:
    return "-".join(value.strip().lower().replace("/", "-").split())
