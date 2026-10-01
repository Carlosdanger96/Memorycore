from __future__ import annotations

from datetime import datetime, timezone
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from .database import SQLiteDatabase
from .postgres_database import PostgresDatabase
from .models import (
    Memory, MemoryStatus, SourceType, validate_confidence, validate_memory_type,
    validate_source_type, validate_status, validate_status_transition,
)
from .policy import RevisionConflictError
from .retrieval import build_fts_query, rank_memories, render_context


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

    def add_memory_or_duplicate(self, **kwargs: Any) -> dict[str, Any]:
        """Create a memory, or return the existing live record for identical content.

        Both the application pre-check and the database unique partial index
        enforce duplicate protection, so independent processes racing on the
        same content always converge on exactly one live record.
        """
        if not isinstance(self.database, SQLiteDatabase):
            memory = self.add_memory(**kwargs)
            return {"duplicate": False, "memory": memory.to_dict()}
        project_id = str(kwargs.get("project_id", "")).strip()
        memory_type = validate_memory_type(str(kwargs.get("memory_type", "")))
        content = str(kwargs.get("content", "")).strip()
        existing = self.database.find_live_by_fingerprint(project_id, memory_type, content)
        if existing is not None:
            return {"duplicate": True, "memory": existing.to_dict()}
        try:
            memory = self.add_memory(memory_type=memory_type, content=content, **{
                key: value for key, value in kwargs.items()
                if key not in {"memory_type", "content"}})
        except sqlite3.IntegrityError:
            existing = self.database.find_live_by_fingerprint(project_id, memory_type, content)
            if existing is not None:
                return {"duplicate": True, "memory": existing.to_dict()}
            raise
        return {"duplicate": False, "memory": memory.to_dict()}

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
        candidate_limit = min(100, max(25, limit * 5))
        if not fts_query:
            memories = self.database.list_recent(project_id.strip(), candidate_limit, status)
        else:
            memories = self.database.search(fts_query, project_id.strip(), candidate_limit, memory_type, status)
        if status == MemoryStatus.ACTIVE.value and query.strip() and isinstance(self.database, SQLiteDatabase):
            exact = self.database.find_exact_active_any(project_id.strip(), query)
            if exact is not None and all(item.id != exact.id for item in memories):
                memories.insert(0, exact)
        return [item.memory for item in rank_memories(query, memories, limit)]

    def find_exact_duplicate(self, *, project_id: str, memory_type: str, content: str) -> Memory | None:
        if not isinstance(self.database, SQLiteDatabase):
            return None
        return self.database.find_live_by_fingerprint(project_id.strip(), validate_memory_type(memory_type), content.strip())

    def retrieve_context(self, *, query: str, project_id: str, limit: int = 10,
                         memory_type: str | None = None,
                         status: str = MemoryStatus.ACTIVE.value) -> dict[str, Any]:
        memories = self.search_memory(query=query, project_id=project_id, limit=limit,
                                      memory_type=memory_type, status=status)
        items = [memory.to_dict() for memory in memories]
        ranked = rank_memories(query, memories, limit)
        return {"project_id": project_id, "query": query, "status": status, "count": len(items),
                "memories": items, "retrieval": [{"memory_id": item.memory.id, "score": round(item.score, 4), "reasons": list(item.reasons)} for item in ranked],
                "context_text": render_context(items)}

    def update_memory(self, memory_id: str, *, content: str | None = None,
                      summary: str | None = None, tags: list[str] | None = None,
                      metadata: dict[str, Any] | None = None,
                      status: str | None = None,
                      updated_by: str | None = None,
                      expected_revision: int | None = None) -> Memory | None:
        current = self.get_memory(memory_id)
        if current is None:
            return None
        if expected_revision is not None and int(expected_revision) != int(current.revision):
            raise RevisionConflictError(memory_id, int(current.revision), int(expected_revision))
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
        result = self.database.update(memory_id, values, self._event(
            memory_id=memory_id, project_id=current.project_id, event_type=event_type,
            client_id=updated_by, previous_state=current.status,
            new_state=values.get("status", current.status),
            details={"fields": sorted(values.keys()), "revision": int(current.revision) + 1},
        ), expected_revision=expected_revision)
        if result is not None and int(result.revision) <= int(current.revision):
            raise RevisionConflictError(memory_id, int(current.revision), int(current.revision))
        return result

    def archive_memory(self, memory_id: str) -> Memory | None:
        return self.update_memory(memory_id, status=MemoryStatus.ARCHIVED.value)

    def approve_memory(self, memory_id: str, *, approved_by: str) -> Memory | None:
        return self.update_memory(memory_id, status=MemoryStatus.ACTIVE.value, updated_by=approved_by)

    def reject_memory(self, memory_id: str, *, rejected_by: str) -> Memory | None:
        return self.update_memory(memory_id, status=MemoryStatus.REJECTED.value, updated_by=rejected_by)

    def supersede_memory(self, memory_id: str, *, content: str, updated_by: str,
                         summary: str | None = None, tags: list[str] | None = None) -> Memory:
        return self._replace_memory(memory_id, content=content, updated_by=updated_by,
            summary=summary, tags=tags, relation_type="supersedes", original_status=MemoryStatus.SUPERSEDED.value)

    def correct_memory(self, memory_id: str, *, content: str, updated_by: str,
                       summary: str | None = None, tags: list[str] | None = None) -> Memory:
        return self._replace_memory(memory_id, content=content, updated_by=updated_by,
            summary=summary, tags=tags, relation_type="corrects", original_status=MemoryStatus.SUPERSEDED.value)

    def _replace_memory(self, memory_id: str, *, content: str, updated_by: str,
                        summary: str | None, tags: list[str] | None,
                        relation_type: str, original_status: str) -> Memory:
        if not isinstance(self.database, SQLiteDatabase):
            raise RuntimeError("atomic replacement is currently available for SQLite")
        original = self.get_memory(memory_id)
        if original is None:
            raise ValueError("memory not found")
        if original.status != MemoryStatus.ACTIVE.value:
            raise ValueError("only active memories can be replaced")
        if not content.strip():
            raise ValueError("content is required")
        now, replacement_id = _now(), str(uuid4())
        replacement = {"id": replacement_id, "project_id": original.project_id,
            "memory_type": original.memory_type, "content": content.strip(),
            "summary": summary.strip() if summary else original.summary,
            "tags": sorted({tag.strip() for tag in (tags if tags is not None else original.tags) if tag.strip()}),
            "status": MemoryStatus.ACTIVE.value, "created_by": updated_by, "updated_by": updated_by,
            "client_id": updated_by, "model_provider": original.model_provider, "model_name": original.model_name,
            "session_id": original.session_id, "source_type": original.source_type,
            "source_uri": original.source_uri, "source_id": original.source_id,
            "confidence": original.confidence, "metadata": original.metadata,
            "created_at": now, "updated_at": now}
        return self.database.replace_memory(original, replacement, relation_type=relation_type,
            original_status=original_status,
            original_event=self._event(memory_id=original.id, project_id=original.project_id,
                event_type="memory_superseded", client_id=updated_by, previous_state="active", new_state=original_status),
            replacement_event=self._event(memory_id=replacement_id, project_id=original.project_id,
                event_type="memory_created", client_id=updated_by, new_state="active",
                details={"relation_type": relation_type, "replaces": original.id}))

    def health(self) -> dict[str, Any]:
        return self.database.health()

    def integrity_check(self) -> dict[str, Any]:
        if not isinstance(self.database, SQLiteDatabase):
            raise RuntimeError("integrity check is only available for the SQLite storage adapter")
        return self.database.integrity_check()

    def get_memory_history(self, memory_id: str, limit: int = 100) -> list[dict[str, Any]]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        return self.database.list_events(memory_id, limit)

    def backup(self, destination: str | Path) -> None:
        if not isinstance(self.database, SQLiteDatabase):
            raise RuntimeError("SQLite backup is only available for the SQLite storage adapter")
        self.database.backup_to(destination)

    def export_jsonl(self, destination: str | Path) -> int:
        """Full-fidelity export: memories, timestamps, provenance, events, and links."""
        if not isinstance(self.database, SQLiteDatabase):
            raise RuntimeError("JSONL export is only available for the SQLite storage adapter")
        path = Path(destination).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        memories = self.database.all_memories()
        with path.open("w", encoding="utf-8") as handle:
            for memory in memories:
                handle.write(json.dumps({"record_type": "memory", **memory.to_dict()}, ensure_ascii=False) + "\n")
            for event in self.database.all_events():
                handle.write(json.dumps({"record_type": "memory_event", **event}, ensure_ascii=False) + "\n")
            for link in self.database.all_links():
                handle.write(json.dumps({"record_type": "memory_link", **link}, ensure_ascii=False) + "\n")
        return len(memories)

    def import_jsonl(self, source: str | Path) -> int:
        """Full-fidelity import preserving IDs, timestamps, provenance, events, and links."""
        if not isinstance(self.database, SQLiteDatabase):
            raise RuntimeError("JSONL import is only available for the SQLite storage adapter")
        memories: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        links: list[dict[str, Any]] = []
        memory_ids: set[str] = set()
        with Path(source).expanduser().open(encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                record_type = record.get("record_type")
                if record_type == "memory":
                    if record["id"] in memory_ids:
                        continue
                    memory_ids.add(record["id"])
                    memories.append(record)
                elif record_type == "memory_event":
                    event = {key: value for key, value in record.items() if key != "record_type"}
                    events.append(event)
                elif record_type == "memory_link":
                    link = {key: value for key, value in record.items() if key != "record_type"}
                    links.append(link)
                else:
                    raise ValueError(f"unknown JSONL record type: {record_type}")
        if not memories:
            raise ValueError("JSONL import requires at least one memory record")
        memories_without_events = memory_ids - {event["memory_id"] for event in events}
        if memories_without_events:
            raise ValueError(
                "JSONL import requires full-fidelity records: memories without audit "
                "events cannot be imported (re-export with audit history)")
        missing_events = [e for e in events if e["memory_id"] not in memory_ids]
        if missing_events:
            raise ValueError("JSONL import references events for unknown memories")
        self.database.replace_all_memories(memories, events, links)
        return len(memories)

    def restore(self, source: str | Path) -> None:
        """Restore from a backup, preserving the original database file first."""
        if not isinstance(self.database, SQLiteDatabase):
            raise RuntimeError("restore is only available for the SQLite storage adapter")
        original = self.database.path
        backup_of_original = original.with_name(original.name + ".pre-restore")
        if original.exists():
            shutil.copy2(original, backup_of_original)
        try:
            self.database.restore_from(source)
        except BaseException:
            if backup_of_original.exists():
                shutil.copy2(backup_of_original, original)
            raise
        finally:
            if backup_of_original.exists():
                backup_of_original.unlink()

    @staticmethod
    def _event(*, memory_id: str, project_id: str, event_type: str,
               client_id: str | None, previous_state: str | None = None,
               new_state: str | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"id": str(uuid4()), "memory_id": memory_id, "project_id": project_id,
                "event_type": event_type, "client_id": client_id,
                "previous_state": previous_state, "new_state": new_state,
                "details": details or {}, "created_at": _now()}
