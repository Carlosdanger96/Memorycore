"""Rehearse SQLite backup and JSONL restore using disposable records only."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from memorycore.memory_service import MemoryService


def snapshot(service: MemoryService) -> tuple:
    memories, events, links, denials = service.database.snapshot_records()
    return ([item.to_dict() for item in memories], events, links, denials)


def assert_restored(service: MemoryService, expected: tuple, active_id: str, old_id: str) -> None:
    assert snapshot(service) == expected
    assert [item.id for item in service.search_memory(
        query="verified backup", project_id="alpha"
    )] == [active_id]
    assert service.search_memory(query="verified backup", project_id="beta") == []
    assert service.get_memory(old_id).status == "superseded"
    assert service.get_memory_links(old_id)[0]["to_memory_id"] == old_id
    assert len(service.get_memory_history(old_id)) == 2


def main() -> None:
    with TemporaryDirectory(prefix="memorycore-recovery-") as directory:
        root = Path(directory)
        source = MemoryService(root / "source.db")
        old = source.add_memory(project_id="alpha", memory_type="decision",
                                content="Use the first backup design",
                                source_type="document", source_uri="docs/source.md")
        active = source.correct_memory(old.id, content="Use a verified backup design",
                                       updated_by="reviewer")
        source.record_access_denial(client_id="reader", operation="memory_search",
                                    project_id="beta", reason="project_not_allowed")
        expected = snapshot(source)
        source.backup(root / "backup.db")
        source.export_jsonl(root / "export.jsonl")
        source.close()

        for name in ("backup.db", "from-jsonl.db"):
            restored = MemoryService(root / name)
            try:
                if name == "from-jsonl.db":
                    restored.import_jsonl(root / "export.jsonl")
                assert_restored(restored, expected, active.id, old.id)
            finally:
                restored.close()
        print(json.dumps({"ok": True, "methods": ["online_backup", "jsonl_import"],
                          "memories": len(expected[0]), "events": len(expected[1]),
                          "links": len(expected[2]), "denials": len(expected[3])}))


if __name__ == "__main__":
    main()
