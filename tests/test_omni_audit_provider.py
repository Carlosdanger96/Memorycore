import json

from memorycore.audit import OpenAIResponsesAuditProvider
from memorycore.experience import OpenAIResponsesCorrectionProvider


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return json.dumps(self.payload).encode()


def test_openai_provider_uses_responses_structured_output(monkeypatch):
    captured = {}
    finding = {
        "finding_type": "contradiction",
        "affected_memory_ids": ["a", "b"],
        "affected_correction_ids": [],
        "explanation": "Values conflict.",
        "evidence": [{"memory_id": "a", "content": "old"}, {"memory_id": "b", "content": "new"}],
        "recommended_action": "supersede",
        "proposed_record": {"content": "new", "summary": None, "tags": ["audited"]},
        "confidence": 0.95,
    }

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data)
        captured["authorization"] = request.headers["Authorization"]
        return _Response({"output_text": json.dumps({"findings": [finding]})})

    monkeypatch.setattr("memorycore.audit.providers.urlopen", fake_urlopen)
    provider = OpenAIResponsesAuditProvider("secret-key", model="gpt-5.6")
    result = provider.find([
        {"id": "a", "memory_type": "fact", "content": "old", "summary": None,
         "tags": [], "confidence": 0.5, "source_type": "manual_import",
         "source_uri": "file:///private/secret-path", "metadata": {
             "claim_key": "policy", "api_token": "must-not-leak", "untrusted": "drop-me",
         }, "created_at": "1", "updated_at": "1"},
        {"id": "b", "memory_type": "fact", "content": "new", "summary": None,
         "tags": [], "confidence": 0.9, "source_type": "manual_import", "source_uri": None,
         "metadata": {}, "created_at": "2", "updated_at": "2"},
    ])
    assert result == [finding]
    assert captured["payload"]["model"] == "gpt-5.6"
    assert captured["payload"]["store"] is False
    assert captured["payload"]["text"]["format"]["type"] == "json_schema"
    assert captured["payload"]["text"]["format"]["strict"] is True
    assert captured["authorization"] == "Bearer secret-key"
    provider_input = captured["payload"]["input"]
    assert "must-not-leak" not in provider_input
    assert "secret-path" not in provider_input
    assert "untrusted" not in provider_input


def test_correction_provider_sends_only_bounded_redacted_trajectory(monkeypatch):
    captured = {}
    proposal = {
        "task_type": "repository_modification",
        "behavior_ids": ["agent.output.verify"],
        "repository": "repo",
        "trigger": {"error_signature": "err:1", "behavior_id": "agent.output.verify"},
        "error_signature": "err:1",
        "operation": "require_verification",
        "instruction": "Verify the tool result.",
        "confidence": 0.9,
        "evidence_event_ids": ["event-1"],
    }

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data)
        return _Response({"output_text": json.dumps(proposal)})

    monkeypatch.setattr("memorycore.experience.providers.urlopen", fake_urlopen)
    provider = OpenAIResponsesCorrectionProvider("secret-key", model="gpt-5.6")
    result = provider.extract({
        "trajectory_id": "traj-1", "project_id": "p",
        "task_type": "repository_modification", "task_description": "test",
        "agent_id": "agent", "repository": "repo", "source_revision": "abc",
        "outcome": "failed", "reward": 0, "error_signature": "err:1",
        "provenance": {"api_key": "provider-secret-must-not-leak"},
        "metadata": {"password": "metadata-secret-must-not-leak"},
        "events": [{
            "event_id": "event-1", "sequence": 1, "event_type": "task_failed",
            "behavior_ids": ["agent.output.verify"], "memory_ids": [],
            "correction_ids": [], "tool_name": "tool",
            "redacted_input": {"Authorization": "Bearer runtime-secret-value"},
            "redacted_output": {"ok": False}, "error_signature": "err:1",
            "outcome": "failed", "metadata": {"cookie": "hidden"},
        }],
    })
    assert result == proposal
    provider_input = captured["payload"]["input"]
    assert "provider-secret-must-not-leak" not in provider_input
    assert "metadata-secret-must-not-leak" not in provider_input
    assert "runtime-secret-value" not in provider_input
    assert "provenance" not in provider_input and '"metadata"' not in provider_input
