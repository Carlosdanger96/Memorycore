from __future__ import annotations

import json
import sqlite3
import threading
import hashlib
import re
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

-- Covering index for list_recent (project + status filter, recency order).
CREATE INDEX IF NOT EXISTS idx_memories_project_status_updated
ON memories(project_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_events (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL REFERENCES memories(id),
    project_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    client_id TEXT,
    previous_state TEXT,
    new_state TEXT,
    details TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memory_events_memory_created
ON memory_events(memory_id, created_at DESC);

CREATE TABLE IF NOT EXISTS memory_links (
    id TEXT PRIMARY KEY,
    from_memory_id TEXT NOT NULL REFERENCES memories(id),
    to_memory_id TEXT NOT NULL REFERENCES memories(id),
    relation_type TEXT NOT NULL CHECK (relation_type IN ('supersedes','corrects','contradicts')),
    created_by TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(from_memory_id, to_memory_id, relation_type)
);

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
            self._apply_migrations()
            self.connection.commit()

    def _apply_migrations(self) -> None:
        migrations = [(1, "initial_storage", "embedded-v1"), (2, "active_retrieval_index", "CREATE INDEX IF NOT EXISTS idx_memories_active_project_updated ON memories(project_id, updated_at DESC) WHERE status = 'active';"), (3, "list_recent_covering_index", "CREATE INDEX IF NOT EXISTS idx_memories_project_status_updated ON memories(project_id, status, updated_at DESC);")]
        applied = {row[0]: row[1] for row in self.connection.execute("SELECT version, checksum FROM schema_migrations")}
        for version, name, sql in migrations:
            checksum = sql if version == 1 else hashlib.sha256(sql.encode()).hexdigest()
            if version in applied:
                if applied[version] != checksum:
                    raise RuntimeError(f"migration checksum mismatch for version {version}")
                continue
            if version == 1:
                self.connection.execute("INSERT INTO schema_migrations(version, name, checksum, applied_at) VALUES (?, ?, ?, datetime('now'))", (version, name, checksum))
                continue
            self.connection.executescript("BEGIN IMMEDIATE; " + sql + " INSERT INTO schema_migrations(version, name, checksum, applied_at) VALUES (" + str(version) + ", '" + name + "', '" + checksum + "', datetime('now')); COMMIT;")

    def _upgrade_status_constraint(self) -> None:
        """Rebuild the v0.1 table when its CHECK constraint lacks new statuses OR types.

        SQLite cannot alter a CHECK constraint in place. This keeps databases
        created before pending/rejected/contradicted (and the observation
        memory_type) existed usable without a manual export/import step.
        """
        sql = self.connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'memories'"
        ).fetchone()[0]
        needs_rebuild = "'pending'" not in sql or "'observation'" not in sql
        if not needs_rebuild:
            return
        try:
            self.connection.executescript("""
            BEGIN IMMEDIATE;
            DROP TRIGGER IF EXISTS memories_ai;
            DROP TRIGGER IF EXISTS memories_ad;
            DROP TRIGGER IF EXISTS memories_au;
            DROP INDEX IF EXISTS idx_memories_project_status;
            DROP INDEX IF EXISTS idx_memories_project_type;
            DROP TABLE IF EXISTS memory_events;
            DROP TABLE IF EXISTS memory_links;
            ALTER TABLE memories RENAME TO memories_legacy;
            CREATE TABLE memories (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                memory_type TEXT NOT NULL CHECK (
                    memory_type IN ('fact','decision','preference','procedure','correction','observation','note')
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
            CREATE INDEX IF NOT EXISTS idx_memories_project_status_updated
            ON memories(project_id, status, updated_at DESC);
            CREATE TABLE memory_events (
                id TEXT PRIMARY KEY,
                memory_id TEXT NOT NULL REFERENCES memories(id),
                project_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                client_id TEXT,
                previous_state TEXT,
                new_state TEXT,
                details TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX idx_memory_events_memory_created
            ON memory_events(memory_id, created_at DESC);
            CREATE TABLE memory_links (
                id TEXT PRIMARY KEY,
                from_memory_id TEXT NOT NULL REFERENCES memories(id),
                to_memory_id TEXT NOT NULL REFERENCES memories(id),
                relation_type TEXT NOT NULL CHECK (relation_type IN ('supersedes','corrects','contradicts')),
                created_by TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(from_memory_id, to_memory_id, relation_type)
            );
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

    def add_link(self, *, from_memory_id: str, to_memory_id: str,
                 relation_type: str, created_by: str | None, created_at: str) -> None:
        """Insert a supersedes/corrects/contradicts link. Idempotent: the UNIQUE
        constraint on (from, to, relation_type) makes a replay a no-op."""
        with self._lock:
            self.connection.execute(
                """INSERT OR IGNORE INTO memory_links
                   (id, from_memory_id, to_memory_id, relation_type, created_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (str(__import__("uuid").uuid4()), from_memory_id, to_memory_id,
                 relation_type, created_by, created_at),
            )
            self.connection.commit()

    def list_links(self, memory_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.connection.execute(
                """SELECT * FROM memory_links
                   WHERE from_memory_id = ? OR to_memory_id = ?
                   ORDER BY created_at ASC""",
                (memory_id, memory_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def add(self, values: dict[str, Any], audit_event: dict[str, Any] | None = None) -> Memory:
        with self._lock:
            try:
                self.connection.execute("BEGIN IMMEDIATE")
                if values["status"] == "active":
                    self._reject_duplicate(values["project_id"], values["content"])
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
                if audit_event:
                    self._insert_event(audit_event)
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise
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
                ORDER BY bm25(memory_fts, 1.0, 3.0, 2.0), m.updated_at DESC
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

    def update(self, memory_id: str, values: dict[str, Any],
               audit_event: dict[str, Any] | None = None) -> Memory | None:
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
            try:
                self.connection.execute("BEGIN IMMEDIATE")
                if status == "active" and (current.status != "active" or content != current.content):
                    self._reject_duplicate(current.project_id, content, exclude_id=memory_id)
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
                if audit_event:
                    self._insert_event(audit_event)
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise
        return self.get(memory_id)

    @staticmethod
    def _normalized_content(content: str) -> str:
        return " ".join(content.casefold().split())

    def duplicate_candidates(self, project_id: str, content: str,
                             exclude_id: str | None = None) -> list[dict[str, Any]]:
        """Deterministic same-project exact and high-overlap candidates."""
        normalized = self._normalized_content(content)
        tokens = set(re.findall(r"\w+", normalized))
        with self._lock:
            rows = self.connection.execute(
                """SELECT id, content FROM memories
                   WHERE project_id = ? AND status = 'active' AND id != ?""",
                (project_id, exclude_id or ""),
            ).fetchall()
        matches = []
        for row in rows:
            candidate = self._normalized_content(row["content"])
            if candidate == normalized:
                matches.append({"memory_id": row["id"], "reason": "exact", "score": 1.0})
                continue
            other = set(re.findall(r"\w+", candidate))
            if min(len(tokens), len(other)) < 4:
                continue
            overlap = len(tokens & other) / len(tokens | other)
            if overlap >= 0.8:
                matches.append({"memory_id": row["id"], "reason": "probable",
                                "score": round(overlap, 4)})
        return sorted(matches, key=lambda item: (-item["score"], item["memory_id"]))

    def _reject_duplicate(self, project_id: str, content: str,
                          exclude_id: str | None = None) -> None:
        matches = self.duplicate_candidates(project_id, content, exclude_id)
        if matches:
            first = matches[0]
            raise ValueError(f"{first['reason']} duplicate memory exists: {first['memory_id']}")

    def list_events(self, memory_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            # Order by rowid (insertion order), not id: event ids are random
            # UUIDs, so a same-timestamp tie-break on id is non-deterministic.
            # created_at alone is also insufficient — two events in one
            # transaction share the same microsecond timestamp.
            rows = self.connection.execute(
                "SELECT * FROM memory_events WHERE memory_id = ? ORDER BY rowid ASC LIMIT ?",
                (memory_id, limit),
            ).fetchall()
        return [{**dict(row), "details": json.loads(row["details"])} for row in rows]

    def all_memories(self) -> list[Memory]:
        with self._lock:
            rows = self.connection.execute("SELECT * FROM memories ORDER BY created_at, id").fetchall()
        return [self._from_row(row) for row in rows]

    def snapshot_records(self) -> tuple[list[Memory], list[dict[str, Any]], list[dict[str, Any]]]:
        """Read a consistent snapshot including the full audit and link history."""
        with self._lock:
            self.connection.execute("BEGIN")
            try:
                memories = [self._from_row(row) for row in self.connection.execute(
                    "SELECT * FROM memories ORDER BY rowid"
                )]
                events = [{**dict(row), "details": json.loads(row["details"])}
                          for row in self.connection.execute(
                              "SELECT * FROM memory_events ORDER BY rowid"
                          )]
                links = [dict(row) for row in self.connection.execute(
                    "SELECT * FROM memory_links ORDER BY rowid"
                )]
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise
        return memories, events, links

    def restore_records(self, memories: list[dict[str, Any]],
                        events: list[dict[str, Any]], links: list[dict[str, Any]]) -> int:
        """Restore a complete snapshot into an empty database atomically."""
        with self._lock:
            try:
                self.connection.execute("BEGIN IMMEDIATE")
                for table in ("memories", "memory_events", "memory_links"):
                    if self.connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                        raise ValueError("JSONL restore requires an empty Memorycore database")
                for item in memories:
                    self.connection.execute(
                        """INSERT INTO memories (
                            id, project_id, memory_type, content, summary, tags, status,
                            created_by, updated_by, client_id, model_provider, model_name,
                            session_id, source_type, source_uri, source_id, confidence,
                            metadata, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (item["id"], item["project_id"], item["memory_type"], item["content"],
                         item.get("summary"), json.dumps(item["tags"], ensure_ascii=False),
                         item["status"], item.get("created_by"), item.get("updated_by"),
                         item.get("client_id"), item.get("model_provider"), item.get("model_name"),
                         item.get("session_id"), item["source_type"], item.get("source_uri"),
                         item.get("source_id"), item.get("confidence"),
                         json.dumps(item["metadata"], ensure_ascii=False),
                         item["created_at"], item["updated_at"]),
                    )
                for event in events:
                    self._insert_event(event)
                for link in links:
                    self.connection.execute(
                        """INSERT INTO memory_links (
                            id, from_memory_id, to_memory_id, relation_type, created_by, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?)""",
                        (link["id"], link["from_memory_id"], link["to_memory_id"],
                         link["relation_type"], link.get("created_by"), link["created_at"]),
                    )
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise
        return len(memories)

    def find_exact_active(self, project_id: str, memory_type: str, content: str) -> Memory | None:
        with self._lock:
            row = self.connection.execute("""SELECT * FROM memories
                WHERE project_id=? AND memory_type=? AND status='active'
                AND lower(trim(content))=lower(trim(?)) LIMIT 1""", (project_id, memory_type, content)).fetchone()
        return self._from_row(row) if row else None

    def find_exact_active_any(self, project_id: str, query: str) -> Memory | None:
        with self._lock:
            row = self.connection.execute("""SELECT * FROM memories WHERE project_id=? AND status='active'
                AND (lower(trim(content))=lower(trim(?)) OR lower(trim(COALESCE(summary,'')))=lower(trim(?)))
                ORDER BY updated_at DESC LIMIT 1""", (project_id, query, query)).fetchone()
        return self._from_row(row) if row else None

    def backup_to(self, destination: str | Path) -> None:
        destination_path = Path(destination).expanduser().resolve()
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            target = sqlite3.connect(destination_path)
            try:
                self.connection.backup(target)
            finally:
                target.close()

    def _insert_event(self, event: dict[str, Any]) -> None:
        self.connection.execute(
            """INSERT INTO memory_events (
                id, memory_id, project_id, event_type, client_id, previous_state,
                new_state, details, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event["id"], event["memory_id"], event["project_id"], event["event_type"],
             event.get("client_id"), event.get("previous_state"), event.get("new_state"),
             json.dumps(event.get("details", {}), ensure_ascii=False), event["created_at"]),
        )

    def replace_memory(self, original: Memory, replacement: dict[str, Any], *, relation_type: str,
                       original_status: str, original_event: dict[str, Any],
                       replacement_event: dict[str, Any]) -> Memory:
        """Atomically create a replacement, link it, retire the original, and audit both."""
        with self._lock:
            try:
                self.connection.execute("BEGIN IMMEDIATE")
                self._reject_duplicate(
                    replacement["project_id"], replacement["content"], exclude_id=original.id
                )
                self.connection.execute("""INSERT INTO memories (id, project_id, memory_type, content, summary, tags, status, created_by, updated_by, client_id, model_provider, model_name, session_id, source_type, source_uri, source_id, confidence, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (replacement["id"], replacement["project_id"], replacement["memory_type"], replacement["content"], replacement.get("summary"), json.dumps(replacement.get("tags", [])), replacement["status"], replacement.get("created_by"), replacement.get("updated_by"), replacement.get("client_id"), replacement.get("model_provider"), replacement.get("model_name"), replacement.get("session_id"), replacement["source_type"], replacement.get("source_uri"), replacement.get("source_id"), replacement.get("confidence"), json.dumps(replacement.get("metadata", {})), replacement["created_at"], replacement["updated_at"]))
                self.connection.execute("UPDATE memories SET status=?, updated_by=?, updated_at=? WHERE id=?", (original_status, replacement.get("created_by"), replacement["updated_at"], original.id))
                self.connection.execute("INSERT INTO memory_links(id, from_memory_id, to_memory_id, relation_type, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?)", (str(__import__('uuid').uuid4()), replacement["id"], original.id, relation_type, replacement.get("created_by"), replacement["created_at"]))
                self._insert_event(original_event)
                self._insert_event(replacement_event)
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise
        result = self.get(replacement["id"])
        if result is None:
            raise RuntimeError("replacement memory could not be reloaded")
        return result

    def health(self) -> dict[str, Any]:
        with self._lock:
            self.connection.execute("SELECT 1").fetchone()
            count = self.connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            self.connection.execute("SELECT rowid FROM memory_fts LIMIT 1").fetchone()
        return {"ok": True, "database": str(self.path), "memory_count": int(count),
                "sqlite_version": sqlite3.sqlite_version, "fts5": True}

    def checkpoint(self) -> dict[str, Any]:
        """TRUNCATE checkpoint: fold the WAL back into the main DB file.

        Keeps the -wal file from growing unbounded under sync churn and makes
        plain file-copy backups capture all committed state."""
        with self._lock:
            row = self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        busy, log_frames, checkpointed = (row[0], row[1], row[2]) if row else (None, None, None)
        return {"ok": True, "busy": bool(busy), "log_frames": log_frames,
                "checkpointed_frames": checkpointed}

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
