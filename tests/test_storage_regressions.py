"""Regression checks for retrieval breadth and durable memory relationships."""

from memorycore.memory_service import MemoryService


def test_large_scoped_query_returns_records_beyond_old_candidate_cap(tmp_path):
    service = MemoryService(tmp_path / "breadth.db")
    try:
        for index in range(125):
            service.add_memory(
                project_id="alpha", memory_type="fact",
                content=f"shared token record {index}",
            )
        service.add_memory(project_id="beta", memory_type="fact", content="shared token secret")

        results = service.search_memory(query="shared token", project_id="alpha", limit=125)
        assert len(results) == 125
        assert all(memory.project_id == "alpha" for memory in results)
    finally:
        service.close()


def test_partial_query_fallback_keeps_project_boundary(tmp_path):
    service = MemoryService(tmp_path / "fallback.db")
    try:
        matching = service.add_memory(
            project_id="alpha", memory_type="fact", content="VibeKeys keypad has RGB modes"
        )
        service.add_memory(project_id="beta", memory_type="fact", content="VibeKeys private note")

        results = service.search_memory(
            query="VibeKeys nonexistentterm", project_id="alpha", limit=5
        )
        assert [memory.id for memory in results] == [matching.id]
    finally:
        service.close()


def test_links_survive_restart_without_duplication(tmp_path):
    path = tmp_path / "links.db"
    service = MemoryService(path)
    original = service.add_memory(project_id="alpha", memory_type="fact", content="old fact")
    correction = service.add_memory(project_id="alpha", memory_type="fact", content="new fact")
    service.link_memories(
        from_memory_id=correction.id,
        to_memory_id=original.id,
        relation_type="corrects",
        created_by="reviewer",
    )
    service.close()

    reopened = MemoryService(path)
    try:
        reopened.link_memories(
            from_memory_id=correction.id,
            to_memory_id=original.id,
            relation_type="corrects",
            created_by="reviewer",
        )
        links = reopened.get_memory_links(original.id)
        assert len(links) == 1
        assert links[0]["from_memory_id"] == correction.id
    finally:
        reopened.close()
