-- Memory Core Database Schema
-- SQLite implementation for Phase 1 MVP
-- Postgres-compatible for Phase 2

-- For SQLite: Enable WAL mode for better concurrency
-- PRAGMA journal_mode=WAL;
-- PRAGMA foreign_keys=ON;

-- Memory records table
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

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_memories_project_id ON memories(project_id);
CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status);
CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_tags ON memories(tags);
CREATE INDEX IF NOT EXISTS idx_memories_confidence ON memories(confidence);

-- Audit log table (append-only)
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

-- Indexes for audit log
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_project_id ON audit_log(project_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);

-- Projects table for access control
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1
);

-- Users table
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    email TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    is_active BOOLEAN NOT NULL DEFAULT 1
);

-- Roles table
CREATE TABLE IF NOT EXISTS roles (
    role_id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_name TEXT NOT NULL UNIQUE CHECK (role_name IN ('admin', 'writer', 'reader', 'auditor')),
    description TEXT
);

-- Insert default roles
INSERT OR IGNORE INTO roles (role_name, description) VALUES 
    ('admin', 'Full access to all projects and operations'),
    ('writer', 'Can read and write memories in authorized projects'),
    ('reader', 'Can only read memories in authorized projects'),
    ('auditor', 'Can only read audit logs');

-- User roles (many-to-many: user to role to project)
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

-- Index for user project roles
CREATE INDEX IF NOT EXISTS idx_user_project_roles_user ON user_project_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_project_roles_project ON user_project_roles(project_id);

-- Full-text search virtual table for memory content (SQLite only)
-- For Postgres, use the migration script which creates tsvector-based search
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    memory_id,
    project_id,
    content,
    tags,
    tokenize="unicode61 remove_diacritics 2"
);

-- Trigger to keep FTS table in sync (SQLite only)
CREATE TRIGGER IF NOT EXISTS memories_fts_insert AFTER INSERT ON memories
BEGIN
    INSERT INTO memories_fts (memory_id, project_id, content, tags)
    VALUES (new.memory_id, new.project_id, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_fts_update AFTER UPDATE ON memories
BEGIN
    UPDATE memories_fts 
    SET content = new.content, tags = new.tags 
    WHERE memory_id = old.memory_id;
END;

CREATE TRIGGER IF NOT EXISTS memories_fts_delete AFTER DELETE ON memories
BEGIN
    DELETE FROM memories_fts WHERE memory_id = old.memory_id;
END;

-- Migration tracking table (for Postgres compatibility)
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT
);
