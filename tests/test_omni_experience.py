import pytest

from memorycore import MemoryService, error_signature


def _trajectory(omni):
    return omni.create_trajectory(
        project_id="p", task_type="repository_modification", task_description="test",
        agent_id="agent", repository="repo", source_revision="abc",
    )


def test_trajectory_is_append_only_ordered_idempotent_and_redacted(tmp_path):
    service = MemoryService(tmp_path / "omni.db")
    trajectory = _trajectory(service.omni)
    event = service.omni.append_trajectory_event(
        trajectory["trajectory_id"], event_type="task_started", sequence=1,
        request_id="same-request", input_data={"Authorization": "Bearer secret-value"},
    )
    repeated = service.omni.append_trajectory_event(
        trajectory["trajectory_id"], event_type="task_started", sequence=99,
        request_id="same-request", input_data={"token": "different"},
    )
    assert event == repeated
    assert event["redacted_input"]["Authorization"] == "[REDACTED]"
    with pytest.raises(ValueError, match="sequence must be 2"):
        service.omni.append_trajectory_event(
            trajectory["trajectory_id"], event_type="tool_called", sequence=3,
        )
    service.close()


def test_error_signature_removes_machine_paths_and_is_stable():
    left = error_signature(
        error_type="ToolError", message="failed at C:\\Users\\Nate\\agent.py",
        behavior_id="agent.output.verify", tool_name="lookup",
        verification_result="false", repository="repo",
    )
    right = error_signature(
        error_type="ToolError", message="failed at /home/other/agent.py",
        behavior_id="agent.output.verify", tool_name="lookup",
        verification_result="false", repository="repo",
    )
    assert left == right


def test_correction_requires_review_and_active_correction_is_ranked(tmp_path):
    service = MemoryService(tmp_path / "correction.db")
    trajectory = _trajectory(service.omni)
    service.omni.append_trajectory_event(
        trajectory["trajectory_id"], event_type="task_failed", sequence=1,
        error_signature_value="err:1",
    )
    correction = service.omni.propose_correction(
        project_id="p", task_type="repository_modification",
        behavior_ids=["agent.output.verify"], repository="repo",
        operation="require_verification", instruction="Verify first.",
        evidence_trajectory_ids=[trajectory["trajectory_id"]], error_signature_value="err:1",
    )
    assert correction["status"] == "pending_review"
    assert service.omni.search_corrections(
        project_id="p", task_type="repository_modification",
        behavior_ids=["agent.output.verify"], repository="repo",
        error_signature_value="err:1",
    ) == []
    active = service.omni.approve_correction(correction["correction_id"], approved_by="reviewer")
    ranked = service.omni.search_corrections(
        project_id="p", task_type="repository_modification",
        behavior_ids=["agent.output.verify"], repository="repo",
        error_signature_value="err:1",
    )
    assert active["status"] == "active"
    assert ranked[0]["correction"]["correction_id"] == correction["correction_id"]
    assert "exact error signature" in ranked[0]["why_matched"]
    service.close()


def test_deterministic_extractor_cites_failed_trajectory_events(tmp_path):
    service = MemoryService(tmp_path / "extract.db")
    trajectory = _trajectory(service.omni)
    service.omni.append_trajectory_event(
        trajectory["trajectory_id"], event_type="task_started", sequence=1,
        behavior_ids=["agent.task.plan"],
    )
    service.omni.append_trajectory_event(
        trajectory["trajectory_id"], event_type="task_failed", sequence=2,
        behavior_ids=["agent.output.verify"], error_signature_value="failure:1",
    )
    correction = service.omni.extract_correction(trajectory["trajectory_id"])
    assert correction["status"] == "pending_review"
    assert correction["operation"] == "require_verification"
    assert correction["provenance"]["evidence_event_ids"]
    service.close()
