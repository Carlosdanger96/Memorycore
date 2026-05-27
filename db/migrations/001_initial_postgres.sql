-- Migration 001: Initial Postgres Schema for Memory Core
-- This migration creates all tables required for Phase 2 Postgres storage

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Memory records table
CREATE TABLE IF NOT EXISTS memories (
    memory_id VARCHAR(64) PRIMARY KEY,
    project_id VARCHAR(64) NOT NULL,
    content TEXT NOT NULL,
    source_refs JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by VARCHAR(64) NOT NULL,
    tags JSONB NOT NULL DEFAULT '[]',
    confidence DECIMAL(3,2) NOT NULL DEFAULT 0.0,
    status VARCHAR(20) NOT NULL DEFAULT 'candidate' 
        CHECK (status IN ('candidate', 'accepted', 'archived'))
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_memories_project_id ON memories(project_id);
CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status);
CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_confidence ON memories(confidence);

-- GIN index for JSONB tags array
CREATE INDEX IF NOT EXISTS idx_memories_tags_gin ON memories USING GIN(tags);

-- Audit log table (append-only)
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    action VARCHAR(20) NOT NULL 
        CHECK (action IN ('read', 'write', 'delete', 'update', 'policy_check')),
    entity_type VARCHAR(20) NOT NULL 
        CHECK (entity_type IN ('memory', 'project', 'config', 'policy')),
    entity_id VARCHAR(64) NOT NULL,
    project_id VARCHAR(64),
    user_id VARCHAR(64) NOT NULL,
    details JSONB NOT NULL DEFAULT '{}',
    ip_address VARCHAR(45),
    user_agent TEXT
);

-- Indexes for audit log
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_project_id ON audit_log(project_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);

-- Projects table for access control
CREATE TABLE IF NOT EXISTS projects (
    project_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by VARCHAR(64) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- Users table
CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(64) PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- Roles table
CREATE TABLE IF NOT EXISTS roles (
    role_id SERIAL PRIMARY KEY,
    role_name VARCHAR(20) NOT NULL UNIQUE 
        CHECK (role_name IN ('admin', 'writer', 'reader', 'auditor')),
    description TEXT
);

-- Insert default roles
INSERT INTO roles (role_name, description) VALUES 
    ('admin', 'Full access to all projects and operations'),
    ('writer', 'Can read and write memories in authorized projects'),
    ('reader', 'Can only read memories in authorized projects'),
    ('auditor', 'Can only read audit logs')
ON CONFLICT (role_name) DO NOTHING;

-- User roles (many-to-many: user to role to project)
CREATE TABLE IF NOT EXISTS user_project_roles (
    user_id VARCHAR(64) NOT NULL,
    project_id VARCHAR(64) NOT NULL,
    role_name VARCHAR(20) NOT NULL 
        CHECK (role_name IN ('admin', 'writer', 'reader', 'auditor')),
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    assigned_by VARCHAR(64) NOT NULL,
    PRIMARY KEY (user_id, project_id, role_name),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
);

-- Index for user project roles
CREATE INDEX IF NOT EXISTS idx_user_project_roles_user ON user_project_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_project_roles_project ON user_project_roles(project_id);

-- Full-text search using tsvector
ALTER TABLE memories ADD COLUMN IF NOT EXISTS search_vector TSVECTOR;

-- Update search_vector for existing rows
UPDATE memories SET search_vector = 
    to_tsvector('english', coalesce(content, '') || ' ' || coalesce(project_id, '')) 
WHERE search_vector IS NULL;

-- Create trigger to update search_vector
CREATE OR REPLACE FUNCTION memories_search_vector_update() RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := to_tsvector('english', coalesce(NEW.content, '') || ' ' || coalesce(NEW.project_id, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger
DROP TRIGGER IF EXISTS trigger_memories_search_vector_update ON memories;
CREATE TRIGGER trigger_memories_search_vector_update
    BEFORE INSERT OR UPDATE ON memories
    FOR EACH ROW EXECUTE FUNCTION memories_search_vector_update();

-- Create GIN index for full-text search
CREATE INDEX IF NOT EXISTS idx_memories_search_vector ON memories USING GIN(search_vector);

-- Create migration tracking table
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id VARCHAR(64) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    description TEXT
);

-- Record this migration
INSERT INTO schema_migrations (migration_id, description) 
VALUES ('001_initial_postgres', 'Initial Postgres schema for Memory Core Phase 2')
ON CONFLICT (migration_id) DO NOTHING;

-- Create a function to check if migration has been applied
CREATE OR REPLACE FUNCTION migration_applied(migration_id VARCHAR(64)) 
RETURNS BOOLEAN AS $$
    SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE migration_id = $1);
$$ LANGUAGE SQL;
