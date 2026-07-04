from memorycore.memory_service import MemoryService


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
