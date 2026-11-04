"""Duplicate proposals may be reviewed, but cannot silently become active."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from memorycore.memory_service import MemoryService


def test_probable_duplicate_is_visible_and_approval_is_blocked(tmp_path):
    service = MemoryService(tmp_path / "duplicates.db")
    try:
        active = service.add_memory(
            project_id="alpha", memory_type="decision",
            content="Use one durable shared memory service",
        )
        proposed = service.add_memory(
            project_id="alpha", memory_type="decision",
            content="Use one reliable durable shared memory service", status="pending",
        )
        assert service.duplicate_candidates(
            project_id="alpha", content=proposed.content
        ) == [{"memory_id": active.id, "reason": "probable", "score": 0.8571}]
        with pytest.raises(ValueError, match=active.id):
            service.approve_memory(proposed.id, approved_by="reviewer")
        assert service.get_memory(proposed.id).status == "pending"
        assert [event["event_type"] for event in service.get_memory_history(proposed.id)] == [
            "memory_created"
        ]
        assert service.duplicate_candidates(project_id="beta", content=proposed.content) == []
    finally:
        service.close()


def test_concurrent_exact_active_writes_cannot_both_commit(tmp_path):
    path = tmp_path / "concurrent.db"
    MemoryService(path).close()
    barrier = Barrier(2)

    def write():
        service = MemoryService(path)
        try:
            barrier.wait(timeout=5)
            try:
                service.add_memory(
                    project_id="alpha", memory_type="fact", content="One durable fact"
                )
                return "created"
            except ValueError as exc:
                assert "duplicate" in str(exc)
                return "blocked"
        finally:
            service.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: write(), range(2)))
    assert sorted(results) == ["blocked", "created"]

    service = MemoryService(path)
    try:
        assert service.health()["memory_count"] == 1
    finally:
        service.close()


def test_correction_cannot_compete_with_another_active_record(tmp_path):
    service = MemoryService(tmp_path / "correction.db")
    try:
        first = service.add_memory(
            project_id="alpha", memory_type="fact", content="Memorycore serves project A"
        )
        second = service.add_memory(
            project_id="alpha", memory_type="fact", content="Memorycore serves project B"
        )
        with pytest.raises(ValueError, match=second.id):
            service.correct_memory(
                first.id, content=second.content, updated_by="reviewer"
            )
        assert service.get_memory(first.id).status == "active"
        assert service.health()["memory_count"] == 2
    finally:
        service.close()
