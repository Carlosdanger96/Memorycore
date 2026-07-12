from memorycore.database import SQLiteDatabase
from memorycore.memory_service import MemoryService
import pytest


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


def test_lifecycle_is_deterministic_and_status_search_is_explicit(tmp_path):
    service = MemoryService(tmp_path / "lifecycle.db")
    pending = service.add_memory(project_id="alpha", memory_type="fact", content="Awaiting review", status="pending")
    assert service.search_memory(query="Awaiting", project_id="alpha") == []
    assert service.search_memory(query="Awaiting", project_id="alpha", status="pending")[0].id == pending.id
    with pytest.raises(ValueError, match="invalid memory status transition"):
        service.update_memory(pending.id, status="superseded")
    approved = service.approve_memory(pending.id, approved_by="reviewer")
    assert approved is not None and approved.status == "active"
    service.close()


def test_memory_audit_history_is_persistent(tmp_path):
    path = tmp_path / "audit.db"
    service = MemoryService(path)
    memory = service.add_memory(project_id="alpha", memory_type="decision",
        content="Use audited shared memory", client_id="mistral")
    service.update_memory(memory.id, summary="Audited", updated_by="hermes")
    history = service.get_memory_history(memory.id)
    assert [event["event_type"] for event in history] == ["memory_created", "memory_updated"]
    assert history[0]["client_id"] == "mistral"
    service.close()
    reopened = MemoryService(path)
    assert len(reopened.get_memory_history(memory.id)) == 2
    reopened.close()
