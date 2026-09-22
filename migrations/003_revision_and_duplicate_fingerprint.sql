-- Migration 3: revision and duplicate fingerprint (reference copy).
--
-- Applied transactionally by the embedded migration runner in
-- src/memorycore/database.py, which also backfills content_fingerprint for
-- existing rows. Kept here as the canonical schema reference.
--
-- The unique partial index enforces duplicate protection at the database
-- level: exactly one live (pending or active) memory may exist per (project,
-- memory type, normalized content fingerprint). Dead lifecycle states free
-- their fingerprint for future reuse. The application-level pre-check is
-- advisory; this constraint is authoritative under concurrent writers.

ALTER TABLE memories ADD COLUMN revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE memories ADD COLUMN content_fingerprint TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_live_fingerprint
ON memories(project_id, memory_type, content_fingerprint)
WHERE content_fingerprint IS NOT NULL AND status IN ('pending', 'active');
