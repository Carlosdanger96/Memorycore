from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .models import Memory
from .policy import MemoryAccessError, RevisionConflictError

LIVE_DUPLICATE_STATUSES = ("pending", "active")

_MIGRATION_3_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_live_fingerprint
ON memories(project_id, memory_type, content_fingerprint)
WHERE content_fingerprint IS NOT NULL AND status IN ('pending', 'active');
"""
_BUSY_TIMEOUT_MS = 5000
_LOCK_RETRY_ATTEMPTS = 40
_LOCK_RETRY_DELAY_SECONDS = 0.25


def normalize_content(content: str) -> str:
    """Stable normalization used for duplicate detection and fingerprints."""
    collapsed = " ".join(content.casefold().split())
    return re.sub(r"[^\w]+", "", collapsed, flags=re.UNICODE)


def content_fingerprint(project_id: str, memory_type: str, content: str) -> str:
    """Stable normalized-content fingerprint scoped by project and memory type."""
    normalized = normalize_content(content)
    if not normalized:
        return ""
    digest = hashlib.sha256()
    digest.update(project_id.strip().casefold().encode("utf-8"))
    digest.update(b"\x1f")
    digest.update(memory_type.strip().casefold().encode("utf-8"))
    digest.update(b"\x1f")
    digest.update(normalized.encode("utf-8"))
    return digest.hexdigest()

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
    revision INTEGER NOT NULL DEFAULT 0,
    content_fingerprint TEXT,
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
"""


class SQLiteDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(self.path, check_same_thread=False, timeout=_BUSY_TIMEOUT_MS / 1000)
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
            (3, "revision_and_duplicate_fingerprint", _MIGRATION_3_SQL),
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
            "revision": "INTEGER NOT NULL DEFAULT 0",
            "content_fingerprint": "TEXT",
        }
        for name, definition in additions.items():
            if name not in existing:
                self.connection.execute(f"ALTER TABLE memories ADD COLUMN {name} {definition}")
        if "content_fingerprint" in existing:
            return
        self.connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_live_fingerprint
            ON memories(project_id, memory_type, content_fingerprint)
            WHERE content_fingerprint IS NOT NULL AND status IN ('pending', 'active')
            """
        )
        self.connection.commit()
        self.recompute_fingerprints()

    def recompute_fingerprints(self) -> int:
        """Backfill fingerprints for existing rows; returns updated row count."""
        updated = 0
        rows = self.connection.execute(
            "SELECT id, project_id, memory_type, content FROM memories"
        ).fetchall()
        for row in rows:
            fingerprint = content_fingerprint(row["project_id"], row["memory_type"], row["content"])
            if not fingerprint:
                continue
            self._execute_with_retry(
                "UPDATE memories SET content_fingerprint = ? WHERE id = ? AND content_fingerprint IS NULL",
                (fingerprint, row["id"]),
            )
            updated += 1
        self.connection.commit()
        return updated

    def _execute_with_retry(self, sql: str, parameters: tuple = ()) -> sqlite3.Cursor:
        """Run one statement with explicit retry on transient lock contention."""
        last_error: Exception | None = None
        for _ in range(_LOCK_RETRY_ATTEMPTS):
            try:
                return self.connection.execute(sql, parameters)
            except sqlite3.OperationalError as error:
                if "locked" not in str(error).lower() and "busy" not in str(error).lower():
                    raise
                last_error = error
                time.sleep(_LOCK_RETRY_DELAY_SECONDS)
        raise MemoryAccessError(f"database remained locked after {_LOCK_RETRY_ATTEMPTS} retries: {last_error}")

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def add(self, values: dict[str, Any], audit_event: dict[str, Any] | None = None) -> Memory:
        """Insert a memory and its audit event in one transaction.

        The database-level unique partial index enforces duplicate protection:
        concurrent processes that pass an application pre-check still cannot
        both insert the same live fingerprint.
        """
        fingerprint = content_fingerprint(values["project_id"], values["memory_type"], values["content"])
        with self._lock:
            self._begin_immediate()
            try:
                self.connection.execute(
                    """
                    INSERT INTO memories (
                        id, project_id, memory_type, content, summary, tags, status,
                        created_by, updated_by, client_id, model_provider, model_name,
                        session_id, source_type, source_uri, source_id, confidence,
                        metadata, revision, content_fingerprint, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        int(values.get("revision", 0)), fingerprint or None,
                        values["created_at"], values["updated_at"],
                    ),
                )
                if audit_event:
                    self._insert_event(audit_event)
                self.connection.commit()
            except BaseException:
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

    def _begin_immediate(self) -> None:
        """BEGIN IMMEDIATE with explicit retry on transient lock contention."""
        last_error: Exception | None = None
        for _ in range(_LOCK_RETRY_ATTEMPTS):
            try:
                self.connection.execute("BEGIN IMMEDIATE")
                return
            except sqlite3.OperationalError as error:
                if "locked" not in str(error).lower() and "busy" not in str(error).lower():
                    raise
                last_error = error
                time.sleep(_LOCK_RETRY_DELAY_SECONDS)
        raise MemoryAccessError(f"database remained locked after {_LOCK_RETRY_ATTEMPTS} retries: {last_error}")

    def find_live_by_fingerprint(self, project_id: str, memory_type: str, content: str) -> Memory | None:
        fingerprint = content_fingerprint(project_id, memory_type, content)
        if not fingerprint:
            return None
        with self._lock:
            row = self.connection.execute(
                """SELECT * FROM memories
                   WHERE project_id = ? AND memory_type = ? AND content_fingerprint = ?
                     AND status IN ('pending', 'active')
                   ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, updated_at DESC
                   LIMIT 1""",
                (project_id, memory_type, fingerprint),
            ).fetchone()
        return self._from_row(row) if row else None

    def update(self, memory_id: str, values: dict[str, Any],
               audit_event: dict[str, Any] | None = None,
               expected_revision: int | None = None) -> Memory | None:
        """Update a memory with optional compare-and-swap revision checking.

        When ``expected_revision`` is given, the update only succeeds if the
        stored revision still matches. Competing updates that lost the race
        raise RevisionConflictError instead of silently overwriting each other.
        """
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
        new_revision = int(getattr(current, "revision", 0)) + 1
        fingerprint = content_fingerprint(current.project_id, current.memory_type, content)
        with self._lock:
            self._begin_immediate()
            try:
                if expected_revision is not None:
                    row = self.connection.execute(
                        "SELECT revision FROM memories WHERE id = ?", (memory_id,)
                    ).fetchone()
                    if row is None:
                        raise MemoryAccessError(f"memory disappeared during update: {memory_id}")
                    if int(row["revision"]) != int(expected_revision):
                        raise RevisionConflictError(memory_id, int(row["revision"]), int(expected_revision))
                cursor = self.connection.execute(
                    """
                    UPDATE memories
                    SET content = ?, summary = ?, tags = ?, status = ?,
                        metadata = ?, updated_at = ?, updated_by = ?,
                        revision = ?, content_fingerprint = ?
                    WHERE id = ?
                    """,
                    (content, summary, json.dumps(tags, ensure_ascii=False), status,
                     json.dumps(metadata, ensure_ascii=False), updated_at, updated_by,
                     new_revision, fingerprint or None, memory_id),
                )
                if cursor.rowcount != 1:
                    raise MemoryAccessError(f"memory disappeared during update: {memory_id}")
                if audit_event:
                    self._insert_event(audit_event)
                self.connection.commit()
            except BaseException:
                self.connection.rollback()
                raise
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

    def all_events(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT * FROM memory_events ORDER BY created_at, id"
            ).fetchall()
        return [{**dict(row), "details": json.loads(row["details"])} for row in rows]

    def all_links(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT * FROM memory_links ORDER BY created_at, id"
            ).fetchall()
        return [dict(row) for row in rows]

    def insert_event_row(self, event: dict[str, Any]) -> None:
        """Insert a historical audit event with its original identity and timestamp."""
        with self._lock:
            self._begin_immediate()
            try:
                self._insert_event(event)
                self.connection.commit()
            except BaseException:
                self.connection.rollback()
                raise

    def insert_link_row(self, link: dict[str, Any]) -> None:
        """Insert a historical memory link with its original identity and timestamp."""
        with self._lock:
            self._begin_immediate()
            try:
                self.connection.execute(
                    """INSERT INTO memory_links (
                        id, from_memory_id, to_memory_id, relation_type, created_by, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (link["id"], link["from_memory_id"], link["to_memory_id"],
                     link["relation_type"], link.get("created_by"), link["created_at"]),
                )
                self.connection.commit()
            except BaseException:
                self.connection.rollback()
                raise

    def replace_all_memories(self, memories: list[dict[str, Any]], events: list[dict[str, Any]],
                             links: list[dict[str, Any]]) -> dict[str, int]:
        """Atomically replace the entire store with imported records."""
        with self._lock:
            self._begin_immediate()
            try:
                self.connection.execute("DELETE FROM memory_events")
                self.connection.execute("DELETE FROM memory_links")
                self.connection.execute("DELETE FROM memories")
                for record in memories:
                    self._insert_raw_memory(record)
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
            except BaseException:
                self.connection.rollback()
                raise
        return {"memories": len(memories), "events": len(events), "links": len(links)}

    def _insert_raw_memory(self, record: dict[str, Any]) -> None:
        fingerprint = record.get("content_fingerprint") or content_fingerprint(
            record["project_id"], record["memory_type"], record["content"])
        self.connection.execute(
            """
            INSERT INTO memories (
                id, project_id, memory_type, content, summary, tags, status,
                created_by, updated_by, client_id, model_provider, model_name,
                session_id, source_type, source_uri, source_id, confidence,
                metadata, revision, content_fingerprint, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (record["id"], record["project_id"], record["memory_type"], record["content"],
             record.get("summary"), json.dumps(record.get("tags", []), ensure_ascii=False),
             record["status"], record.get("created_by"), record.get("updated_by"),
             record.get("client_id"), record.get("model_provider"), record.get("model_name"),
             record.get("session_id"), record.get("source_type", "manual_import"),
             record.get("source_uri"), record.get("source_id"), record.get("confidence"),
             json.dumps(record.get("metadata", {}), ensure_ascii=False),
             int(record.get("revision", 0)), fingerprint or None,
             record.get("created_at") or record.get("updated_at") or "1970-01-01T00:00:00+00:00",
             record.get("updated_at") or record.get("created_at") or "1970-01-01T00:00:00+00:00"),
        )

    def integrity_check(self) -> dict[str, Any]:
        with self._lock:
            integrity = self.connection.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_key_violations = self.connection.execute("PRAGMA foreign_key_check").fetchall()
            counts = {
                "memories": self.connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0],
                "memory_events": self.connection.execute("SELECT COUNT(*) FROM memory_events").fetchone()[0],
                "memory_links": self.connection.execute("SELECT COUNT(*) FROM memory_links").fetchone()[0],
            }
        return {
            "integrity": integrity,
            "foreign_key_violations": len(foreign_key_violations),
            "counts": counts,
        }

    def restore_from(self, source: str | Path) -> None:
        """Replace this database with a backup snapshot, preserving the original file first."""
        source_path = Path(source).expanduser().resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"backup does not exist: {source_path}")
        with self._lock:
            self.connection.close()
            shutil.copy2(source_path, self.path)
            self.connection = sqlite3.connect(self.path, check_same_thread=False,
                                              timeout=_BUSY_TIMEOUT_MS / 1000)
            self.connection.row_factory = sqlite3.Row
        self.initialize()

    def list_projects(self) -> list[str]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT DISTINCT project_id FROM memories ORDER BY project_id"
            ).fetchall()
        return [row["project_id"] for row in rows]

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
        replacement_fingerprint = content_fingerprint(replacement["project_id"], replacement["memory_type"], replacement["content"])
        with self._lock:
            try:
                self._begin_immediate()
                self.connection.execute("""INSERT INTO memories (id, project_id, memory_type, content, summary, tags, status, created_by, updated_by, client_id, model_provider, model_name, session_id, source_type, source_uri, source_id, confidence, metadata, revision, content_fingerprint, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (replacement["id"], replacement["project_id"], replacement["memory_type"], replacement["content"], replacement.get("summary"), json.dumps(replacement.get("tags", [])), replacement["status"], replacement.get("created_by"), replacement.get("updated_by"), replacement.get("client_id"), replacement.get("model_provider"), replacement.get("model_name"), replacement.get("session_id"), replacement["source_type"], replacement.get("source_uri"), replacement.get("source_id"), replacement.get("confidence"), json.dumps(replacement.get("metadata", {})), 0, replacement_fingerprint or None, replacement["created_at"], replacement["updated_at"]))
                self.connection.execute("UPDATE memories SET status=?, updated_by=?, updated_at=?, revision=revision+1 WHERE id=?", (original_status, replacement.get("created_by"), replacement["updated_at"], original.id))
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
            revision=int(row["revision"]) if "revision" in row.keys() else 0,
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
