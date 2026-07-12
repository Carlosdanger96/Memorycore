from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class MemoryType(StrEnum):
    FACT = "fact"
    DECISION = "decision"
    PREFERENCE = "preference"
    PROCEDURE = "procedure"
    CORRECTION = "correction"
    NOTE = "note"


class MemoryStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    ARCHIVED = "archived"
    SUPERSEDED = "superseded"
    CONTRADICTED = "contradicted"


class SourceType(StrEnum):
    USER_STATEMENT = "user_statement"
    LLM_INFERENCE = "llm_inference"
    CONVERSATION = "conversation"
    DOCUMENT = "document"
    EMAIL = "email"
    GITHUB = "github"
    WEB = "web"
    MANUAL_IMPORT = "manual_import"
    SYSTEM_EVENT = "system_event"


@dataclass(slots=True)
class Memory:
    id: str
    project_id: str
    memory_type: str
    content: str
    summary: str | None
    tags: list[str]
    status: str
    created_by: str | None
    updated_by: str | None
    client_id: str | None
    model_provider: str | None
    model_name: str | None
    session_id: str | None
    source_type: str
    source_uri: str | None
    source_id: str | None
    confidence: float | None
    metadata: dict[str, Any]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_memory_type(value: str) -> str:
    try:
        return MemoryType(value).value
    except ValueError as exc:
        allowed = ", ".join(item.value for item in MemoryType)
        raise ValueError(f"memory_type must be one of: {allowed}") from exc


def validate_status(value: str) -> str:
    try:
        return MemoryStatus(value).value
    except ValueError as exc:
        allowed = ", ".join(item.value for item in MemoryStatus)
        raise ValueError(f"status must be one of: {allowed}") from exc


def validate_source_type(value: str) -> str:
    try:
        return SourceType(value).value
    except ValueError as exc:
        allowed = ", ".join(item.value for item in SourceType)
        raise ValueError(f"source_type must be one of: {allowed}") from exc


def validate_confidence(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence must be a number between 0 and 1") from exc
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    return confidence
