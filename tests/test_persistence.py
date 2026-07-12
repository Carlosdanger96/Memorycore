from memorycore.memory_service import MemoryService
from memorycore.database import SQLiteDatabase


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
