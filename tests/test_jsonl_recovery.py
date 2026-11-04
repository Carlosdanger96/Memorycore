"""A JSONL recovery must retain the same records, relationships, and audit trail."""

import pytest
import sqlite3

from memorycore.memory_service import MemoryService


def test_jsonl_round_trip_preserves_history_links_and_search(tmp_path):
    original = MemoryService(tmp_path / "original.db")
    first = original.add_memory(
        project_id="alpha", memory_type="decision", content="Use source A",
        source_type="document", source_uri="notes/a.md", created_by="client-a",
    )
    replacement = original.correct_memory(first.id, content="Use source B", updated_by="client-b")
    pending = original.add_memory(
        project_id="beta", memory_type="fact", content="Private pending fact",
        status="pending", created_by="client-c",
    )
    before = original.database.snapshot_records()
    export = tmp_path / "memorycore.jsonl"
    assert original.export_jsonl(export) == 3
    original.close()

    restored = MemoryService(tmp_path / "restored.db")
    try:
        assert restored.import_jsonl(export) == 3
        after = restored.database.snapshot_records()
        assert [record.to_dict() for record in after[0]] == [record.to_dict() for record in before[0]]
        assert after[1:] == before[1:]
        assert [record.id for record in restored.search_memory(
            query="source B", project_id="alpha"
        )] == [replacement.id]
        assert restored.get_memory(pending.id).status == "pending"
        assert restored.search_memory(query="pending", project_id="beta") == []
    finally:
        restored.close()


def test_incomplete_export_and_nonempty_target_leave_data_unchanged(tmp_path):
    source = MemoryService(tmp_path / "source.db")
    source.add_memory(project_id="alpha", memory_type="fact", content="Durable fact")
    export = tmp_path / "memorycore.jsonl"
    source.export_jsonl(export)
    source.close()

    target = MemoryService(tmp_path / "target.db")
    existing = target.add_memory(project_id="beta", memory_type="fact", content="Keep this")
    with pytest.raises(ValueError, match="empty"):
        target.import_jsonl(export)
    assert target.get_memory(existing.id) is not None
    target.close()

    broken = tmp_path / "broken.jsonl"
    broken.write_text("\n".join(export.read_text(encoding="utf-8").splitlines()[:-1]) + "\n", encoding="utf-8")
    empty = MemoryService(tmp_path / "empty.db")
    try:
        with pytest.raises(ValueError, match="incomplete"):
            empty.import_jsonl(broken)
        assert empty.health()["memory_count"] == 0
    finally:
        empty.close()


def test_bad_relationship_rolls_back_entire_restore(tmp_path):
    source = MemoryService(tmp_path / "source.db")
    first = source.add_memory(project_id="alpha", memory_type="fact", content="First")
    second = source.add_memory(project_id="alpha", memory_type="fact", content="Second")
    source.link_memories(
        from_memory_id=second.id, to_memory_id=first.id, relation_type="corrects"
    )
    export = tmp_path / "memorycore.jsonl"
    source.export_jsonl(export)
    source.close()

    # A syntactically valid but invalid relationship must not leave imported
    # memories behind. Recalculate the trailer to exercise the database gate.
    import hashlib
    import json

    rows = [json.loads(line) for line in export.read_text(encoding="utf-8").splitlines()]
    next(row for row in rows if row["record_type"] == "memory_link")["to_memory_id"] = "missing"
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows[1:-1])
    rows[-1]["sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    export.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )

    restored = MemoryService(tmp_path / "restored.db")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            restored.import_jsonl(export)
        assert restored.health()["memory_count"] == 0
    finally:
        restored.close()
