from memorycore.database import SQLiteDatabase
from memorycore.memory_service import MemoryService


def test_database_crud_and_fts(tmp_path):
    service = MemoryService(tmp_path / "memory.db")
    memory = service.add_memory(project_id="alpha", memory_type="decision",
        content="Use SQLite as the canonical local store", summary="SQLite is canonical",
        tags=["storage", "sqlite"])
    assert service.get_memory(memory.id) == memory
    assert [item.id for item in service.search_memory(query="canonical SQLite", project_id="alpha")] == [memory.id]
    updated = service.update_memory(memory.id, summary="SQLite remains canonical")
    assert updated is not None and updated.summary == "SQLite remains canonical"
    archived = service.archive_memory(memory.id)
    assert archived is not None and archived.status == "archived"
    assert service.search_memory(query="SQLite", project_id="alpha") == []
    service.close()


def test_database_health(tmp_path):
    database = SQLiteDatabase(tmp_path / "health.db")
    database.initialize()
    health = database.health()
    assert health["ok"] is True and health["fts5"] is True
    database.close()
