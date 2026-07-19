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


def test_correction_outcome_is_evidence_backed_idempotent_and_persistent(tmp_path):
    database = tmp_path / "outcome.db"
    service = MemoryService(database)
    failed = _trajectory(service.omni)
    service.omni.append_trajectory_event(
        failed["trajectory_id"], event_type="task_failed", sequence=1,
        request_id="failed-terminal", error_signature_value="failure:outcome",
    )
    correction = service.omni.propose_correction(
        project_id="p", task_type="repository_modification", behavior_ids=[],
        repository="repo", operation="require_verification", instruction="Verify.",
        evidence_trajectory_ids=[failed["trajectory_id"]],
        error_signature_value="failure:outcome",
    )
    correction = service.omni.approve_correction(
        correction["correction_id"], approved_by="reviewer",
    )
    successful = _trajectory(service.omni)
    service.omni.append_trajectory_event(
        successful["trajectory_id"], event_type="correction_applied", sequence=1,
        request_id="applied", correction_ids=[correction["correction_id"]],
    )
    completed = service.omni.append_trajectory_event(
        successful["trajectory_id"], event_type="task_completed", sequence=2,
        request_id="completed",
    )
    first = service.omni.record_correction_outcome(
        correction["correction_id"], trajectory_id=successful["trajectory_id"],
        outcome="succeeded", evidence_event_id=completed["event_id"], actor="agent",
        request_id="outcome-1", details={"Authorization": "Bearer hidden-value"},
    )
    repeated = service.omni.record_correction_outcome(
        correction["correction_id"], trajectory_id=successful["trajectory_id"],
        outcome="succeeded", evidence_event_id=completed["event_id"], actor="agent",
        request_id="outcome-1",
    )
    assert first["created"] is True and repeated["created"] is False
    assert repeated["correction"]["use_count"] == 1
    assert repeated["correction"]["success_count"] == 1
    assert repeated["correction"]["successful_trajectory_ids"] == [successful["trajectory_id"]]
    events = service.omni.list_correction_events(correction["correction_id"])
    assert [event["event_type"] for event in events] == [
        "proposed", "approved", "applied", "succeeded",
    ]
    assert events[-1]["details"]["Authorization"] == "[REDACTED]"
    service.close()

    reopened = MemoryService(database)
    persisted = reopened.database.get_omni_record(correction["correction_id"], "correction")
    assert persisted["use_count"] == 1 and persisted["success_count"] == 1
    assert len(reopened.omni.list_correction_events(correction["correction_id"])) == 4
    reopened.close()


def test_trajectory_rejects_events_after_terminal_and_bad_references(tmp_path):
    service = MemoryService(tmp_path / "references.db")
    trajectory = _trajectory(service.omni)
    with pytest.raises(ValueError, match="memory reference"):
        service.omni.append_trajectory_event(
            trajectory["trajectory_id"], event_type="task_started", sequence=1,
            memory_ids=["missing-memory"],
        )
    service.omni.append_trajectory_event(
        trajectory["trajectory_id"], event_type="task_completed", sequence=1,
    )
    with pytest.raises(ValueError, match="terminal"):
        service.omni.append_trajectory_event(
            trajectory["trajectory_id"], event_type="tool_called", sequence=2,
        )
    service.close()
