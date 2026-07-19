from __future__ import annotations

import json
import sqlite3
import threading
import hashlib
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

CREATE TABLE IF NOT EXISTS omni_records (
    record_id TEXT PRIMARY KEY,
    record_type TEXT NOT NULL CHECK (
        record_type IN ('behavior','trajectory','correction','audit_finding')
    ),
    project_id TEXT NOT NULL,
    status TEXT NOT NULL,
    repository TEXT,
    source_revision TEXT,
    task_type TEXT,
    error_signature TEXT,
    behavior_ids TEXT NOT NULL DEFAULT '[]',
    confidence REAL,
    record_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_omni_records_lookup
ON omni_records(record_type, project_id, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_omni_records_correction_match
ON omni_records(record_type, project_id, repository, task_type, error_signature);

CREATE TABLE IF NOT EXISTS omni_trajectory_events (
    event_id TEXT PRIMARY KEY,
    trajectory_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    request_id TEXT,
    event_type TEXT NOT NULL,
    event_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(trajectory_id, sequence),
    UNIQUE(trajectory_id, request_id)
);

CREATE INDEX IF NOT EXISTS idx_omni_events_trajectory
ON omni_trajectory_events(trajectory_id, sequence);

CREATE TABLE IF NOT EXISTS omni_revision_events (
    event_id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    reviewer TEXT,
    details TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_omni_revision_finding
ON omni_revision_events(finding_id, created_at);
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
        migrations = [
            (1, "initial_storage", "embedded-v1"),
            (2, "active_retrieval_index", "CREATE INDEX IF NOT EXISTS idx_memories_active_project_updated ON memories(project_id, updated_at DESC) WHERE status = 'active';"),
            (3, "omni_memory_harness", """
                CREATE TABLE IF NOT EXISTS omni_records (
                    record_id TEXT PRIMARY KEY,
                    record_type TEXT NOT NULL CHECK (record_type IN ('behavior','trajectory','correction','audit_finding')),
                    project_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    repository TEXT,
                    source_revision TEXT,
                    task_type TEXT,
                    error_signature TEXT,
                    behavior_ids TEXT NOT NULL DEFAULT '[]',
                    confidence REAL,
                    record_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_omni_records_lookup
                ON omni_records(record_type, project_id, status, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_omni_records_correction_match
                ON omni_records(record_type, project_id, repository, task_type, error_signature);
                CREATE TABLE IF NOT EXISTS omni_trajectory_events (
                    event_id TEXT PRIMARY KEY,
                    trajectory_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL CHECK (sequence >= 1),
                    request_id TEXT,
                    event_type TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(trajectory_id, sequence),
                    UNIQUE(trajectory_id, request_id)
                );
                CREATE INDEX IF NOT EXISTS idx_omni_events_trajectory
                ON omni_trajectory_events(trajectory_id, sequence);
                CREATE TABLE IF NOT EXISTS omni_revision_events (
                    event_id TEXT PRIMARY KEY,
                    finding_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    reviewer TEXT,
                    details TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_omni_revision_finding
                ON omni_revision_events(finding_id, created_at);
            """),
        ]
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
            DROP TABLE IF EXISTS memory_events;
            DROP TABLE IF EXISTS memory_links;
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

    def add(self, values: dict[str, Any], audit_event: dict[str, Any] | None = None) -> Memory:
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
            if audit_event:
                self._insert_event(audit_event)
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
        return self.get(memory_id)

    def list_events(self, memory_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT * FROM memory_events WHERE memory_id = ? ORDER BY created_at ASC LIMIT ?",
                (memory_id, limit),
            ).fetchall()
        return [{**dict(row), "details": json.loads(row["details"])} for row in rows]

    def all_memories(self) -> list[Memory]:
        with self._lock:
            rows = self.connection.execute("SELECT * FROM memories ORDER BY created_at, id").fetchall()
        return [self._from_row(row) for row in rows]

    def put_omni_record(self, record_type: str, record_id: str, record: dict[str, Any],
                        *, project_id: str, status: str, repository: str | None = None,
                        source_revision: str | None = None, task_type: str | None = None,
                        error_signature: str | None = None,
                        behavior_ids: list[str] | None = None,
                        confidence: float | None = None) -> dict[str, Any]:
        created_at = str(record.get("created_at") or record.get("started_at") or record.get("timestamp"))
        updated_at = str(record.get("updated_at") or record.get("completed_at") or created_at)
        payload = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with self._lock:
            self.connection.execute(
                """INSERT INTO omni_records (
                    record_id, record_type, project_id, status, repository,
                    source_revision, task_type, error_signature, behavior_ids,
                    confidence, record_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(record_id) DO UPDATE SET
                    status=excluded.status, repository=excluded.repository,
                    source_revision=excluded.source_revision, task_type=excluded.task_type,
                    error_signature=excluded.error_signature,
                    behavior_ids=excluded.behavior_ids, confidence=excluded.confidence,
                    record_json=excluded.record_json, updated_at=excluded.updated_at""",
                (record_id, record_type, project_id, status, repository,
                 source_revision, task_type, error_signature,
                 json.dumps(behavior_ids or [], ensure_ascii=False), confidence,
                 payload, created_at, updated_at),
            )
            self.connection.commit()
        return record

    def get_omni_record(self, record_id: str, record_type: str | None = None) -> dict[str, Any] | None:
        query = "SELECT record_json FROM omni_records WHERE record_id = ?"
        parameters: tuple[Any, ...] = (record_id,)
        if record_type is not None:
            query += " AND record_type = ?"
            parameters = (record_id, record_type)
        with self._lock:
            row = self.connection.execute(query, parameters).fetchone()
        return json.loads(row["record_json"]) if row else None

    def list_omni_records(self, record_type: str, project_id: str,
                          *, status: str | None = None,
                          repository: str | None = None,
                          limit: int = 100) -> list[dict[str, Any]]:
        clauses = ["record_type = ?", "project_id = ?"]
        parameters: list[Any] = [record_type, project_id]
        if status is not None:
            clauses.append("status = ?")
            parameters.append(status)
        if repository is not None:
            clauses.append("repository = ?")
            parameters.append(repository)
        parameters.append(limit)
        with self._lock:
            rows = self.connection.execute(
                f"SELECT record_json FROM omni_records WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT ?",
                parameters,
            ).fetchall()
        return [json.loads(row["record_json"]) for row in rows]

    def count_omni_records(self, record_type: str) -> int:
        with self._lock:
            row = self.connection.execute(
                "SELECT COUNT(*) AS count FROM omni_records WHERE record_type=?",
                (record_type,),
            ).fetchone()
        return int(row["count"])

    def append_omni_event(self, event: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        with self._lock:
            if event.get("request_id"):
                row = self.connection.execute(
                    "SELECT event_json FROM omni_trajectory_events WHERE trajectory_id=? AND request_id=?",
                    (event["trajectory_id"], event["request_id"]),
                ).fetchone()
                if row:
                    return json.loads(row["event_json"]), False
            self.connection.execute(
                """INSERT INTO omni_trajectory_events (
                    event_id, trajectory_id, sequence, request_id, event_type,
                    event_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (event["event_id"], event["trajectory_id"], event["sequence"],
                 event.get("request_id"), event["event_type"],
                 json.dumps(event, ensure_ascii=False, sort_keys=True), event["timestamp"]),
            )
            self.connection.commit()
        return event, True

    def list_omni_events(self, trajectory_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT event_json FROM omni_trajectory_events WHERE trajectory_id=? ORDER BY sequence",
                (trajectory_id,),
            ).fetchall()
        return [json.loads(row["event_json"]) for row in rows]

    def add_omni_revision_event(self, event: dict[str, Any]) -> None:
        with self._lock:
            self.connection.execute(
                """INSERT INTO omni_revision_events (
                    event_id, finding_id, event_type, reviewer, details, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (event["event_id"], event["finding_id"], event["event_type"],
                 event.get("reviewer"), json.dumps(event.get("details", {}), ensure_ascii=False),
                 event["created_at"]),
            )
            self.connection.commit()

    def list_omni_revision_events(self, finding_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT * FROM omni_revision_events WHERE finding_id=? ORDER BY created_at",
                (finding_id,),
            ).fetchall()
        return [{**dict(row), "details": json.loads(row["details"])} for row in rows]

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
