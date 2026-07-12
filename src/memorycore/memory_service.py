from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .database import SQLiteDatabase
from .models import (
    Memory, MemoryStatus, SourceType, validate_confidence, validate_memory_type,
    validate_source_type, validate_status,
)
from .retrieval import build_fts_query, render_context


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryService:
    def __init__(self, database_path: str | Path) -> None:
        self.database = SQLiteDatabase(database_path)
        self.database.initialize()

    def close(self) -> None:
        self.database.close()

    def add_memory(self, *, project_id: str, memory_type: str, content: str,
                   summary: str | None = None, tags: list[str] | None = None,
                   created_by: str | None = None, metadata: dict[str, Any] | None = None,
                   client_id: str | None = None, model_provider: str | None = None,
                   model_name: str | None = None, session_id: str | None = None,
                   source_type: str = SourceType.MANUAL_IMPORT.value,
                   source_uri: str | None = None, source_id: str | None = None,
                   confidence: float | None = None, status: str = MemoryStatus.ACTIVE.value,
                   memory_id: str | None = None) -> Memory:
        project_id = project_id.strip()
        content = content.strip()
        if not project_id:
            raise ValueError("project_id is required")
        if not content:
            raise ValueError("content is required")
        timestamp = _now()
        return self.database.add({
            "id": memory_id or str(uuid4()), "project_id": project_id,
            "memory_type": validate_memory_type(memory_type), "content": content,
            "summary": summary.strip() if summary else None,
            "tags": sorted({tag.strip() for tag in (tags or []) if tag.strip()}),
            "status": validate_status(status), "created_by": created_by,
            "updated_by": created_by, "client_id": client_id,
            "model_provider": model_provider, "model_name": model_name,
            "session_id": session_id, "source_type": validate_source_type(source_type),
            "source_uri": source_uri, "source_id": source_id,
            "confidence": validate_confidence(confidence),
            "metadata": metadata or {}, "created_at": timestamp, "updated_at": timestamp,
        })

    def get_memory(self, memory_id: str) -> Memory | None:
        return self.database.get(memory_id)

    def search_memory(self, *, query: str, project_id: str, limit: int = 10,
                      memory_type: str | None = None) -> list[Memory]:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        if memory_type is not None:
            memory_type = validate_memory_type(memory_type)
        fts_query = build_fts_query(query)
        if not fts_query:
            return self.database.list_recent(project_id.strip(), limit)
        return self.database.search(fts_query, project_id.strip(), limit, memory_type)

    def retrieve_context(self, *, query: str, project_id: str, limit: int = 10,
                         memory_type: str | None = None) -> dict[str, Any]:
        memories = self.search_memory(query=query, project_id=project_id, limit=limit,
                                      memory_type=memory_type)
        items = [memory.to_dict() for memory in memories]
        return {"project_id": project_id, "query": query, "count": len(items),
                "memories": items, "context_text": render_context(items)}

    def update_memory(self, memory_id: str, *, content: str | None = None,
                      summary: str | None = None, tags: list[str] | None = None,
                      metadata: dict[str, Any] | None = None,
                      status: str | None = None,
                      updated_by: str | None = None) -> Memory | None:
        values: dict[str, Any] = {"updated_at": _now()}
        if content is not None:
            if not content.strip():
                raise ValueError("content cannot be empty")
            values["content"] = content.strip()
        if summary is not None:
            values["summary"] = summary.strip() or None
        if tags is not None:
            values["tags"] = sorted({tag.strip() for tag in tags if tag.strip()})
        if metadata is not None:
            values["metadata"] = metadata
        if status is not None:
            values["status"] = validate_status(status)
        if updated_by is not None:
            values["updated_by"] = updated_by
        return self.database.update(memory_id, values)

    def archive_memory(self, memory_id: str) -> Memory | None:
        return self.update_memory(memory_id, status=MemoryStatus.ARCHIVED.value)

    def health(self) -> dict[str, Any]:
        return self.database.health()
