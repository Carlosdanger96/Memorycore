import pytest

from memorycore import (
    CorrectionOperation,
    CorrectionOutcome,
    ExperienceCorrection,
    ExperienceCorrectionLedger,
    MemoryService,
)


def test_capture_retrieve_and_record_outcome(tmp_path):
    service = MemoryService(tmp_path / "memory.db")
    ledger = ExperienceCorrectionLedger(service)
    correction = ledger.capture(
        project_id="omni-core",
        correction=ExperienceCorrection(
            task_type="obsidian_note_write",
            trigger="A requested project note may already exist",
            failed_behavior="Created a duplicate note after exact-title-only lookup",
            operation=CorrectionOperation.EXPAND_SEARCH.value,
            instruction="Search title, aliases, path and backlinks before creating a note",
            tools=("obsidian-rest",),
            repositories=("markdown-memory",),
            applicability=("create_note", "update_note"),
            evidence="Retry updated the canonical note without creating another file",
        ),
        created_by="hermes",
        client_id="hermes",
        confidence=0.94,
        status="active",
    )

    assert correction.memory_type == "experience_correction"
    assert correction.metadata["schema"] == "memorycore.experience_correction.v1"
    assert correction.metadata["reuse"]["attempts"] == 0

    retrieved = ledger.retrieve(
        project_id="omni-core",
        task_type="obsidian_note_write",
        query="canonical note",
        tools=("obsidian-rest",),
        repositories=("markdown-memory",),
        minimum_confidence=0.8,
    )
    assert [item.id for item in retrieved] == [correction.id]

    updated = ledger.record_outcome(
        correction.id,
        outcome=CorrectionOutcome.SUCCEEDED.value,
        updated_by="hermes",
        evidence="Canonical note updated",
    )
    assert updated.metadata["reuse"] == {
        "attempts": 1,
        "successes": 1,
        "failures": 0,
        "last_outcome": "succeeded",
        "last_evidence": "Canonical note updated",
    }
    service.close()


def test_retrieval_respects_scope_and_confidence(tmp_path):
    service = MemoryService(tmp_path / "memory.db")
    ledger = ExperienceCorrectionLedger(service)
    ledger.capture(
        project_id="alpha",
        correction=ExperienceCorrection(
            task_type="deploy",
            trigger="Deployment requested",
            failed_behavior="Skipped tests",
            operation="require_verification",
            instruction="Run the repository test suite before deployment",
            repositories=("alpha-repo",),
        ),
        confidence=0.6,
        status="active",
    )

    assert ledger.retrieve(
        project_id="alpha",
        task_type="deploy",
        repositories=("different-repo",),
    ) == []
    assert ledger.retrieve(
        project_id="alpha",
        task_type="deploy",
        repositories=("alpha-repo",),
        minimum_confidence=0.8,
    ) == []
    service.close()


def test_invalid_operation_is_rejected(tmp_path):
    service = MemoryService(tmp_path / "memory.db")
    ledger = ExperienceCorrectionLedger(service)
    with pytest.raises(ValueError, match="operation must be one of"):
        ledger.capture(
            project_id="alpha",
            correction=ExperienceCorrection(
                task_type="task",
                trigger="trigger",
                failed_behavior="failure",
                operation="invent_a_graph_database",
                instruction="Do something dramatic",
            ),
        )
    service.close()
