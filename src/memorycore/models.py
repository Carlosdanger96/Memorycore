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
    ACTIVE = "active"
    ARCHIVED = "archived"
    SUPERSEDED = "superseded"


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
