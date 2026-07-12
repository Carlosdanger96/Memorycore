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
        status IN ('pending','active','rejected','archived','superseded','contradicted')
    ),
    created_by TEXT,
    updated_by TEXT,
    client_id TEXT,
    model_provider TEXT,
    model_name TEXT,
    session_id TEXT,
    source_type TEXT NOT NULL DEFAULT 'manual_import',
    source_uri TEXT,
    source_id TEXT,
    confidence REAL,
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
            self._upgrade_status_constraint()
            self._migrate_memories_table()
            self.connection.commit()

    def _upgrade_status_constraint(self) -> None:
        """Rebuild the v0.1 table when its CHECK constraint lacks new statuses.

        SQLite cannot alter a CHECK constraint in place. This keeps databases
        created before pending/rejected/contradicted existed usable without a
        manual export/import step.
        """
        sql = self.connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'memories'"
        ).fetchone()[0]
        if "'pending'" in sql:
            return
        try:
            self.connection.executescript("""
            BEGIN IMMEDIATE;
            DROP TRIGGER IF EXISTS memories_ai;
            DROP TRIGGER IF EXISTS memories_ad;
            DROP TRIGGER IF EXISTS memories_au;
            DROP INDEX IF EXISTS idx_memories_project_status;
            DROP INDEX IF EXISTS idx_memories_project_type;
            ALTER TABLE memories RENAME TO memories_legacy;
            CREATE TABLE memories (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                memory_type TEXT NOT NULL CHECK (
                    memory_type IN ('fact','decision','preference','procedure','correction','note')
                ),
                content TEXT NOT NULL,
                summary TEXT,
                tags TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'active' CHECK (
                    status IN ('pending','active','rejected','archived','superseded','contradicted')
                ),
                created_by TEXT,
                updated_by TEXT,
                client_id TEXT,
                model_provider TEXT,
                model_name TEXT,
                session_id TEXT,
                source_type TEXT NOT NULL DEFAULT 'manual_import',
                source_uri TEXT,
                source_id TEXT,
                confidence REAL,
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO memories (
                id, project_id, memory_type, content, summary, tags, status,
                created_by, updated_by, metadata, created_at, updated_at
            ) SELECT
                id, project_id, memory_type, content, summary, tags, status,
                created_by, created_by, metadata, created_at, updated_at
            FROM memories_legacy;
            DROP TABLE memories_legacy;
            CREATE INDEX IF NOT EXISTS idx_memories_project_status
            ON memories(project_id, status);
            CREATE INDEX IF NOT EXISTS idx_memories_project_type
            ON memories(project_id, memory_type);
            DELETE FROM memory_fts;
            INSERT INTO memory_fts(id, content, summary, tags)
            SELECT id, content, COALESCE(summary, ''), tags FROM memories;
            CREATE TRIGGER memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memory_fts(id, content, summary, tags)
                VALUES (new.id, new.content, COALESCE(new.summary, ''), new.tags);
            END;
            CREATE TRIGGER memories_ad AFTER DELETE ON memories BEGIN
                DELETE FROM memory_fts WHERE id = old.id;
            END;
            CREATE TRIGGER memories_au AFTER UPDATE ON memories BEGIN
                DELETE FROM memory_fts WHERE id = old.id;
                INSERT INTO memory_fts(id, content, summary, tags)
                VALUES (new.id, new.content, COALESCE(new.summary, ''), new.tags);
            END;
            COMMIT;
        """)
        except Exception:
            self.connection.rollback()
            raise

    def _migrate_memories_table(self) -> None:
        """Add provenance columns to databases created by pre-0.2 Memorycore."""
        existing = {
            row["name"] for row in self.connection.execute("PRAGMA table_info(memories)")
        }
        additions = {
            "updated_by": "TEXT",
            "client_id": "TEXT",
            "model_provider": "TEXT",
            "model_name": "TEXT",
            "session_id": "TEXT",
            "source_type": "TEXT NOT NULL DEFAULT 'manual_import'",
            "source_uri": "TEXT",
            "source_id": "TEXT",
            "confidence": "REAL",
        }
        for name, definition in additions.items():
            if name not in existing:
                self.connection.execute(f"ALTER TABLE memories ADD COLUMN {name} {definition}")

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def add(self, values: dict[str, Any]) -> Memory:
        with self._lock:
            self.connection.execute(
                """
                INSERT INTO memories (
                    id, project_id, memory_type, content, summary, tags, status,
                    created_by, updated_by, client_id, model_provider, model_name,
                    session_id, source_type, source_uri, source_id, confidence,
                    metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values["id"], values["project_id"], values["memory_type"],
                    values["content"], values.get("summary"),
                    json.dumps(values.get("tags", []), ensure_ascii=False),
                    values["status"], values.get("created_by"),
                    values.get("updated_by"), values.get("client_id"),
                    values.get("model_provider"), values.get("model_name"),
                    values.get("session_id"), values["source_type"],
                    values.get("source_uri"), values.get("source_id"),
                    values.get("confidence"),
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

    def search(self, fts_query: str, project_id: str, limit: int,
               memory_type: str | None = None, status: str = "active") -> list[Memory]:
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT m.*
                FROM memory_fts
                JOIN memories AS m ON m.id = memory_fts.id
                WHERE memory_fts MATCH ?
                  AND m.project_id = ?
                  AND m.status = ?
                  AND (? IS NULL OR m.memory_type = ?)
                ORDER BY bm25(memory_fts), m.updated_at DESC
                LIMIT ?
                """,
                (fts_query, project_id, status, memory_type, memory_type, limit),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def list_recent(self, project_id: str, limit: int, status: str = "active") -> list[Memory]:
        with self._lock:
            rows = self.connection.execute(
                """
                SELECT * FROM memories
                WHERE project_id = ? AND status = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (project_id, status, limit),
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
        updated_by = values.get("updated_by", current.updated_by)
        with self._lock:
            self.connection.execute(
                """
                UPDATE memories
                SET content = ?, summary = ?, tags = ?, status = ?,
                    metadata = ?, updated_at = ?, updated_by = ?
                WHERE id = ?
                """,
                (content, summary, json.dumps(tags, ensure_ascii=False), status,
                 json.dumps(metadata, ensure_ascii=False), updated_at, updated_by, memory_id),
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
            updated_by=row["updated_by"], client_id=row["client_id"],
            model_provider=row["model_provider"], model_name=row["model_name"],
            session_id=row["session_id"], source_type=row["source_type"],
            source_uri=row["source_uri"], source_id=row["source_id"],
            confidence=row["confidence"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
