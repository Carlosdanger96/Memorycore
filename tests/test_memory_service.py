import pytest

from memorycore.memory_service import MemoryService


def test_project_scope_and_context(tmp_path):
    service = MemoryService(tmp_path / "memory.db")
    first = service.add_memory(project_id="alpha", memory_type="procedure",
        content="Back up the database before migrations")
    service.add_memory(project_id="beta", memory_type="procedure",
        content="Back up the database before migrations")
    context = service.retrieve_context(query="database migrations", project_id="alpha")
    assert context["count"] == 1
    assert context["memories"][0]["id"] == first.id
    assert first.id in context["context_text"]
    service.close()


def test_validation(tmp_path):
    service = MemoryService(tmp_path / "memory.db")
    with pytest.raises(ValueError):
        service.add_memory(project_id="", memory_type="fact", content="x")
    with pytest.raises(ValueError):
        service.add_memory(project_id="p", memory_type="unknown", content="x")
    with pytest.raises(ValueError):
        service.search_memory(query="x", project_id="p", limit=0)
    service.close()
