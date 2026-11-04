from __future__ import annotations

"""PostgreSQL storage adapter for the central Memorycore service.

The adapter deliberately matches the SQLiteDatabase operations used by
MemoryService. MCP clients never select a database engine or connect to it.
"""

import json
from typing import Any
from uuid import uuid4

from .models import Memory
from .duplicates import find_candidates


class PostgresDatabase:
    def __init__(self, database_url: str) -> None:
        try:
            from sqlalchemy import create_engine
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "PostgreSQL support is optional. Install it with: pip install -e '.[postgres]'"
            ) from exc
        self._sqlalchemy = __import__("sqlalchemy")
        self.engine = create_engine(database_url, pool_pre_ping=True, future=True)
        self.database_url = database_url

    def initialize(self) -> None:
        text = self._sqlalchemy.text
        with self.engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, memory_type TEXT NOT NULL,
                    content TEXT NOT NULL, summary TEXT, tags JSONB NOT NULL DEFAULT '[]'::jsonb,
                    status TEXT NOT NULL DEFAULT 'active', created_by TEXT, updated_by TEXT,
                    client_id TEXT, model_provider TEXT, model_name TEXT, session_id TEXT,
                    source_type TEXT NOT NULL DEFAULT 'manual_import', source_uri TEXT,
                    source_id TEXT, confidence DOUBLE PRECISION, metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )
            """))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_memories_project_status ON memories(project_id, status)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_memories_project_type ON memories(project_id, memory_type)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_memories_search ON memories USING GIN (to_tsvector('simple', content || ' ' || COALESCE(summary, '')))"))
            connection.execute(text("""CREATE TABLE IF NOT EXISTS memory_events (
                id TEXT PRIMARY KEY, memory_id TEXT NOT NULL REFERENCES memories(id), project_id TEXT NOT NULL,
                event_type TEXT NOT NULL, client_id TEXT, previous_state TEXT, new_state TEXT,
                details JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TEXT NOT NULL,
                event_order BIGINT GENERATED ALWAYS AS IDENTITY
            )"""))
            connection.execute(text("ALTER TABLE memory_events ADD COLUMN IF NOT EXISTS event_order BIGSERIAL"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_memory_events_memory_created ON memory_events(memory_id, created_at DESC)"))
            connection.execute(text("""CREATE TABLE IF NOT EXISTS memory_links (
                id TEXT PRIMARY KEY,
                from_memory_id TEXT NOT NULL REFERENCES memories(id),
                to_memory_id TEXT NOT NULL REFERENCES memories(id),
                relation_type TEXT NOT NULL CHECK (relation_type IN ('supersedes','corrects','contradicts')),
                created_by TEXT, created_at TEXT NOT NULL,
                UNIQUE(from_memory_id, to_memory_id, relation_type)
            )"""))

    def close(self) -> None:
        self.engine.dispose()

    def add(self, values: dict[str, Any], audit_event: dict[str, Any] | None = None) -> Memory:
        from sqlalchemy import text
        with self.engine.begin() as connection:
            if values["status"] == "active":
                self._reject_duplicate(connection, values["project_id"], values["content"])
            connection.execute(text("""
                INSERT INTO memories (id, project_id, memory_type, content, summary, tags, status,
                    created_by, updated_by, client_id, model_provider, model_name, session_id,
                    source_type, source_uri, source_id, confidence, metadata, created_at, updated_at)
                VALUES (:id, :project_id, :memory_type, :content, :summary, CAST(:tags AS jsonb), :status,
                    :created_by, :updated_by, :client_id, :model_provider, :model_name, :session_id,
                    :source_type, :source_uri, :source_id, :confidence, CAST(:metadata AS jsonb), :created_at, :updated_at)
            """), {**values, "tags": json.dumps(values.get("tags", [])), "metadata": json.dumps(values.get("metadata", {}))})
            if audit_event:
                self._insert_event(connection, audit_event)
        memory = self.get(values["id"])
        if memory is None:
            raise RuntimeError("inserted memory could not be reloaded")
        return memory

    def get(self, memory_id: str) -> Memory | None:
        from sqlalchemy import text
        with self.engine.connect() as connection:
            row = connection.execute(text("SELECT * FROM memories WHERE id = :id"), {"id": memory_id}).mappings().first()
        return self._from_row(row) if row else None

    def search(self, fts_query: str, project_id: str, limit: int,
               memory_type: str | None = None, status: str = "active") -> list[Memory]:
        from sqlalchemy import text
        with self.engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT * FROM memories
                WHERE project_id = :project_id AND status = :status
                  AND (CAST(:memory_type AS TEXT) IS NULL OR memory_type = :memory_type)
                  AND to_tsvector('simple', content || ' ' || COALESCE(summary, ''))
                      @@ plainto_tsquery('simple', :query)
                ORDER BY updated_at DESC LIMIT :limit
            """), {"project_id": project_id, "status": status, "memory_type": memory_type,
                    "query": fts_query.replace('"', '').replace(' AND ', ' '), "limit": limit}).mappings().all()
        return [self._from_row(row) for row in rows]

    def list_recent(self, project_id: str, limit: int, status: str = "active") -> list[Memory]:
        from sqlalchemy import text
        with self.engine.connect() as connection:
            rows = connection.execute(text("SELECT * FROM memories WHERE project_id=:project_id AND status=:status ORDER BY updated_at DESC LIMIT :limit"), {"project_id": project_id, "status": status, "limit": limit}).mappings().all()
        return [self._from_row(row) for row in rows]

    def update(self, memory_id: str, values: dict[str, Any], audit_event: dict[str, Any] | None = None) -> Memory | None:
        current = self.get(memory_id)
        if current is None:
            return None
        from sqlalchemy import text
        params = {"id": memory_id, "content": values.get("content", current.content), "summary": values.get("summary", current.summary), "tags": json.dumps(values.get("tags", current.tags)), "status": values.get("status", current.status), "metadata": json.dumps(values.get("metadata", current.metadata)), "updated_at": values.get("updated_at", current.updated_at), "updated_by": values.get("updated_by", current.updated_by)}
        with self.engine.begin() as connection:
            if params["status"] == "active" and (
                current.status != "active" or params["content"] != current.content
            ):
                self._reject_duplicate(connection, current.project_id, params["content"], memory_id)
            connection.execute(text("""UPDATE memories SET content=:content, summary=:summary,
                tags=CAST(:tags AS jsonb), status=:status, metadata=CAST(:metadata AS jsonb),
                updated_at=:updated_at, updated_by=:updated_by WHERE id=:id"""), params)
            if audit_event:
                self._insert_event(connection, audit_event)
        return self.get(memory_id)

    def list_events(self, memory_id: str, limit: int = 100) -> list[dict[str, Any]]:
        from sqlalchemy import text
        with self.engine.connect() as connection:
            rows = connection.execute(text("SELECT * FROM memory_events WHERE memory_id=:memory_id ORDER BY event_order ASC LIMIT :limit"), {"memory_id": memory_id, "limit": limit}).mappings().all()
        return [{key: value for key, value in row.items() if key != "event_order"} for row in rows]

    def snapshot_records(self) -> tuple[list[Memory], list[dict[str, Any]], list[dict[str, Any]]]:
        from sqlalchemy import text

        with self.engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            memories = [self._from_row(row) for row in connection.execute(
                text("SELECT * FROM memories ORDER BY id")
            ).mappings().all()]
            events = [{key: value for key, value in row.items() if key != "event_order"}
                      for row in connection.execute(
                          text("SELECT * FROM memory_events ORDER BY event_order")
                      ).mappings().all()]
            links = [dict(row) for row in connection.execute(
                text("SELECT * FROM memory_links ORDER BY id")
            ).mappings().all()]
        return memories, events, links

    def restore_records(self, memories: list[dict[str, Any]],
                        events: list[dict[str, Any]], links: list[dict[str, Any]]) -> int:
        from sqlalchemy import text

        with self.engine.begin() as connection:
            for table in ("memories", "memory_events", "memory_links"):
                if connection.execute(text(f"SELECT 1 FROM {table} LIMIT 1")).first():
                    raise ValueError("JSONL restore requires an empty Memorycore database")
            for item in memories:
                connection.execute(text("""INSERT INTO memories (
                    id, project_id, memory_type, content, summary, tags, status,
                    created_by, updated_by, client_id, model_provider, model_name,
                    session_id, source_type, source_uri, source_id, confidence,
                    metadata, created_at, updated_at
                ) VALUES (
                    :id, :project_id, :memory_type, :content, :summary,
                    CAST(:tags AS jsonb), :status, :created_by, :updated_by,
                    :client_id, :model_provider, :model_name, :session_id,
                    :source_type, :source_uri, :source_id, :confidence,
                    CAST(:metadata AS jsonb), :created_at, :updated_at
                )"""), {**item, "tags": json.dumps(item["tags"]),
                         "metadata": json.dumps(item["metadata"])})
            for event in events:
                self._insert_event(connection, event)
            for link in links:
                connection.execute(text("""INSERT INTO memory_links (
                    id, from_memory_id, to_memory_id, relation_type, created_by, created_at
                ) VALUES (:id, :from_memory_id, :to_memory_id, :relation_type,
                          :created_by, :created_at)"""), link)
        return len(memories)

    def replace_memory(self, original: Memory, replacement: dict[str, Any], *,
                       relation_type: str, original_status: str,
                       original_event: dict[str, Any],
                       replacement_event: dict[str, Any]) -> Memory:
        """Create a replacement, retire its source, link, and audit in one transaction."""
        from sqlalchemy import text

        with self.engine.begin() as connection:
            self._project_write_lock(connection, replacement["project_id"])
            locked = connection.execute(
                text("SELECT status FROM memories WHERE id=:id FOR UPDATE"), {"id": original.id}
            ).scalar_one_or_none()
            if locked != "active":
                raise ValueError("only active memories can be replaced")
            self._reject_duplicate(
                connection, replacement["project_id"], replacement["content"], original.id
            )
            connection.execute(text("""INSERT INTO memories (
                id, project_id, memory_type, content, summary, tags, status,
                created_by, updated_by, client_id, model_provider, model_name,
                session_id, source_type, source_uri, source_id, confidence,
                metadata, created_at, updated_at
            ) VALUES (
                :id, :project_id, :memory_type, :content, :summary,
                CAST(:tags AS jsonb), :status, :created_by, :updated_by,
                :client_id, :model_provider, :model_name, :session_id,
                :source_type, :source_uri, :source_id, :confidence,
                CAST(:metadata AS jsonb), :created_at, :updated_at
            )"""), {**replacement, "tags": json.dumps(replacement["tags"]),
                    "metadata": json.dumps(replacement["metadata"])})
            connection.execute(text("""UPDATE memories SET status=:status,
                updated_by=:updated_by, updated_at=:updated_at WHERE id=:id"""),
                {"status": original_status, "updated_by": replacement["created_by"],
                 "updated_at": replacement["updated_at"], "id": original.id})
            connection.execute(text("""INSERT INTO memory_links (
                id, from_memory_id, to_memory_id, relation_type, created_by, created_at
            ) VALUES (:id, :from_id, :to_id, :relation_type, :created_by, :created_at)"""),
                {"id": str(uuid4()), "from_id": replacement["id"], "to_id": original.id,
                 "relation_type": relation_type, "created_by": replacement["created_by"],
                 "created_at": replacement["created_at"]})
            self._insert_event(connection, original_event)
            self._insert_event(connection, replacement_event)
        memory = self.get(replacement["id"])
        if memory is None:
            raise RuntimeError("replacement memory could not be reloaded")
        return memory

    @staticmethod
    def _project_write_lock(connection: Any, project_id: str) -> None:
        from sqlalchemy import text

        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:project_id))"),
            {"project_id": project_id},
        )

    def _duplicate_candidates(self, connection: Any, project_id: str,
                              content: str, exclude_id: str | None = None) -> list[dict[str, Any]]:
        from sqlalchemy import text

        rows = connection.execute(text("""SELECT id, content FROM memories
            WHERE project_id=:project_id AND status='active' AND id<>:exclude_id"""),
            {"project_id": project_id, "exclude_id": exclude_id or ""}).mappings().all()
        return find_candidates(rows, content)

    def duplicate_candidates(self, project_id: str, content: str,
                             exclude_id: str | None = None) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            return self._duplicate_candidates(connection, project_id, content, exclude_id)

    def _reject_duplicate(self, connection: Any, project_id: str,
                          content: str, exclude_id: str | None = None) -> None:
        self._project_write_lock(connection, project_id)
        matches = self._duplicate_candidates(connection, project_id, content, exclude_id)
        if matches:
            first = matches[0]
            raise ValueError(f"{first['reason']} duplicate memory exists: {first['memory_id']}")

    def add_link(self, *, from_memory_id: str, to_memory_id: str,
                 relation_type: str, created_by: str | None, created_at: str) -> None:
        from sqlalchemy import text
        with self.engine.begin() as connection:
            connection.execute(text("""INSERT INTO memory_links (id, from_memory_id, to_memory_id,
                relation_type, created_by, created_at) VALUES (:id, :from_memory_id, :to_memory_id,
                :relation_type, :created_by, :created_at) ON CONFLICT DO NOTHING"""),
                {"id": str(uuid4()), "from_memory_id": from_memory_id,
                 "to_memory_id": to_memory_id, "relation_type": relation_type,
                 "created_by": created_by, "created_at": created_at})

    def list_links(self, memory_id: str) -> list[dict[str, Any]]:
        from sqlalchemy import text
        with self.engine.connect() as connection:
            rows = connection.execute(text("""SELECT * FROM memory_links
                WHERE from_memory_id=:id OR to_memory_id=:id ORDER BY created_at ASC"""),
                {"id": memory_id}).mappings().all()
        return [dict(row) for row in rows]

    def checkpoint(self) -> dict[str, Any]:
        # WAL checkpointing is a SQLite concept; PostgreSQL checkpoints itself.
        return {"ok": True, "busy": False, "log_frames": None, "checkpointed_frames": None,
                "note": "PostgreSQL manages its own WAL; no-op"}

    @staticmethod
    def _insert_event(connection: Any, event: dict[str, Any]) -> None:
        from sqlalchemy import text
        connection.execute(text("""INSERT INTO memory_events (id, memory_id, project_id, event_type,
            client_id, previous_state, new_state, details, created_at) VALUES (:id, :memory_id,
            :project_id, :event_type, :client_id, :previous_state, :new_state,
            CAST(:details AS jsonb), :created_at)"""), {**event, "details": json.dumps(event.get("details", {}))})

    def health(self) -> dict[str, Any]:
        from sqlalchemy import text
        with self.engine.connect() as connection:
            count = connection.execute(text("SELECT COUNT(*) FROM memories")).scalar_one()
            version = connection.execute(text("SHOW server_version")).scalar_one()
        return {"ok": True, "database": "postgresql", "memory_count": int(count), "postgres_version": version, "fts5": False}

    @staticmethod
    def _from_row(row: Any) -> Memory:
        data = dict(row)
        return Memory(id=data["id"], project_id=data["project_id"], memory_type=data["memory_type"],
            content=data["content"], summary=data["summary"], tags=data["tags"], status=data["status"],
            created_by=data["created_by"], updated_by=data["updated_by"], client_id=data["client_id"],
            model_provider=data["model_provider"], model_name=data["model_name"], session_id=data["session_id"],
            source_type=data["source_type"], source_uri=data["source_uri"], source_id=data["source_id"],
            confidence=data["confidence"], metadata=data["metadata"], created_at=data["created_at"], updated_at=data["updated_at"])
