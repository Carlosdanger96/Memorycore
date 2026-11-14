from memorycore import MemoryService


def test_audit_approval_preserves_originals_and_projection_is_idempotent(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    service = MemoryService(tmp_path / "audit.db", vault_roots=[vault])
    first = service.add_memory(
        project_id="p", memory_type="procedure", content="Verification is optional.",
        metadata={"claim_key": "verification"}, tags=["policy"],
    )
    second = service.add_memory(
        project_id="p", memory_type="procedure", content="Verification is required.",
        metadata={"claim_key": "verification"}, tags=["policy"],
    )
    finding = service.omni.audit_memories(project_id="p")[0]
    assert finding["finding_type"] == "contradiction"
    approved = service.omni.approve_revision(finding["finding_id"], approved_by="reviewer")
    assert approved["status"] == "approved"
    assert service.get_memory(first.id) is not None and service.get_memory(second.id) is not None
    original = service.get_memory(first.id)
    other = service.get_memory(second.id)
    assert {original.status, other.status} <= {"superseded", "archived"}
    projected = service.omni.project_obsidian(vault, project_id="p")
    repeated = service.omni.project_obsidian(vault, project_id="p")
    assert projected["written"] and repeated["written"] == []
    dashboard = vault / "90_LLM_Exchange" / "Omni Memory Harness" / "Dashboard.md"
    assert "canonical_source" in dashboard.read_text(encoding="utf-8")
    service.close()
