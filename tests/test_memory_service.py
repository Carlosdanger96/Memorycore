import pytest

from memorycore.memory_service import MemoryService
from memorycore.models import ValidationError


def test_project_scope_and_context(tmp_path):
    """Test project scoping and context retrieval."""
    service = MemoryService(tmp_path / "memory.db")
    
    first = service.add_memory(
        project_id="alpha",
        memory_type="procedure",
        content="Back up the database before migrations",
    )
    service.add_memory(
        project_id="beta",
        memory_type="procedure",
        content="Back up the database before migrations",
    )
    
    context = service.retrieve_context(query="database migrations", project_id="alpha")
    assert context["count"] == 1
    assert context["memories"][0]["id"] == first.id
    assert first.id in context["context_text"]
    
    service.close()


def test_validation(tmp_path):
    """Test input validation."""
    service = MemoryService(tmp_path / "memory.db")
    
    # Test empty project_id
    with pytest.raises(ValidationError):
        service.add_memory(project_id="", memory_type="fact", content="x")
    
    # Test invalid memory_type
    with pytest.raises(ValidationError):
        service.add_memory(project_id="p", memory_type="unknown", content="x")
    
    # Test empty content
    with pytest.raises(ValidationError):
        service.add_memory(project_id="p", memory_type="fact", content="")
    
    # Test invalid limit
    with pytest.raises(ValidationError):
        service.search_memory(query="x", project_id="p", limit=0)
    
    # Test limit too high
    with pytest.raises(ValidationError):
        service.search_memory(query="x", project_id="p", limit=101)
    
    service.close()


def test_batch_operations(tmp_path):
    """Test batch memory operations."""
    service = MemoryService(tmp_path / "batch.db")
    
    # Test batch add
    memories_data = [
        {"project_id": "batch_test", "memory_type": "fact", "content": f"Fact {i}"}
        for i in range(5)
    ]
    
    memories = service.add_memories(memories_data)
    assert len(memories) == 5
    
    # Test batch get
    memory_ids = [m.id for m in memories]
    retrieved = service.get_memories(memory_ids)
    assert len(retrieved) == 5
    
    service.close()


def test_memory_status_transitions(tmp_path):
    """Test memory status transitions."""
    service = MemoryService(tmp_path / "status.db")
    
    memory = service.add_memory(
        project_id="status_test",
        memory_type="fact",
        content="Status test",
    )
    
    # Test archive
    archived = service.archive_memory(memory.id)
    assert archived is not None
    assert archived.is_archived()
    assert not archived.is_active()
    
    # Test activate
    activated = service.activate_memory(memory.id)
    assert activated is not None
    assert activated.is_active()
    assert not activated.is_archived()
    
    # Test supersede
    superseded = service.supersede_memory(memory.id)
    assert superseded is not None
    assert superseded.is_superseded()
    
    service.close()


def test_memory_helper_methods(tmp_path):
    """Test memory helper methods."""
    service = MemoryService(tmp_path / "helpers.db")
    
    memory = service.add_memory(
        project_id="helpers_test",
        memory_type="fact",
        content="Helper test",
        summary="Test summary",
        tags=["test", "helper"],
        metadata={"key": "value"},
    )
    
    # Test to_dict
    memory_dict = memory.to_dict()
    assert memory_dict["id"] == memory.id
    assert memory_dict["content"] == "Helper test"
    
    # Test to_json
    memory_json = memory.to_json()
    assert memory.id in memory_json
    
    # Test is_active
    assert memory.is_active()
    assert not memory.is_archived()
    assert not memory.is_superseded()
    
    # Test age (should be very small)
    assert memory.age_seconds() >= 0
    assert memory.time_since_update_seconds() >= 0
    
    service.close()


def test_context_manager(tmp_path):
    """Test MemoryService as context manager."""
    with MemoryService(tmp_path / "context.db") as service:
        memory = service.add_memory(
            project_id="context_test",
            memory_type="fact",
            content="Context manager test",
        )
        assert service.get_memory(memory.id) is not None
    
    # Service should be closed after context
    # (We can't directly test this, but it should work)


def test_callbacks(tmp_path):
    """Test memory operation callbacks."""
    added_memories = []
    updated_memories = []
    archived_memories = []
    
    def on_added(memory):
        added_memories.append(memory)
    
    def on_updated(memory):
        updated_memories.append(memory)
    
    def on_archived(memory):
        archived_memories.append(memory)
    
    service = MemoryService(
        tmp_path / "callbacks.db",
        on_memory_added=on_added,
        on_memory_updated=on_updated,
        on_memory_archived=on_archived,
    )
    
    # Test add callback
    memory = service.add_memory(
        project_id="callbacks_test",
        memory_type="fact",
        content="Callback test",
    )
    assert len(added_memories) == 1
    assert added_memories[0].id == memory.id
    
    # Test update callback
    updated = service.update_memory(memory.id, content="Updated content")
    assert len(updated_memories) == 1
    assert updated_memories[0].id == memory.id
    
    # Test archive callback
    archived = service.archive_memory(memory.id)
    assert len(archived_memories) == 1
    assert archived_memories[0].id == memory.id
    
    service.close()
