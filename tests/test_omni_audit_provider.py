import json

from memorycore.audit import OpenAIResponsesAuditProvider


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
         "tags": [], "confidence": 0.5, "source_type": "manual_import", "source_uri": None,
         "metadata": {}, "created_at": "1", "updated_at": "1"},
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
