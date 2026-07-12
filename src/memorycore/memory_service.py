from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from .database import SQLiteDatabase
from .postgres_database import PostgresDatabase
from .models import (
    Memory, MemoryStatus, SourceType, validate_confidence, validate_memory_type,
    validate_source_type, validate_status, validate_status_transition,
)
from .retrieval import build_fts_query, render_context


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryService:
    def __init__(self, database_path: str | Path) -> None:
        database_target = str(database_path)
        self.database = PostgresDatabase(database_target) if database_target.startswith(("postgresql://", "postgres://")) else SQLiteDatabase(database_path)
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
        memory_id = memory_id or str(uuid4())
        values = {
            "id": memory_id, "project_id": project_id,
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
        }
        return self.database.add(values, self._event(
            memory_id=memory_id, project_id=project_id, event_type="memory_created",
            client_id=client_id, new_state=values["status"], details={"memory_type": values["memory_type"]},
        ))

    def get_memory(self, memory_id: str) -> Memory | None:
        return self.database.get(memory_id)

    def search_memory(self, *, query: str, project_id: str, limit: int = 10,
                      memory_type: str | None = None,
                      status: str = MemoryStatus.ACTIVE.value) -> list[Memory]:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        if memory_type is not None:
            memory_type = validate_memory_type(memory_type)
        status = validate_status(status)
        fts_query = build_fts_query(query)
        if not fts_query:
            memories = self.database.list_recent(project_id.strip(), limit, status)
        else:
            memories = self.database.search(fts_query, project_id.strip(), limit, memory_type, status)
        priority = {"correction": 0, "decision": 1, "preference": 2, "fact": 3, "procedure": 4, "note": 5}
        return sorted(memories, key=lambda item: (priority.get(item.memory_type, 99), -(item.confidence or 0), item.updated_at))[:limit]

    def find_exact_duplicate(self, *, project_id: str, memory_type: str, content: str) -> Memory | None:
        if not isinstance(self.database, SQLiteDatabase):
            return None
        return self.database.find_exact_active(project_id.strip(), validate_memory_type(memory_type), content.strip())

    def retrieve_context(self, *, query: str, project_id: str, limit: int = 10,
                         memory_type: str | None = None,
                         status: str = MemoryStatus.ACTIVE.value) -> dict[str, Any]:
        memories = self.search_memory(query=query, project_id=project_id, limit=limit,
                                      memory_type=memory_type, status=status)
        items = [memory.to_dict() for memory in memories]
        return {"project_id": project_id, "query": query, "status": status, "count": len(items),
                "memories": items, "context_text": render_context(items)}

    def update_memory(self, memory_id: str, *, content: str | None = None,
                      summary: str | None = None, tags: list[str] | None = None,
                      metadata: dict[str, Any] | None = None,
                      status: str | None = None,
                      updated_by: str | None = None) -> Memory | None:
        current = self.get_memory(memory_id)
        if current is None:
            return None
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
            values["status"] = validate_status_transition(current.status, status)
        if updated_by is not None:
            values["updated_by"] = updated_by
        event_type = "memory_updated"
        if "status" in values:
            event_type = {
                MemoryStatus.ACTIVE.value: "memory_approved",
                MemoryStatus.REJECTED.value: "memory_rejected",
                MemoryStatus.ARCHIVED.value: "memory_archived",
            }.get(values["status"], "memory_status_changed")
        return self.database.update(memory_id, values, self._event(
            memory_id=memory_id, project_id=current.project_id, event_type=event_type,
            client_id=updated_by, previous_state=current.status,
            new_state=values.get("status", current.status), details={"fields": sorted(values.keys())},
        ))

    def archive_memory(self, memory_id: str) -> Memory | None:
        return self.update_memory(memory_id, status=MemoryStatus.ARCHIVED.value)

    def approve_memory(self, memory_id: str, *, approved_by: str) -> Memory | None:
        return self.update_memory(memory_id, status=MemoryStatus.ACTIVE.value, updated_by=approved_by)

    def reject_memory(self, memory_id: str, *, rejected_by: str) -> Memory | None:
        return self.update_memory(memory_id, status=MemoryStatus.REJECTED.value, updated_by=rejected_by)

    def health(self) -> dict[str, Any]:
        return self.database.health()

    def get_memory_history(self, memory_id: str, limit: int = 100) -> list[dict[str, Any]]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        return self.database.list_events(memory_id, limit)

    def backup(self, destination: str | Path) -> None:
        if not isinstance(self.database, SQLiteDatabase):
            raise RuntimeError("SQLite backup is only available for the SQLite storage adapter")
        self.database.backup_to(destination)

    def export_jsonl(self, destination: str | Path) -> int:
        if not isinstance(self.database, SQLiteDatabase):
            raise RuntimeError("JSONL export is only available for the SQLite storage adapter")
        path = Path(destination).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        memories = self.database.all_memories()
        with path.open("w", encoding="utf-8") as handle:
            for memory in memories:
                handle.write(json.dumps({"record_type": "memory", **memory.to_dict()}, ensure_ascii=False) + "\n")
                for event in self.get_memory_history(memory.id):
                    handle.write(json.dumps({"record_type": "memory_event", **event}, ensure_ascii=False) + "\n")
        return len(memories)

    def import_jsonl(self, source: str | Path) -> int:
        if not isinstance(self.database, SQLiteDatabase):
            raise RuntimeError("JSONL import is only available for the SQLite storage adapter")
        imported = 0
        with Path(source).expanduser().open(encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                if record.get("record_type") != "memory" or self.get_memory(record["id"]):
                    continue
                self.add_memory(project_id=record["project_id"], memory_type=record["memory_type"],
                    content=record["content"], summary=record.get("summary"), tags=record.get("tags"),
                    created_by=record.get("created_by"), client_id=record.get("client_id"),
                    model_provider=record.get("model_provider"), model_name=record.get("model_name"),
                    session_id=record.get("session_id"), source_type=record.get("source_type", "manual_import"),
                    source_uri=record.get("source_uri"), source_id=record.get("source_id"),
                    confidence=record.get("confidence"), metadata=record.get("metadata"),
                    status=record.get("status", "active"), memory_id=record["id"])
                imported += 1
        return imported

    @staticmethod
    def _event(*, memory_id: str, project_id: str, event_type: str,
               client_id: str | None, previous_state: str | None = None,
               new_state: str | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"id": str(uuid4()), "memory_id": memory_id, "project_id": project_id,
                "event_type": event_type, "client_id": client_id,
                "previous_state": previous_state, "new_state": new_state,
                "details": details or {}, "created_at": _now()}
