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
    versions = [
        row[0] for row in database.connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
    ]
    assert versions == [1, 2, 3, 4]
    assert database.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='omni_correction_events'"
    ).fetchone() is not None
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


def test_sqlite_backup_and_jsonl_export(tmp_path):
    source = tmp_path / "source.db"
    service = MemoryService(source)
    memory = service.add_memory(project_id="alpha", memory_type="fact", content="Export this memory")
    service.update_memory(memory.id, summary="Exported", updated_by="tester")
    backup = tmp_path / "backup.db"
    exported = tmp_path / "memorycore.jsonl"
    service.backup(backup)
    assert service.export_jsonl(exported) == 1
    service.close()
    restored = MemoryService(backup)
    assert restored.get_memory(memory.id) is not None
    restored.close()
    lines = exported.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3 and '"record_type": "memory_event"' in lines[1]
    imported = MemoryService(tmp_path / "imported.db")
    assert imported.import_jsonl(exported) == 1
    assert imported.get_memory(memory.id) is not None
    imported.close()


def test_exact_duplicate_detection_is_project_scoped(tmp_path):
    service = MemoryService(tmp_path / "duplicates.db")
    first = service.add_memory(project_id="alpha", memory_type="fact", content="Shared memory is durable")
    assert service.find_exact_duplicate(project_id="alpha", memory_type="fact", content="  shared MEMORY is durable ") is not None
    assert service.find_exact_duplicate(project_id="beta", memory_type="fact", content=first.content) is None
    service.close()


def test_supersession_is_atomic_and_audited(tmp_path):
    service = MemoryService(tmp_path / "replace.db")
    original = service.add_memory(project_id="alpha", memory_type="decision", content="Use SQLite")
    replacement = service.supersede_memory(original.id, content="Use SQLite behind Memorycore", updated_by="hermes")
    assert service.get_memory(original.id).status == "superseded"
    assert replacement.status == "active"
    assert any(event["event_type"] == "memory_superseded" for event in service.get_memory_history(original.id))
    service.close()


def test_retrieval_uses_candidate_pool_and_exact_summary(tmp_path):
    service = MemoryService(tmp_path / "retrieval.db")
    for index in range(30):
        service.add_memory(project_id="alpha", memory_type="note", content=f"A shared token record {index}")
    exact = service.add_memory(project_id="alpha", memory_type="note", content="Different body", summary="Shared token")
    results = service.search_memory(query="shared token", project_id="alpha", limit=1)
    assert results[0].id == exact.id
    plan = service.database.connection.execute("EXPLAIN QUERY PLAN SELECT * FROM memories WHERE project_id='alpha' AND status='active' ORDER BY updated_at DESC").fetchall()
    assert any("idx_memories_active_project_updated" in row[3] for row in plan)
    service.close()
