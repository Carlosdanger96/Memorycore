from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .models import Memory

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    memory_type TEXT NOT NULL CHECK (
        memory_type IN ('fact','decision','preference','procedure','correction','note')
    ),
    content TEXT NOT NULL,
    summary TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active' CHECK (
        status IN ('active','archived','superseded')
    ),
    created_by TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memories_project_status
ON memories(project_id, status);

CREATE INDEX IF NOT EXISTS idx_memories_project_type
ON memories(project_id, memory_type);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    id UNINDEXED,
    content,
    summary,
    tags,
    tokenize = 'unicode61'
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memory_fts(id, content, summary, tags)
    VALUES (new.id, new.content, COALESCE(new.summary, ''), new.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    DELETE FROM memory_fts WHERE id = old.id;
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    DELETE FROM memory_fts WHERE id = old.id;
    INSERT INTO memory_fts(id, content, summary, tags)
    VALUES (new.id, new.content, COALESCE(new.summary, ''), new.tags);
END;
"""


class SQLiteDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row

    def initialize(self) -> None:
        with self._lock:
            self.connection.executescript(SCHEMA_SQL)
            self.connection.commit()

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def add(self, values: dict[str, Any]) -> Memory:
        with self._lock:
            self.connection.execute(
                """
                INSERT INTO memories (
                    id, project_id, memory_type, content, summary, tags, status,
                    created_by, metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values["id"], values["project_id"], values["memory_type"],
                    values["content"], values.get("summary"),
                    json.dumps(values.get("tags", []), ensure_ascii=False),
                    values["status"], values.get("created_by"),
                    json.dumps(values.get("metadata", {}), ensure_ascii=False),
                    values["created_at"], values["updated_at"],
                ),
            )
            self.connection.commit()
        memory = self.get(values["id"])
        if memory is None:
            raise RuntimeError("inserted memory could not be reloaded")
        return memory

    def get(self, memory_id: str) -> Memory | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT * FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
        return self._from_row(row) if row else None

    def search(self, fts_query: str, project_id: str, limit: int, memory_type: str | None = None) -> list[Memory]:
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT m.*
                FROM memory_fts
                JOIN memories AS m ON m.id = memory_fts.id
                WHERE memory_fts MATCH ?
                  AND m.project_id = ?
                  AND m.status = 'active'
                  AND (? IS NULL OR m.memory_type = ?)
                ORDER BY bm25(memory_fts), m.updated_at DESC
                LIMIT ?
                """,
                (fts_query, project_id, memory_type, memory_type, limit),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def list_recent(self, project_id: str, limit: int) -> list[Memory]:
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT * FROM memories
                WHERE project_id = ? AND status = 'active'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def update(self, memory_id: str, values: dict[str, Any]) -> Memory | None:
        current = self.get(memory_id)
        if current is None:
            return None
        content = values.get("content", current.content)
        summary = values.get("summary", current.summary)
        tags = values.get("tags", current.tags)
        status = values.get("status", current.status)
        metadata = values.get("metadata", current.metadata)
        updated_at = values.get("updated_at", current.updated_at)
        with self._lock:
            self.connection.execute(
                """
                UPDATE memories
                SET content = ?, summary = ?, tags = ?, status = ?,
                    metadata = ?, updated_at = ?
                WHERE id = ?
                """,
                (content, summary, json.dumps(tags, ensure_ascii=False), status,
                 json.dumps(metadata, ensure_ascii=False), updated_at, memory_id),
            )
            self.connection.commit()
        return self.get(memory_id)

    def health(self) -> dict[str, Any]:
        with self._lock:
            self.connection.execute("SELECT 1").fetchone()
            count = self.connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            self.connection.execute("SELECT rowid FROM memory_fts LIMIT 1").fetchone()
        return {"ok": True, "database": str(self.path), "memory_count": int(count),
                "sqlite_version": sqlite3.sqlite_version, "fts5": True}

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Memory:
        return Memory(
            id=row["id"], project_id=row["project_id"], memory_type=row["memory_type"],
            content=row["content"], summary=row["summary"], tags=json.loads(row["tags"]),
            status=row["status"], created_by=row["created_by"], metadata=json.loads(row["metadata"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
