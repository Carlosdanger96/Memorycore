from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .models import Memory

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = NORMAL;

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

CREATE INDEX IF NOT EXISTS idx_memories_project_status_type
ON memories(project_id, status, memory_type);

CREATE INDEX IF NOT EXISTS idx_memories_created_at
ON memories(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_memories_updated_at
ON memories(updated_at DESC);

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


class MemorycoreError(Exception):
    """Base exception for Memorycore errors."""
    pass


class DatabaseError(MemorycoreError):
    """Database-related errors."""
    pass


class MemoryNotFoundError(MemorycoreError):
    """Raised when a memory is not found."""
    pass


class SQLiteDatabase:
    """
    Thread-safe SQLite database wrapper for Memorycore.
    
    Provides CRUD operations for memories with FTS5 full-text search.
    Uses WAL mode for better concurrency and read performance.
    """

    def __init__(self, path: str | Path) -> None:
        """
        Initialize the database connection.
        
        Args:
            path: Path to the SQLite database file
            
        Raises:
            DatabaseError: If database cannot be opened
        """
        try:
            self.path = Path(path).expanduser().resolve()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._lock = threading.RLock()
            self.connection = sqlite3.connect(
                self.path, 
                check_same_thread=False,
                isolation_level=None  # Enable autocommit for WAL mode
            )
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA journal_mode = WAL")
            logger.info("Database opened: %s", self.path)
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to open database: {e}") from e

    def initialize(self) -> None:
        """
        Initialize the database schema.
        
        Creates tables, indexes, and triggers if they don't exist.
        Thread-safe operation.
        """
        with self._lock:
            try:
                self.connection.executescript(SCHEMA_SQL)
                self.connection.commit()
                logger.info("Database schema initialized")
            except sqlite3.Error as e:
                raise DatabaseError(f"Failed to initialize schema: {e}") from e

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            try:
                self.connection.close()
                logger.info("Database closed")
            except sqlite3.Error as e:
                logger.error("Error closing database: %s", e)

    def add(self, values: dict[str, Any]) -> Memory:
        """
        Add a new memory to the database.
        
        Args:
            values: Dictionary containing memory data
            
        Returns:
            Memory: The created memory object
            
        Raises:
            DatabaseError: If insertion fails
        """
        with self._lock:
            try:
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
                logger.debug("Memory added: %s", values["id"])
            except sqlite3.Error as e:
                raise DatabaseError(f"Failed to add memory: {e}") from e
        
        memory = self.get(values["id"])
        if memory is None:
            raise DatabaseError("Inserted memory could not be reloaded")
        return memory

    def get(self, memory_id: str) -> Memory | None:
        """
        Retrieve a memory by its ID.
        
        Args:
            memory_id: The unique identifier of the memory
            
        Returns:
            Memory or None: The memory object if found, None otherwise
        """
        with self._lock:
            try:
                row = self.connection.execute(
                    "SELECT * FROM memories WHERE id = ?", (memory_id,)
                ).fetchone()
                return self._from_row(row) if row else None
            except sqlite3.Error as e:
                logger.error("Error retrieving memory %s: %s", memory_id, e)
                return None

    def search(self, fts_query: str, project_id: str, limit: int, 
               memory_type: str | None = None) -> list[Memory]:
        """
        Search memories using FTS5 full-text search.
        
        Args:
            fts_query: FTS5 query string
            project_id: Project scope filter
            limit: Maximum number of results
            memory_type: Optional memory type filter
            
        Returns:
            list[Memory]: List of matching memories
        """
        with self._lock:
            try:
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
            except sqlite3.Error as e:
                logger.error("Search error: %s", e)
                return []

    def list_recent(self, project_id: str, limit: int) -> list[Memory]:
        """
        List recently updated memories for a project.
        
        Args:
            project_id: Project scope filter
            limit: Maximum number of results
            
        Returns:
            list[Memory]: List of recent memories
        """
        with self._lock:
            try:
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
            except sqlite3.Error as e:
                logger.error("Error listing recent memories: %s", e)
                return []

    def update(self, memory_id: str, values: dict[str, Any]) -> Memory | None:
        """
        Update an existing memory.
        
        Args:
            memory_id: The unique identifier of the memory to update
            values: Dictionary containing fields to update
            
        Returns:
            Memory or None: The updated memory object if found, None otherwise
        """
        current = self.get(memory_id)
        if current is None:
            logger.warning("Memory not found for update: %s", memory_id)
            return None
        
        content = values.get("content", current.content)
        summary = values.get("summary", current.summary)
        tags = values.get("tags", current.tags)
        status = values.get("status", current.status)
        metadata = values.get("metadata", current.metadata)
        updated_at = values.get("updated_at", current.updated_at)
        
        with self._lock:
            try:
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
                logger.debug("Memory updated: %s", memory_id)
            except sqlite3.Error as e:
                logger.error("Error updating memory %s: %s", memory_id, e)
                return None
        
        return self.get(memory_id)

    def delete(self, memory_id: str) -> bool:
        """
        Delete a memory from the database.
        
        Args:
            memory_id: The unique identifier of the memory to delete
            
        Returns:
            bool: True if memory was deleted, False otherwise
        """
        with self._lock:
            try:
                cursor = self.connection.execute(
                    "DELETE FROM memories WHERE id = ?", (memory_id,)
                )
                self.connection.commit()
                deleted = cursor.rowcount > 0
                if deleted:
                    logger.debug("Memory deleted: %s", memory_id)
                return deleted
            except sqlite3.Error as e:
                logger.error("Error deleting memory %s: %s", memory_id, e)
                return False

    def health(self) -> dict[str, Any]:
        """
        Check database health and return status information.
        
        Returns:
            dict: Health status information
        """
        with self._lock:
            try:
                # Test basic connectivity
                self.connection.execute("SELECT 1").fetchone()
                
                # Get memory count
                count = self.connection.execute(
                    "SELECT COUNT(*) FROM memories"
                ).fetchone()[0]
                
                # Test FTS5 table
                self.connection.execute("SELECT rowid FROM memory_fts LIMIT 1").fetchone()
                
                # Get database file size
                db_size = self.path.stat().st_size if self.path.exists() else 0
                
                return {
                    "ok": True,
                    "database": str(self.path),
                    "memory_count": int(count),
                    "database_size_bytes": db_size,
                    "sqlite_version": sqlite3.sqlite_version,
                    "fts5": True,
                    "wal_mode": True,
                }
            except sqlite3.Error as e:
                logger.error("Health check failed: %s", e)
                return {
                    "ok": False,
                    "database": str(self.path),
                    "error": str(e),
                    "sqlite_version": sqlite3.sqlite_version,
                }

    def get_stats(self, project_id: str | None = None) -> dict[str, Any]:
        """
        Get statistics about memories in the database.
        
        Args:
            project_id: Optional project filter
            
        Returns:
            dict: Statistics about memories
        """
        with self._lock:
            try:
                if project_id:
                    total = self.connection.execute(
                        "SELECT COUNT(*) FROM memories WHERE project_id = ?",
                        (project_id,)
                    ).fetchone()[0]
                    active = self.connection.execute(
                        "SELECT COUNT(*) FROM memories WHERE project_id = ? AND status = 'active'",
                        (project_id,)
                    ).fetchone()[0]
                    archived = self.connection.execute(
                        "SELECT COUNT(*) FROM memories WHERE project_id = ? AND status = 'archived'",
                        (project_id,)
                    ).fetchone()[0]
                else:
                    total = self.connection.execute(
                        "SELECT COUNT(*) FROM memories"
                    ).fetchone()[0]
                    active = self.connection.execute(
                        "SELECT COUNT(*) FROM memories WHERE status = 'active'"
                    ).fetchone()[0]
                    archived = self.connection.execute(
                        "SELECT COUNT(*) FROM memories WHERE status = 'archived'"
                    ).fetchone()[0]
                
                return {
                    "total": int(total),
                    "active": int(active),
                    "archived": int(archived),
                    "project_id": project_id,
                }
            except sqlite3.Error as e:
                logger.error("Stats error: %s", e)
                return {"error": str(e)}

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Memory:
        """
        Convert a database row to a Memory object.
        
        Args:
            row: SQLite row object
            
        Returns:
            Memory: Memory object populated from row data
        """
        return Memory(
            id=row["id"],
            project_id=row["project_id"],
            memory_type=row["memory_type"],
            content=row["content"],
            summary=row["summary"],
            tags=json.loads(row["tags"]),
            status=row["status"],
            created_by=row["created_by"],
            metadata=json.loads(row["metadata"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
