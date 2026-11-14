from memorycore.memory_service import MemoryService
from memorycore.database import SCHEMA_SQL, SQLiteDatabase


def test_memory_survives_restart(tmp_path):
    path = tmp_path / "persistent.db"
    first = MemoryService(path)
    memory = first.add_memory(project_id="alpha", memory_type="fact",
        content="This memory must survive restart")
    first.close()
    second = MemoryService(path)
    restored = second.get_memory(memory.id)
    assert restored is not None and restored.content == "This memory must survive restart"
    assert second.search_memory(query="survive restart", project_id="alpha")[0].id == memory.id
    second.close()


def test_v01_database_is_upgraded_for_approval_statuses(tmp_path):
    path = tmp_path / "v01.db"
    database = SQLiteDatabase(path)
    database.connection.executescript("""
        CREATE TABLE memories (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, memory_type TEXT NOT NULL,
            content TEXT NOT NULL, summary TEXT, tags TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived','superseded')),
            created_by TEXT, metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        INSERT INTO memories VALUES (
            'old-memory', 'alpha', 'fact', 'Preserve this legacy memory', NULL, '[]',
            'active', 'legacy-client', '{"origin":"v0.1"}',
            '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
        );
    """)
    database.connection.commit()
    database.initialize()
    database.initialize()
    database.close()
    service = MemoryService(path)
    restored = service.get_memory("old-memory")
    assert restored is not None and restored.metadata == {"origin": "v0.1"}
    assert service.search_memory(query="legacy memory", project_id="alpha")[0].id == "old-memory"
    pending = service.add_memory(project_id="alpha", memory_type="note", content="Needs review", status="pending")
    assert pending.status == "pending" and pending.source_type == "manual_import"
    service.close()


def test_legacy_constraint_upgrade_preserves_audit_links_and_provenance(tmp_path):
    path = tmp_path / "legacy-with-history.db"
    database = SQLiteDatabase(path)
    database.connection.executescript(SCHEMA_SQL.replace("'observation',", ""))
    for memory_id in ("original", "replacement"):
        database.connection.execute(
            """INSERT INTO memories (
                id, project_id, memory_type, content, tags, status,
                created_by, updated_by, client_id, source_type, source_uri,
                confidence, metadata, created_at, updated_at
            ) VALUES (?, 'alpha', 'fact', ?, '[]', 'active',
                      'writer', 'reviewer', 'client-a', 'document', 'notes/a.md',
                      0.9, '{"source":"legacy"}', '2026-01-01', '2026-01-02')""",
            (memory_id, f"Legacy {memory_id} fact"),
        )
    for event_id, event_type in (("z-first", "memory_created"),
                                 ("a-second", "memory_updated")):
        database.connection.execute(
            """INSERT INTO memory_events (
                id, memory_id, project_id, event_type, details, created_at
            ) VALUES (?, 'original', 'alpha', ?, '{}', '2026-01-01')""",
            (event_id, event_type),
        )
    database.connection.execute(
        """INSERT INTO memory_links (
            id, from_memory_id, to_memory_id, relation_type, created_at
        ) VALUES ('link-1', 'replacement', 'original', 'corrects', '2026-01-02')"""
    )
    database.connection.commit()
    database.initialize()
    database.close()

    service = MemoryService(path)
    try:
        original = service.get_memory("original")
        assert original is not None
        assert original.client_id == "client-a"
        assert original.source_uri == "notes/a.md"
        assert original.confidence == 0.9
        assert original.metadata == {"source": "legacy"}
        assert [event["id"] for event in service.get_memory_history("original")] == [
            "z-first", "a-second"
        ]
        assert service.get_memory_links("original")[0]["id"] == "link-1"
        assert service.search_memory(query="Legacy original", project_id="alpha")[0].id == "original"
        assert service.database.connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        service.close()
