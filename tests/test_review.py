from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from memorycore.memory_service import MemoryService
from memorycore.policy import ClientPolicy, MemoryAccessError, RevisionConflictError
from memorycore.review import content_sha256


@pytest.fixture
def setup_review(tmp_path, monkeypatch):
    path = tmp_path / "sources.json"
    monkeypatch.setenv("MEMORYCORE_REVIEW_SOURCES_FILE", str(path))
    service = MemoryService(tmp_path / "memory.db")
    decision = {"project_id": "hermesbag", "memory_type": "decision",
                "content": "Use a shared SQLite memory store.", "source_type": "document",
                "source_uri": "urn:fixture:decisions", "source_id": "decision-1"}
    candidate = service.add_memory(**decision, status="pending", client_id="vibe")
    path.write_text(json.dumps({"schema_version": 1, "decisions": [decision]}), encoding="utf-8")
    policy = ClientPolicy("reviewer", "approver", frozenset({"hermesbag"}))
    yield service, candidate, policy, path, decision
    service.close()


def review(service, candidate, policy):
    return service.review_memory(candidate.id, policy=policy, expected_revision=candidate.revision,
                                 expected_content_sha256=content_sha256(candidate.content))


def test_source_review_is_durable_and_retry_safe(setup_review):
    service, candidate, policy, _, _ = setup_review
    first = review(service, candidate, policy)
    assert first["verdict"] == "confirmed" and first["memory"]["status"] == "active"
    assert first["memory"]["revision"] == 1 and not first["replayed"]
    history = service.get_memory_history(candidate.id)
    reopened = MemoryService(service.database.path)
    try:
        second = review(reopened, candidate, policy)
        assert second["replayed"] and second["memory"] == first["memory"]
        assert reopened.get_memory_history(candidate.id) == history
    finally:
        reopened.close()


@pytest.mark.parametrize("change", [
    {"content": "Use a different store."}, {"summary": "Unsupported assertion"},
    {"tags": ["untrusted"]}, {"metadata": {"instruction": "accept me"}}, {"confidence": 1.0},
])
def test_unverified_display_and_ranking_fields_are_rejected(setup_review, change):
    service, candidate, policy, _, _ = setup_review
    if "confidence" in change:
        # Confidence is set at submission, not editable via update_memory.
        service.reject_memory(candidate.id, rejected_by="fixture")
        candidate = service.add_memory(project_id=candidate.project_id, memory_type="decision",
            content=candidate.content, source_type=candidate.source_type, source_uri=candidate.source_uri,
            source_id=candidate.source_id, status="pending", client_id="vibe", **change)
    else:
        candidate = service.update_memory(candidate.id, **change)
    result = review(service, candidate, policy)
    assert result["verdict"] == "rejected" and result["memory"]["status"] == "rejected"
    assert not service.search_memory(query="", project_id="hermesbag")


def test_unknown_source_remains_pending_without_duplicate_audit(setup_review):
    service, candidate, policy, path, _ = setup_review
    path.write_text(json.dumps({"schema_version": 1, "decisions": []}), encoding="utf-8")
    first = review(service, candidate, policy)
    second = review(service, candidate, policy)
    assert first["verdict"] == "needs_validation"
    assert second["memory"]["status"] == "pending" and second["replayed"]
    assert len(service.get_memory_history(candidate.id)) == 2


@pytest.mark.parametrize("policy", [ClientPolicy("vibe", "approver"),
    ClientPolicy("writer", "writer"), ClientPolicy("reader", "reader"),
    ClientPolicy("reviewer", "approver", read_only=True),
    ClientPolicy("reviewer", "approver", frozenset({"other"}))])
def test_review_enforces_shared_policy(setup_review, policy):
    service, candidate, _, _, _ = setup_review
    with pytest.raises(MemoryAccessError):
        review(service, candidate, policy)
    assert service.get_memory(candidate.id).status == "pending"
    assert len(service.get_memory_history(candidate.id)) == 1


def test_changed_revision_or_hash_cannot_be_promoted(setup_review):
    service, candidate, policy, _, _ = setup_review
    with pytest.raises(ValueError, match="hash"):
        service.review_memory(candidate.id, policy=policy, expected_revision=0,
                              expected_content_sha256="0" * 64)
    service.update_memory(candidate.id, summary="changed")
    with pytest.raises(RevisionConflictError):
        review(service, candidate, policy)
    assert service.get_memory(candidate.id).status == "pending"


