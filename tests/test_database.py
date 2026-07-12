import pytest

from memorycore.database import (
    DatabaseError,
    MemoryNotFoundError,
    SQLiteDatabase,
)
from memorycore.memory_service import MemoryService


def test_database_crud_and_fts(tmp_path):
    """Test basic CRUD operations and FTS5 search."""
    service = MemoryService(tmp_path / "memory.db")
    
    # Test add and get
    memory = service.add_memory(
        project_id="alpha",
        memory_type="decision",
        content="Use SQLite as the canonical local store",
        summary="SQLite is canonical",
        tags=["storage", "sqlite"],
    )
    assert service.get_memory(memory.id) == memory
    
    # Test search
    results = service.search_memory(query="canonical SQLite", project_id="alpha")
    assert len(results) == 1
    assert results[0].id == memory.id
    
    # Test update
    updated = service.update_memory(memory.id, summary="SQLite remains canonical")
    assert updated is not None
    assert updated.summary == "SQLite remains canonical"
    
    # Test archive
    archived = service.archive_memory(memory.id)
    assert archived is not None
    assert archived.status == "archived"
    
    # Archived memories should not appear in search
    assert service.search_memory(query="SQLite", project_id="alpha") == []
    
    service.close()


def test_database_health(tmp_path):
    """Test database health check."""
    database = SQLiteDatabase(tmp_path / "health.db")
    database.initialize()
    health = database.health()
    assert health["ok"] is True
    assert health["fts5"] is True
    assert health["wal_mode"] is True
    database.close()


def test_database_stats(tmp_path):
    """Test database statistics."""
    service = MemoryService(tmp_path / "stats.db")
    
    # Add some memories
    service.add_memory(project_id="test", memory_type="fact", content="Test fact 1")
    service.add_memory(project_id="test", memory_type="fact", content="Test fact 2")
    service.add_memory(project_id="other", memory_type="decision", content="Test decision")
    
    # Test overall stats
    stats = service.get_stats()
    assert stats["total"] == 3
    assert stats["active"] == 3
    assert stats["archived"] == 0
    
    # Test project-specific stats
    project_stats = service.get_stats(project_id="test")
    assert project_stats["total"] == 2
    assert project_stats["project_id"] == "test"
    
    service.close()


def test_database_backup_restore(tmp_path):
    """Test database backup and restore."""
    db_path = tmp_path / "backup_test.db"
    backup_path = tmp_path / "backup.db"
    
    # Create and populate database
    service = MemoryService(db_path)
    memory = service.add_memory(
        project_id="backup_test",
        memory_type="fact",
        content="Backup test content",
        tags=["backup"],
    )
    service.close()
    
    # Create backup
    service = MemoryService(db_path)
    assert service.backup(backup_path) is True
    service.close()
    
    # Verify backup file exists
    assert backup_path.exists()
    
    # Restore from backup to a new location
    restore_path = tmp_path / "restored.db"
    service = MemoryService(restore_path)
    assert service.restore(backup_path) is True
    
    # Verify restored data
    restored_memory = service.get_memory(memory.id)
    assert restored_memory is not None
    assert restored_memory.content == "Backup test content"
    assert restored_memory.tags == ["backup"]
    
    service.close()


def test_database_list_projects(tmp_path):
    """Test listing projects."""
    service = MemoryService(tmp_path / "projects.db")
    
    # Add memories to different projects
    service.add_memory(project_id="project_a", memory_type="fact", content="A")
    service.add_memory(project_id="project_b", memory_type="fact", content="B")
    service.add_memory(project_id="project_a", memory_type="decision", content="C")
    
    projects = service.list_projects()
    assert len(projects) == 2
    assert "project_a" in projects
    assert "project_b" in projects
    
    service.close()


def test_database_delete(tmp_path):
    """Test memory deletion."""
    service = MemoryService(tmp_path / "delete.db")
    
    memory = service.add_memory(
        project_id="delete_test",
        memory_type="fact",
        content="To be deleted",
    )
    
    # Verify memory exists
    assert service.get_memory(memory.id) is not None
    
    # Delete memory
    assert service.delete_memory(memory.id) is True
    
    # Verify memory is gone
    assert service.get_memory(memory.id) is None
    
    service.close()


def test_database_error_handling(tmp_path):
    """Test error handling."""
    # Test with invalid path
    with pytest.raises(Exception):
        SQLiteDatabase("/nonexistent/directory/db.db")
    
    # Test getting non-existent memory
    service = MemoryService(tmp_path / "error.db")
    assert service.get_memory("nonexistent-id") is None
    assert service.delete_memory("nonexistent-id") is False
    service.close()
