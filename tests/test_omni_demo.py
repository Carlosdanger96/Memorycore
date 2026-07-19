import json

from memorycore.demo.runner import run_demo
from memorycore.memory_service import MemoryService


def test_full_failed_to_corrected_demo_persists_across_restart(tmp_path):
    report = run_demo(tmp_path / "run")
    assert report["ok"] is True
    assert report["duration_seconds"] >= 0
    assert report["repository_revision"]
    assert report["revision_decision_id"].startswith("revision_")
    assert report["correction_id"] in report["retrieved_correction_ids"]
    loaded = json.loads((tmp_path / "run" / "demo-report.json").read_text(encoding="utf-8"))
    assert loaded["successful_trajectory_id"] == report["successful_trajectory_id"]
    reopened = MemoryService(report["database"])
    successful = reopened.omni.get_trajectory(report["successful_trajectory_id"])
    assert successful["outcome"] == "success"
    assert any(item["event_type"] == "verification_run" for item in successful["events"])
    correction = reopened.database.get_omni_record(report["correction_id"], "correction")
    assert correction["use_count"] == 1 and correction["success_count"] == 1
    events = reopened.omni.list_correction_events(report["correction_id"])
    assert any(item["event_type"] == "succeeded" for item in events)
    backup = tmp_path / "omni-backup.db"
    reopened.backup(backup)
    reopened.close()
    restored = MemoryService(backup)
    restored_trajectory = restored.omni.get_trajectory(report["successful_trajectory_id"])
    assert restored_trajectory is not None and restored_trajectory["outcome"] == "success"
    restored.close()
