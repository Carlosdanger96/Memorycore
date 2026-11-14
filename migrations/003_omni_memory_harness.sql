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