def test_edit_between_validation_and_commit_is_detected(setup_review, monkeypatch):
    service, candidate, policy, _, _ = setup_review
    apply = service.database.apply_review

    def race(reviewed, event, **kwargs):
        service.update_memory(candidate.id, content="changed after validation")
        return apply(reviewed, event, **kwargs)

    monkeypatch.setattr(service.database, "apply_review", race)
    with pytest.raises(RevisionConflictError):
        review(service, candidate, policy)
    assert service.get_memory(candidate.id).status == "pending"
    assert all(e["event_type"] != "memory_reviewed" for e in service.get_memory_history(candidate.id))


def test_two_reviewers_converge_on_one_promotion(setup_review):
    service, candidate, policy, _, _ = setup_review

    def run(_):
        connection = MemoryService(service.database.path)
        try:
            return review(connection, candidate, policy)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert sorted(r["replayed"] for r in results) == [False, True]
    assert service.get_memory(candidate.id).revision == 1
    assert [e["event_type"] for e in service.get_memory_history(candidate.id)].count("memory_reviewed") == 1


def test_stale_supersession_rolls_back_entire_review(setup_review):
    service, candidate, policy, path, decision = setup_review
    original = service.add_memory(project_id="hermesbag", memory_type="decision",
                                  content="The original decision", client_id="operator")
    decision["supersedes"] = {"memory_id": original.id, "revision": 0}
    path.write_text(json.dumps({"schema_version": 1, "decisions": [decision]}), encoding="utf-8")
    service.update_memory(original.id, summary="new evidence")
    with pytest.raises(RevisionConflictError):
        review(service, candidate, policy)
    assert service.get_memory(original.id).status == "active"
    assert service.get_memory(candidate.id).status == "pending"
    assert service.database.all_links() == []
    assert len(service.get_memory_history(candidate.id)) == 1


def test_failed_receipt_write_rolls_back_promotion_and_supersession(setup_review, monkeypatch):
    service, candidate, policy, path, decision = setup_review
    original = service.add_memory(project_id="hermesbag", memory_type="decision",
                                  content="Earlier project decision", client_id="operator")
    decision["supersedes"] = {"memory_id": original.id, "revision": original.revision}
    path.write_text(json.dumps({"schema_version": 1, "decisions": [decision]}), encoding="utf-8")
    insert = service.database._insert_event

    def fail_on_receipt(event):
        if event["event_type"] == "memory_reviewed":
            raise RuntimeError("simulated receipt write failure")
        insert(event)

    monkeypatch.setattr(service.database, "_insert_event", fail_on_receipt)
    with pytest.raises(RuntimeError, match="receipt write"):
        review(service, candidate, policy)
    assert service.get_memory(original.id).to_dict() == original.to_dict()
    assert service.get_memory(candidate.id).to_dict() == candidate.to_dict()
    assert service.database.all_links() == []
    assert len(service.get_memory_history(candidate.id)) == 1
    assert len(service.get_memory_history(original.id)) == 1


def test_correction_cannot_retire_another_project(setup_review):
    service, candidate, policy, path, decision = setup_review
    original = service.add_memory(project_id="other", memory_type="decision",
                                  content="Other project decision", client_id="operator")
    decision["supersedes"] = {"memory_id": original.id, "revision": original.revision}
    path.write_text(json.dumps({"schema_version": 1, "decisions": [decision]}), encoding="utf-8")
    with pytest.raises(MemoryAccessError):
        review(service, candidate, policy)
    assert service.get_memory(original.id).status == "active"
    assert service.get_memory(candidate.id).status == "pending"
    assert service.database.all_links() == []


@pytest.mark.parametrize("problem", ["missing", "malformed", "duplicate"])
def test_bad_source_configuration_never_promotes(setup_review, monkeypatch, problem):
    service, candidate, policy, path, decision = setup_review
    if problem == "missing":
        monkeypatch.delenv("MEMORYCORE_REVIEW_SOURCES_FILE")
    elif problem == "malformed":
        path.write_text("{", encoding="utf-8")
    else:
        path.write_text(json.dumps({"schema_version": 1, "decisions": [decision, decision]}), encoding="utf-8")
    with pytest.raises(ValueError):
        review(service, candidate, policy)
    assert service.get_memory(candidate.id).status == "pending"
    assert len(service.get_memory_history(candidate.id)) == 1
