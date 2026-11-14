CREATE TABLE IF NOT EXISTS omni_correction_events (
    event_id TEXT PRIMARY KEY,
    correction_id TEXT NOT NULL,
    trajectory_id TEXT,
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'proposed','approved','applied','succeeded','failed','partial',
            'rejected','superseded'
        )
    ),
    outcome TEXT CHECK (outcome IS NULL OR outcome IN ('succeeded','failed','partial')),
    evidence_event_id TEXT,
    actor TEXT,
    request_id TEXT,
    details TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(correction_id, request_id)
);

CREATE INDEX IF NOT EXISTS idx_omni_correction_events
ON omni_correction_events(correction_id, created_at, event_id);
