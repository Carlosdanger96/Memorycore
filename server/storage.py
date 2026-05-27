"""Storage Backend for Memory Core.

Provides durable storage for memory records with SQLite and Postgres backends.
Implements the memory schema: memory_id, project_id, content, source_refs,
created_at, created_by, tags, confidence, status.

Phase 2 adds Postgres support with connection pooling and transaction management.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

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
    def from_row(cls, row: Any) -> "MemoryRecord":
        """Create MemoryRecord from database row (SQLite or Postgres)."""
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
    audit_id: Union[int, str]
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
        """Convert to dictionary for serialization."""
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


class StorageError(Exception):
    """Base exception for storage errors."""
    pass


class ConnectionError(StorageError):
    """Exception for connection errors."""
    pass


class TransactionError(StorageError):
    """Exception for transaction errors."""
    pass


class BaseStorage:
    """Abstract base class for storage backends."""
    
    def __init__(self, db_path: str = "file:memorycore.db", **kwargs):
        """Initialize storage backend.
        
        Args:
            db_path: Database connection string/DSN
            **kwargs: Additional backend-specific configuration
        """
        self.db_path = db_path
        self.kwargs = kwargs
    
    def _initialize_database(self) -> None:
        """Initialize database schema. Must be implemented by subclasses."""
        raise NotImplementedError
    
    @contextmanager
    def get_cursor(self) -> Any:
        """Context manager for database cursor. Must be implemented by subclasses."""
        raise NotImplementedError
    
    # Memory CRUD operations
    def create_memory(self, record: MemoryRecord) -> MemoryRecord:
        """Create a new memory record."""
        raise NotImplementedError
    
    def get_memory(self, memory_id: str) -> Optional[MemoryRecord]:
        """Get a memory record by ID."""
        raise NotImplementedError
    
    def update_memory(self, memory_id: str, updates: Dict[str, Any]) -> Optional[MemoryRecord]:
        """Update a memory record."""
        raise NotImplementedError
    
    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory record."""
        raise NotImplementedError
    
    def search_memories(
        self,
        project_id: Optional[str] = None,
        query: Optional[str] = None,
        status: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[MemoryRecord], int]:
        """Search memory records with filters."""
        raise NotImplementedError
    
    def get_memories_by_project(self, project_id: str, limit: int = 100) -> List[MemoryRecord]:
        """Get all memories for a specific project."""
        raise NotImplementedError
    
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
        raise NotImplementedError
    
    def get_audit_logs(
        self,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[AuditRecord], int]:
        """Get audit log entries with filters."""
        raise NotImplementedError
    
    # Project operations
    def create_project(self, project_id: str, name: str, created_by: str, description: str = "") -> bool:
        """Create a new project."""
        raise NotImplementedError
    
    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get project by ID."""
        raise NotImplementedError
    
    def project_exists(self, project_id: str) -> bool:
        """Check if project exists."""
        raise NotImplementedError
    
    # User operations
    def create_user(self, user_id: str, username: str, email: str = "") -> bool:
        """Create a new user."""
        raise NotImplementedError
    
    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        raise NotImplementedError
    
    def user_exists(self, user_id: str) -> bool:
        """Check if user exists."""
        raise NotImplementedError
    
    # Role operations
    def grant_role(self, user_id: str, project_id: str, role_name: str, assigned_by: str) -> bool:
        """Grant a role to a user for a project."""
        raise NotImplementedError
    
    def get_user_roles(self, user_id: str, project_id: Optional[str] = None) -> List[str]:
        """Get roles for a user, optionally filtered by project."""
        raise NotImplementedError
    
    def has_role(self, user_id: str, project_id: str, role_name: str) -> bool:
        """Check if user has a specific role for a project."""
        raise NotImplementedError
    
    def close(self) -> None:
        """Close database connection."""
        pass
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class SQLiteStorage(BaseStorage):
    """SQLite storage backend for Memory Core."""

    def __init__(self, db_path: str = "file:memorycore.db", **kwargs):
        """Initialize SQLite storage.
        
        Args:
            db_path: SQLite DSN or file path
            **kwargs: Additional configuration (ignored for SQLite)
        """
        super().__init__(db_path, **kwargs)
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
        
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now')),
            description TEXT
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
        """Context manager for database cursor with transaction management."""
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
        """Search memory records with filters."""
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


class PostgresStorage(BaseStorage):
    """Postgres storage backend for Memory Core with connection pooling."""

    def __init__(
        self,
        db_path: str = None,
        host: str = "localhost",
        port: int = 5432,
        database: str = "memorycore",
        user: str = "memorycore",
        password: str = "",
        sslmode: str = "prefer",
        min_connections: int = 1,
        max_connections: int = 10,
        connection_timeout: int = 30,
        **kwargs
    ):
        """Initialize Postgres storage with connection pooling.
        
        Args:
            db_path: Connection string (if provided, overrides individual params)
            host: Postgres host
            port: Postgres port
            database: Database name
            user: Database user
            password: Database password
            sslmode: SSL mode (disable, allow, prefer, require)
            min_connections: Minimum connections in pool
            max_connections: Maximum connections in pool
            connection_timeout: Connection timeout in seconds
            **kwargs: Additional psycopg2 connection parameters
        """
        super().__init__(db_path or f"host={host} port={port} dbname={database} user={user}", **kwargs)
        
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.sslmode = sslmode
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.connection_timeout = connection_timeout
        
        # Connection pool
        self._pool = None
        
        # Import psycopg2
        try:
            import psycopg2
            from psycopg2 import pool
            self.psycopg2 = psycopg2
            self.pool = pool
        except ImportError:
            raise ImportError(
                "psycopg2-binary is required for Postgres storage. "
                "Install with: pip install psycopg2-binary"
            )
        
        # Initialize connection pool
        self._initialize_pool()
        self._initialize_database()

    def _initialize_pool(self) -> None:
        """Initialize connection pool."""
        if self._pool is None:
            self._pool = self.pool.SimpleConnectionPool(
                minconn=self.min_connections,
                maxconn=self.max_connections,
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                sslmode=self.sslmode,
                connect_timeout=self.connection_timeout,
            )

    def _get_connection_from_pool(self):
        """Get a connection from the pool."""
        if self._pool is None:
            self._initialize_pool()
        return self._pool.getconn()

    def _return_connection_to_pool(self, conn):
        """Return a connection to the pool."""
        if self._pool and conn:
            try:
                self._pool.putconn(conn)
            except Exception as e:
                logger.error(f"Error returning connection to pool: {e}")
                conn.close()

    def _initialize_database(self) -> None:
        """Initialize database schema using migration scripts."""
        # Check if migrations table exists
        conn = None
        try:
            conn = self._get_connection_from_pool()
            cursor = conn.cursor()
            
            # Check if schema_migrations table exists
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'schema_migrations'
                );
            """)
            migrations_exist = cursor.fetchone()[0]
            
            if not migrations_exist:
                # Run initial migration
                migrations_dir = Path(__file__).parent.parent / "db" / "migrations"
                if migrations_dir.exists():
                    migration_files = sorted(migrations_dir.glob("*.sql"))
                    for migration_file in migration_files:
                        with open(migration_file, "r") as f:
                            migration_sql = f.read()
                        cursor.execute(migration_sql)
                        conn.commit()
                        logger.info(f"Applied migration: {migration_file.name}")
                else:
                    # Fallback to schema.sql
                    schema_path = Path(__file__).parent.parent / "db" / "schema.sql"
                    if schema_path.exists():
                        with open(schema_path, "r") as f:
                            schema_sql = f.read()
                        # Filter out SQLite-specific statements
                        schema_sql = self._filter_sqlite_statements(schema_sql)
                        cursor.execute(schema_sql)
                        conn.commit()
            
            cursor.close()
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self._return_connection_to_pool(conn)

    def _filter_sqlite_statements(self, sql: str) -> str:
        """Filter out SQLite-specific statements for Postgres compatibility."""
        lines = []
        skip_until_semicolon = False
        
        for line in sql.split('\n'):
            line = line.strip()
            
            # Skip SQLite-specific statements
            if line.startswith('--') or line.startswith('PRAGMA') or line.startswith('CREATE VIRTUAL TABLE'):
                continue
            
            # Skip FTS-specific triggers
            if 'memories_fts' in line:
                continue
            
            # Convert SQLite types to Postgres types
            line = line.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'BIGSERIAL PRIMARY KEY')
            line = line.replace('TEXT NOT NULL DEFAULT (datetime(', 'TEXT NOT NULL DEFAULT (')
            line = line.replace("datetime('now')", 'NOW()')
            line = line.replace('BOOLEAN NOT NULL DEFAULT 1', 'BOOLEAN NOT NULL DEFAULT TRUE')
            line = line.replace('BOOLEAN NOT NULL DEFAULT 0', 'BOOLEAN NOT NULL DEFAULT FALSE')
            line = line.replace('INSERT OR IGNORE', 'INSERT INTO ... ON CONFLICT DO NOTHING')
            line = line.replace('INSERT OR REPLACE', 'INSERT INTO ... ON CONFLICT DO UPDATE')
            
            # Skip empty lines
            if not line:
                continue
            
            lines.append(line)
        
        return '\n'.join(lines)

    @contextmanager
    def get_cursor(self) -> Any:
        """Context manager for database cursor with transaction management."""
        conn = None
        cursor = None
        try:
            conn = self._get_connection_from_pool()
            cursor = conn.cursor()
            yield cursor
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            raise TransactionError(f"Transaction failed: {e}") from e
        finally:
            if cursor:
                cursor.close()
            if conn:
                self._return_connection_to_pool(conn)

    # Memory CRUD operations
    
    def create_memory(self, record: MemoryRecord) -> MemoryRecord:
        """Create a new memory record."""
        with self.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO memories (memory_id, project_id, content, source_refs, 
                                     created_at, created_by, tags, confidence, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (memory_id) DO UPDATE 
                SET content = EXCLUDED.content, 
                    source_refs = EXCLUDED.source_refs,
                    created_at = EXCLUDED.created_at,
                    created_by = EXCLUDED.created_by,
                    tags = EXCLUDED.tags,
                    confidence = EXCLUDED.confidence,
                    status = EXCLUDED.status
                RETURNING *
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
            row = cursor.fetchone()
            if row:
                return MemoryRecord.from_row(row)
        return record

    def get_memory(self, memory_id: str) -> Optional[MemoryRecord]:
        """Get a memory record by ID."""
        with self.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM memories WHERE memory_id = %s",
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
            set_clauses.append("content = %s")
            params.append(updates["content"])
        if "source_refs" in updates:
            set_clauses.append("source_refs = %s")
            params.append(json.dumps(updates["source_refs"]))
        if "tags" in updates:
            set_clauses.append("tags = %s")
            params.append(json.dumps(updates["tags"]))
        if "confidence" in updates:
            set_clauses.append("confidence = %s")
            params.append(updates["confidence"])
        if "status" in updates:
            set_clauses.append("status = %s")
            params.append(updates["status"])

        if not set_clauses:
            return existing

        params.append(memory_id)
        query = f"UPDATE memories SET {', '.join(set_clauses)} WHERE memory_id = %s RETURNING *"
        
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
            if row:
                return MemoryRecord.from_row(row)
        
        return self.get_memory(memory_id)

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory record."""
        with self.get_cursor() as cursor:
            cursor.execute("DELETE FROM memories WHERE memory_id = %s", (memory_id,))
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
        """Search memory records with filters using full-text search."""
        where_clauses = []
        params = []

        if project_id:
            where_clauses.append("project_id = %s")
            params.append(project_id)
        
        if status:
            where_clauses.append("status = %s")
            params.append(status)
        
        if tags:
            # Use JSONB array contains operator for Postgres
            for tag in tags:
                where_clauses.append("tags @> %s")
                params.append(json.dumps([tag]))

        # Count query
        count_where = " AND ".join(where_clauses) if where_clauses else "TRUE"
        
        with self.get_cursor() as cursor:
            # Get total count
            cursor.execute(f"SELECT COUNT(*) FROM memories WHERE {count_where}", params)
            total = cursor.fetchone()[0]
            
            # Build search query
            if query:
                # Use full-text search
                where_clauses.append("search_vector @@ to_tsquery('english', %s)")
                params.append(query)
                search_where = " AND ".join(where_clauses)
                cursor.execute(
                    f"SELECT * FROM memories WHERE {search_where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
                    params + [limit, offset]
                )
            else:
                search_where = " AND ".join(where_clauses) if where_clauses else "TRUE"
                cursor.execute(
                    f"SELECT * FROM memories WHERE {search_where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
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
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING audit_id, timestamp
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
            row = cursor.fetchone()
            audit_id = row[0] if row else None
        
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
            where_clauses.append("project_id = %s")
            params.append(project_id)
        
        if user_id:
            where_clauses.append("user_id = %s")
            params.append(user_id)
        
        if action:
            where_clauses.append("action = %s")
            params.append(action)

        count_where = " AND ".join(where_clauses) if where_clauses else "TRUE"
        
        with self.get_cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM audit_log WHERE {count_where}", params)
            total = cursor.fetchone()[0]
            
            search_where = " AND ".join(where_clauses) if where_clauses else "TRUE"
            cursor.execute(
                f"SELECT * FROM audit_log WHERE {search_where} ORDER BY timestamp DESC LIMIT %s OFFSET %s",
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
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (project_id) DO NOTHING
                """, (project_id, name, description, created_by))
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Error creating project: {e}")
                return False

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get project by ID."""
        with self.get_cursor() as cursor:
            cursor.execute("SELECT * FROM projects WHERE project_id = %s", (project_id,))
            row = cursor.fetchone()
            if row:
                # Convert row to dict
                return {col: row[col] for col in [d[0] for d in cursor.description]}
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
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                """, (user_id, username, email))
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Error creating user: {e}")
                return False

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        with self.get_cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
            if row:
                return {col: row[col] for col in [d[0] for d in cursor.description]}
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
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id, project_id, role_name) DO NOTHING
                """, (user_id, project_id, role_name, assigned_by))
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Error granting role: {e}")
                return False

    def get_user_roles(self, user_id: str, project_id: Optional[str] = None) -> List[str]:
        """Get roles for a user, optionally filtered by project."""
        with self.get_cursor() as cursor:
            if project_id:
                cursor.execute(
                    "SELECT role_name FROM user_project_roles WHERE user_id = %s AND project_id = %s",
                    (user_id, project_id)
                )
            else:
                cursor.execute(
                    "SELECT role_name FROM user_project_roles WHERE user_id = %s",
                    (user_id,)
                )
            rows = cursor.fetchall()
            return [row[0] for row in rows]

    def has_role(self, user_id: str, project_id: str, role_name: str) -> bool:
        """Check if user has a specific role for a project."""
        roles = self.get_user_roles(user_id, project_id)
        return role_name in roles

    def close(self) -> None:
        """Close all connections in the pool."""
        if self._pool:
            self._pool.closeall()
            self._pool = None


def create_storage(config: Dict[str, Any]) -> BaseStorage:
    """Factory function to create storage backend based on configuration.
    
    Args:
        config: Storage configuration dictionary with keys:
            - driver: 'sqlite' or 'postgres'
            - dsn: Connection string (for SQLite)
            - host, port, database, user, password, sslmode (for Postgres)
            - min_connections, max_connections, connection_timeout (for Postgres)
    
    Returns:
        Storage backend instance (SQLiteStorage or PostgresStorage)
    """
    driver = config.get("driver", "sqlite")
    
    if driver == "postgres":
        return PostgresStorage(
            host=config.get("host", "localhost"),
            port=config.get("port", 5432),
            database=config.get("database", "memorycore"),
            user=config.get("user", "memorycore"),
            password=config.get("password", ""),
            sslmode=config.get("sslmode", "prefer"),
            min_connections=config.get("min_connections", 1),
            max_connections=config.get("max_connections", 10),
            connection_timeout=config.get("connection_timeout", 30),
        )
    else:
        # Default to SQLite
        dsn = config.get("dsn", "file:memorycore.db")
        return SQLiteStorage(db_path=dsn)


# Backwards compatibility: Storage is an alias for SQLiteStorage
Storage = SQLiteStorage
