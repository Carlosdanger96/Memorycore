from __future__ import annotations

from abc import ABC, abstractmethod
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class AuditProvider(ABC):
    model: str
    prompt_version = "omni-audit-v1"

    @abstractmethod
    def find(self, memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
        raise NotImplementedError


class DeterministicAuditProvider(AuditProvider):
    model = "deterministic-auditor-v1"

    def find(self, memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for index, first in enumerate(memories):
            for second in memories[index + 1:]:
                key_a = first.get("metadata", {}).get("claim_key")
                key_b = second.get("metadata", {}).get("claim_key")
                same_claim = bool(key_a and key_a == key_b)
                same_content = first["content"].strip().casefold() == second["content"].strip().casefold()
                if not same_claim and not same_content:
                    continue
                finding_type = "duplicate" if same_content else "contradiction"
                preferred = second if second["created_at"] >= first["created_at"] else first
                findings.append({
                    "finding_type": finding_type,
                    "affected_memory_ids": [first["id"], second["id"]],
                    "affected_correction_ids": [],
                    "explanation": (
                        f"Active memories share claim scope {key_a!r} but contain incompatible values."
                        if finding_type == "contradiction"
                        else "Active memories contain the same normalized content."
                    ),
                    "evidence": [
                        {"memory_id": first["id"], "content": first["content"]},
                        {"memory_id": second["id"], "content": second["content"]},
                    ],
                    "recommended_action": "supersede" if finding_type == "contradiction" else "consolidate",
                    "proposed_record": {
                        "content": preferred["content"],
                        "summary": "Governed consolidation proposal",
                        "tags": sorted(set(first.get("tags", []) + second.get("tags", []) + ["audited"])),
                    },
                    "confidence": 0.97 if same_claim else 0.99,
                })
        return findings


class OpenAIResponsesAuditProvider(AuditProvider):
    """Strict structured-output provider for optional live GPT-5.6 audits."""

    prompt_version = "omni-audit-gpt56-v1"

    def __init__(self, api_key: str, *, model: str = "gpt-5.6",
                 base_url: str = "https://api.openai.com/v1", timeout: float = 60.0) -> None:
        if not api_key.strip():
            raise ValueError("OpenAI API key is required")
        self.api_key = api_key.strip()
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @classmethod
    def from_environment(cls) -> OpenAIResponsesAuditProvider:
        api_key = os.getenv("OPENAI_API_KEY", "")
        return cls(
            api_key, model=os.getenv("MEMORYCORE_AUDIT_MODEL", "gpt-5.6"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )

    def find(self, memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
        safe_memories = [{
            "id": item["id"], "memory_type": item["memory_type"],
            "content": item["content"][:4000], "summary": item.get("summary"),
            "tags": item.get("tags", []), "confidence": item.get("confidence"),
            "source_type": item.get("source_type"), "source_uri": item.get("source_uri"),
            "metadata": item.get("metadata", {}), "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        } for item in memories[:100]]
        payload = {
            "model": self.model,
            "store": False,
            "instructions": (
                "Audit governed agent memories. Return only evidence-supported findings. "
                "Never rewrite records. Prefer no finding over speculation. A contradiction "
                "requires two claims with the same scope and incompatible values. Proposed "
                "records must preserve the best-supported content and remain reviewable."
            ),
            "input": json.dumps({"memories": safe_memories}, ensure_ascii=False),
            "text": {"format": {
                "type": "json_schema", "name": "omni_memory_audit", "strict": True,
                "schema": _AUDIT_SCHEMA,
            }},
        }
        request = Request(
            f"{self.base_url}/responses", data=json.dumps(payload).encode(), method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = json.load(response)
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode()).get("error", {}).get("message", "request failed")
            except Exception:
                detail = "request failed"
            raise RuntimeError(f"OpenAI audit request failed with HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError("OpenAI audit request could not reach the configured API") from exc
        text = raw.get("output_text") or self._output_text(raw)
        if not text:
            raise RuntimeError("OpenAI audit response did not contain output text")
        parsed = json.loads(text)
        findings = parsed.get("findings")
        if not isinstance(findings, list):
            raise RuntimeError("OpenAI audit response did not match the required schema")
        return findings

    @staticmethod
    def _output_text(response: dict[str, Any]) -> str | None:
        for item in response.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    return content["text"]
        return None


_FINDING_TYPES = [
    "duplicate", "contradiction", "supersession", "stale", "unsupported_claim",
    "scope_mismatch", "provenance_gap", "consolidation_candidate",
]

_AUDIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "finding_type": {"type": "string", "enum": _FINDING_TYPES},
                    "affected_memory_ids": {"type": "array", "items": {"type": "string"}},
                    "affected_correction_ids": {"type": "array", "items": {"type": "string"}},
                    "explanation": {"type": "string"},
                    "evidence": {
                        "type": "array", "items": {
                            "type": "object",
                            "properties": {"memory_id": {"type": "string"}, "content": {"type": "string"}},
                            "required": ["memory_id", "content"], "additionalProperties": False,
                        },
                    },
                    "recommended_action": {"type": "string"},
                    "proposed_record": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"}, "summary": {"type": ["string", "null"]},
                            "tags": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["content", "summary", "tags"], "additionalProperties": False,
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": [
                    "finding_type", "affected_memory_ids", "affected_correction_ids", "explanation",
                    "evidence", "recommended_action", "proposed_record", "confidence",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["findings"],
    "additionalProperties": False,
}
