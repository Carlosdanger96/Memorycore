from __future__ import annotations

"""PostgreSQL storage adapter for the central Memorycore service.

The adapter deliberately matches the SQLiteDatabase operations used by
MemoryService. MCP clients never select a database engine or connect to it.
"""

import json
from typing import Any

from .models import Memory


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

    def close(self) -> None:
        self.engine.dispose()

    def add(self, values: dict[str, Any]) -> Memory:
        from sqlalchemy import text
        with self.engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO memories (id, project_id, memory_type, content, summary, tags, status,
                    created_by, updated_by, client_id, model_provider, model_name, session_id,
                    source_type, source_uri, source_id, confidence, metadata, created_at, updated_at)
                VALUES (:id, :project_id, :memory_type, :content, :summary, CAST(:tags AS jsonb), :status,
                    :created_by, :updated_by, :client_id, :model_provider, :model_name, :session_id,
                    :source_type, :source_uri, :source_id, :confidence, CAST(:metadata AS jsonb), :created_at, :updated_at)
            """), {**values, "tags": json.dumps(values.get("tags", [])), "metadata": json.dumps(values.get("metadata", {}))})
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
                  AND (:memory_type IS NULL OR memory_type = :memory_type)
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

    def update(self, memory_id: str, values: dict[str, Any]) -> Memory | None:
        current = self.get(memory_id)
        if current is None:
            return None
        from sqlalchemy import text
        params = {"id": memory_id, "content": values.get("content", current.content), "summary": values.get("summary", current.summary), "tags": json.dumps(values.get("tags", current.tags)), "status": values.get("status", current.status), "metadata": json.dumps(values.get("metadata", current.metadata)), "updated_at": values.get("updated_at", current.updated_at), "updated_by": values.get("updated_by", current.updated_by)}
        with self.engine.begin() as connection:
            connection.execute(text("""UPDATE memories SET content=:content, summary=:summary,
                tags=CAST(:tags AS jsonb), status=:status, metadata=CAST(:metadata AS jsonb),
                updated_at=:updated_at, updated_by=:updated_by WHERE id=:id"""), params)
        return self.get(memory_id)

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
