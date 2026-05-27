"""SQLite Storage Implementation for Memory Core.

Provides durable storage for memory records with SQLite backend.
Implements the memory schema: memory_id, project_id, content, source_refs,
created_at, created_by, tags, confidence, status.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import logging

logger = logging.getLogger(__name__)


# Memory status enum
class MemoryStatus:
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    ARCHIVED = "archived"


@dataclass
class MemoryRecord:
    """Represents a memory record from storage."""
    memory_id: str
    project_id: str
    content: str
    source_refs: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_by: str = ""
    tags: List[str] = field(default_factory=list)
    confidence: float = 0.0
    status: str = MemoryStatus.CANDIDATE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "project_id": self.project_id,
            "content": self.content,
            "source_refs": self.source_refs,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "tags": self.tags,
            "confidence": self.confidence,
            "status": self.status,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "MemoryRecord":
        """Create MemoryRecord from SQLite row."""
        return cls(
            memory_id=row["memory_id"],
            project_id=row["project_id"],
            content=row["content"],
            source_refs=json.loads(row["source_refs"] or "[]"),
            created_at=row["created_at"],
            created_by=row["created_by"],
            tags=json.loads(row["tags"] or "[]"),
            confidence=row["confidence"] or 0.0,
            status=row["status"] or MemoryStatus.CANDIDATE,
        )


@dataclass
class AuditRecord:
    """Represents an audit log entry."""
    audit_id: int
    timestamp: str
    action: str
    entity_type: str
    entity_id: str
    project_id: Optional[str]
    user_id: str
    details: Dict[str, Any]
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "timestamp": self.timestamp,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "project_id": self.project_id,
            "user_id": self.user_id,
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
        }


class Storage:
    """SQLite storage backend for Memory Core."""

    def __init__(self, db_path: str = "file:memorycore.db"):
        """Initialize storage with database path.
        
        Args:
            db_path: SQLite DSN or file path. Use 'file:memorycore.db' for
                     file-based storage, or ':memory:' for in-memory.
        """
        self.db_path = db_path
        self._connection: Optional[sqlite3.Connection] = None
        self._initialize_database()

    def _initialize_database(self) -> None:
        """Initialize database schema."""
        schema_path = Path(__file__).parent.parent / "db" / "schema.sql"
        if not schema_path.exists():
            # Fallback to repo root
            schema_path = Path(__file__).parent.parent.parent / "db" / "schema.sql"
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Enable WAL mode and foreign keys
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            
            # Execute schema
            if schema_path.exists():
                with open(schema_path, "r") as f:
                    schema_sql = f.read()
                cursor.executescript(schema_sql)
            else:
                # Fallback inline schema
                cursor.executescript(self._get_fallback_schema())
            
            conn.commit()

    def _get_fallback_schema(self) -> str:
        """Fallback schema if file not found."""
        return """
        CREATE TABLE IF NOT EXISTS memories (
            memory_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            content TEXT NOT NULL,
            source_refs TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            created_by TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '[]',
            confidence REAL NOT NULL DEFAULT 0.0,
            status TEXT NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate', 'accepted', 'archived'))
        );
        
        CREATE INDEX IF NOT EXISTS idx_memories_project_id ON memories(project_id);
        CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status);
        
        CREATE TABLE IF NOT EXISTS audit_log (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            action TEXT NOT NULL CHECK (action IN ('read', 'write', 'delete', 'update', 'policy_check')),
            entity_type TEXT NOT NULL CHECK (entity_type IN ('memory', 'project', 'config', 'policy')),
            entity_id TEXT NOT NULL,
            project_id TEXT,
            user_id TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '{}',
            ip_address TEXT,
            user_agent TEXT
        );
        
        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            created_by TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT 1
        );
        
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            email TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            is_active BOOLEAN NOT NULL DEFAULT 1
        );
        
        CREATE TABLE IF NOT EXISTS roles (
            role_id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_name TEXT NOT NULL UNIQUE CHECK (role_name IN ('admin', 'writer', 'reader', 'auditor')),
            description TEXT
        );
        
        INSERT OR IGNORE INTO roles (role_name, description) VALUES 
            ('admin', 'Full access to all projects and operations'),
            ('writer', 'Can read and write memories in authorized projects'),
            ('reader', 'Can only read memories in authorized projects'),
            ('auditor', 'Can only read audit logs');
        
        CREATE TABLE IF NOT EXISTS user_project_roles (
            user_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            role_name TEXT NOT NULL CHECK (role_name IN ('admin', 'writer', 'reader', 'auditor')),
            assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
            assigned_by TEXT NOT NULL,
            PRIMARY KEY (user_id, project_id, role_name),
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (project_id) REFERENCES projects(project_id)
        );
        """

    @contextmanager
    def _get_connection(self) -> Any:
        """Context manager for database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA foreign_keys=ON")
        
        try:
            yield self._connection
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            raise

    @contextmanager
    def get_cursor(self) -> Any:
        """Context manager for database cursor."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                yield cursor
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cursor.close()

    # Memory CRUD operations
    
    def create_memory(self, record: MemoryRecord) -> MemoryRecord:
        """Create a new memory record."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO memories (memory_id, project_id, content, source_refs, 
                                     created_at, created_by, tags, confidence, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.memory_id,
                record.project_id,
                record.content,
                json.dumps(record.source_refs),
                record.created_at,
                record.created_by,
                json.dumps(record.tags),
                record.confidence,
                record.status,
            ))
        return record

    def get_memory(self, memory_id: str) -> Optional[MemoryRecord]:
        """Get a memory record by ID."""
        with self.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM memories WHERE memory_id = ?",
                (memory_id,)
            )
            row = cursor.fetchone()
            if row:
                return MemoryRecord.from_row(row)
            return None

    def update_memory(self, memory_id: str, updates: Dict[str, Any]) -> Optional[MemoryRecord]:
        """Update a memory record."""
        existing = self.get_memory(memory_id)
        if not existing:
            return None

        # Build update query
        set_clauses = []
        params = []
        
        if "content" in updates:
            set_clauses.append("content = ?")
            params.append(updates["content"])
        if "source_refs" in updates:
            set_clauses.append("source_refs = ?")
            params.append(json.dumps(updates["source_refs"]))
        if "tags" in updates:
            set_clauses.append("tags = ?")
            params.append(json.dumps(updates["tags"]))
        if "confidence" in updates:
            set_clauses.append("confidence = ?")
            params.append(updates["confidence"])
        if "status" in updates:
            set_clauses.append("status = ?")
            params.append(updates["status"])

        if not set_clauses:
            return existing

        params.append(memory_id)
        query = f"UPDATE memories SET {', '.join(set_clauses)} WHERE memory_id = ?"
        
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
        
        return self.get_memory(memory_id)

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory record."""
        with self.get_cursor() as cursor:
            cursor.execute("DELETE FROM memories WHERE memory_id = ?", (memory_id,))
            return cursor.rowcount > 0

    def search_memories(
        self,
        project_id: Optional[str] = None,
        query: Optional[str] = None,
        status: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[MemoryRecord], int]:
        """Search memory records with filters.
        
        Args:
            project_id: Filter by project ID
            query: Full-text search query
            status: Filter by status (candidate, accepted, archived)
            tags: Filter by tags (AND logic)
            limit: Maximum number of results
            offset: Pagination offset
            
        Returns:
            Tuple of (results, total_count)
        """
        where_clauses = []
        params = []

        if project_id:
            where_clauses.append("project_id = ?")
            params.append(project_id)
        
        if status:
            where_clauses.append("status = ?")
            params.append(status)
        
        if tags:
            # JSON array contains all tags
            for tag in tags:
                where_clauses.append("tags LIKE ?")
                params.append(f"%{tag}%")

        # Count query
        count_where = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        with self.get_cursor() as cursor:
            # Get total count
            cursor.execute(f"SELECT COUNT(*) FROM memories WHERE {count_where}", params)
            total = cursor.fetchone()[0]
            
            # Build search query
            if query:
                # Use FTS if available, otherwise LIKE
                try:
                    fts_query = f"""
                        SELECT m.* FROM memories m
                        JOIN memories_fts f ON m.memory_id = f.memory_id
                        WHERE {count_where} AND (f.content MATCH ? OR f.tags MATCH ?)
                        ORDER BY m.created_at DESC
                        LIMIT ? OFFSET ?
                    """
                    cursor.execute(fts_query, params + [query, query, limit, offset])
                except sqlite3.OperationalError:
                    # Fallback to LIKE search
                    where_clauses.append("(content LIKE ? OR tags LIKE ?)")
                    params.extend([f"%{query}%", f"%{query}%"])
                    search_where = " AND ".join(where_clauses)
                    cursor.execute(
                        f"SELECT * FROM memories WHERE {search_where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                        params + [limit, offset]
                    )
            else:
                search_where = " AND ".join(where_clauses) if where_clauses else "1=1"
                cursor.execute(
                    f"SELECT * FROM memories WHERE {search_where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    params + [limit, offset]
                )
            
            rows = cursor.fetchall()
            results = [MemoryRecord.from_row(row) for row in rows]
        
        return results, total

    def get_memories_by_project(self, project_id: str, limit: int = 100) -> List[MemoryRecord]:
        """Get all memories for a specific project."""
        results, _ = self.search_memories(project_id=project_id, limit=limit)
        return results

    # Audit log operations
    
    def log_audit(
        self,
        action: str,
        entity_type: str,
        entity_id: str,
        user_id: str,
        project_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditRecord:
        """Log an audit entry (append-only)."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO audit_log (action, entity_type, entity_id, project_id, 
                                       user_id, details, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                action,
                entity_type,
                entity_id,
                project_id,
                user_id,
                json.dumps(details or {}),
                ip_address,
                user_agent,
            ))
            audit_id = cursor.lastrowid
        
        return AuditRecord(
            audit_id=audit_id,
            timestamp=datetime.utcnow().isoformat(),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            project_id=project_id,
            user_id=user_id,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def get_audit_logs(
        self,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[AuditRecord], int]:
        """Get audit log entries with filters."""
        where_clauses = []
        params = []

        if project_id:
            where_clauses.append("project_id = ?")
            params.append(project_id)
        
        if user_id:
            where_clauses.append("user_id = ?")
            params.append(user_id)
        
        if action:
            where_clauses.append("action = ?")
            params.append(action)

        count_where = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        with self.get_cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM audit_log WHERE {count_where}", params)
            total = cursor.fetchone()[0]
            
            search_where = " AND ".join(where_clauses) if where_clauses else "1=1"
            cursor.execute(
                f"SELECT * FROM audit_log WHERE {search_where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                params + [limit, offset]
            )
            
            rows = cursor.fetchall()
            results = []
            for row in rows:
                results.append(AuditRecord(
                    audit_id=row["audit_id"],
                    timestamp=row["timestamp"],
                    action=row["action"],
                    entity_type=row["entity_type"],
                    entity_id=row["entity_id"],
                    project_id=row["project_id"],
                    user_id=row["user_id"],
                    details=json.loads(row["details"] or "{}"),
                    ip_address=row["ip_address"],
                    user_agent=row["user_agent"],
                ))
        
        return results, total

    # Project operations
    
    def create_project(self, project_id: str, name: str, created_by: str, description: str = "") -> bool:
        """Create a new project."""
        with self.get_cursor() as cursor:
            try:
                cursor.execute("""
                    INSERT INTO projects (project_id, name, description, created_by)
                    VALUES (?, ?, ?, ?)
                """, (project_id, name, description, created_by))
                return True
            except sqlite3.IntegrityError:
                return False

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get project by ID."""
        with self.get_cursor() as cursor:
            cursor.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def project_exists(self, project_id: str) -> bool:
        """Check if project exists."""
        return self.get_project(project_id) is not None

    # User operations
    
    def create_user(self, user_id: str, username: str, email: str = "") -> bool:
        """Create a new user."""
        with self.get_cursor() as cursor:
            try:
                cursor.execute("""
                    INSERT INTO users (user_id, username, email)
                    VALUES (?, ?, ?)
                """, (user_id, username, email))
                return True
            except sqlite3.IntegrityError:
                return False

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        with self.get_cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def user_exists(self, user_id: str) -> bool:
        """Check if user exists."""
        return self.get_user(user_id) is not None

    # Role operations
    
    def grant_role(self, user_id: str, project_id: str, role_name: str, assigned_by: str) -> bool:
        """Grant a role to a user for a project."""
        with self.get_cursor() as cursor:
            try:
                cursor.execute("""
                    INSERT INTO user_project_roles (user_id, project_id, role_name, assigned_by)
                    VALUES (?, ?, ?, ?)
                """, (user_id, project_id, role_name, assigned_by))
                return True
            except sqlite3.IntegrityError:
                return False

    def get_user_roles(self, user_id: str, project_id: Optional[str] = None) -> List[str]:
        """Get roles for a user, optionally filtered by project."""
        with self.get_cursor() as cursor:
            if project_id:
                cursor.execute(
                    "SELECT role_name FROM user_project_roles WHERE user_id = ? AND project_id = ?",
                    (user_id, project_id)
                )
            else:
                cursor.execute(
                    "SELECT role_name FROM user_project_roles WHERE user_id = ?",
                    (user_id,)
                )
            rows = cursor.fetchall()
            return [row["role_name"] for row in rows]

    def has_role(self, user_id: str, project_id: str, role_name: str) -> bool:
        """Check if user has a specific role for a project."""
        roles = self.get_user_roles(user_id, project_id)
        return role_name in roles

    def close(self) -> None:
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
