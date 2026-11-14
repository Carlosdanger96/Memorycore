from __future__ import annotations

from abc import ABC, abstractmethod
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..omni_security import bounded_redact


class CorrectionProvider(ABC):
    model: str
    prompt_version = "omni-correction-v1"

    @abstractmethod
    def extract(self, failed: dict[str, Any], successful: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError


class DeterministicCorrectionProvider(CorrectionProvider):
    model = "deterministic-correction-v1"

    def extract(self, failed: dict[str, Any], successful: dict[str, Any] | None = None) -> dict[str, Any]:
        events = failed.get("events", [])
        behaviors = sorted({item for event in events for item in event.get("behavior_ids", [])})
        failed_behavior = "agent.output.verify" if "agent.output.verify" in behaviors else (behaviors[-1] if behaviors else "agent.output.verify")
        return {
            "task_type": failed["task_type"], "behavior_ids": [failed_behavior],
            "repository": failed["repository"],
            "trigger": {"error_signature": failed.get("error_signature"), "behavior_id": failed_behavior},
            "error_signature": failed.get("error_signature"), "operation": "require_verification",
            "instruction": "Verify relevant tool output and its success state before continuing execution.",
            "confidence": 0.82, "evidence_event_ids": [event["event_id"] for event in events[-3:]],
        }


class OpenAIResponsesCorrectionProvider(CorrectionProvider):
    prompt_version = "omni-correction-gpt56-v1"

    def __init__(self, api_key: str, *, model: str = "gpt-5.6",
                 base_url: str = "https://api.openai.com/v1", timeout: float = 60.0) -> None:
        if not api_key.strip():
            raise ValueError("OpenAI API key is required")
        self.api_key, self.model = api_key.strip(), model
        self.base_url, self.timeout = base_url.rstrip("/"), timeout

    @classmethod
    def from_environment(cls) -> OpenAIResponsesCorrectionProvider:
        return cls(
            os.getenv("OPENAI_API_KEY", ""),
            model=os.getenv("MEMORYCORE_CORRECTION_MODEL", "gpt-5.6"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )

    def extract(self, failed: dict[str, Any], successful: dict[str, Any] | None = None) -> dict[str, Any]:
        safe_failed = self._safe_trajectory(failed)
        safe_successful = self._safe_trajectory(successful) if successful else None
        provider_input = {"failed_trajectory": safe_failed, "successful_comparison": safe_successful}
        while (safe_successful and safe_successful["events"] and
               len(json.dumps(provider_input, ensure_ascii=False)) > 100_000):
            safe_successful["events"].pop()
        while safe_failed["events"] and len(json.dumps(provider_input, ensure_ascii=False)) > 100_000:
            safe_failed["events"].pop(0)
        payload = {
            "model": self.model, "store": False,
            "instructions": (
                "Extract one operational, reusable correction from a failed agent trajectory. "
                "Use only the supported operation enum. Cite evidence event IDs. Do not return "
                "free-form reflection or invent events."
            ),
            "input": json.dumps(provider_input, ensure_ascii=False),
            "text": {"format": {"type": "json_schema", "name": "experience_correction",
                                 "strict": True, "schema": _CORRECTION_SCHEMA}},
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
            raise RuntimeError(f"OpenAI correction request failed with HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError("OpenAI correction request could not reach the configured API") from exc
        text = raw.get("output_text") or self._output_text(raw)
        if not text:
            raise RuntimeError("OpenAI correction response did not contain output text")
        return json.loads(text)

    @staticmethod
    def _safe_trajectory(trajectory: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "trajectory_id": trajectory.get("trajectory_id"),
            "project_id": trajectory.get("project_id"),
            "task_type": trajectory.get("task_type"),
            "task_description": trajectory.get("task_description"),
            "agent_id": trajectory.get("agent_id"),
            "repository": trajectory.get("repository"),
            "source_revision": trajectory.get("source_revision"),
            "outcome": trajectory.get("outcome"),
            "reward": trajectory.get("reward"),
            "error_signature": trajectory.get("error_signature"),
            "events": [{
                key: event.get(key)
                for key in (
                    "event_id", "sequence", "event_type", "behavior_ids", "memory_ids",
                    "correction_ids", "tool_name", "redacted_input", "redacted_output",
                    "error_signature", "outcome",
                )
            } for event in trajectory.get("events", [])[:500]],
        }
        return bounded_redact(allowed, max_string=4000, max_items=500)

    @staticmethod
    def _output_text(response: dict[str, Any]) -> str | None:
        for item in response.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return content.get("text")
        return None


_CORRECTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "task_type": {"type": "string"},
        "behavior_ids": {"type": "array", "items": {"type": "string"}},
        "repository": {"type": "string"},
        "trigger": {
            "type": "object",
            "properties": {"error_signature": {"type": ["string", "null"]}, "behavior_id": {"type": ["string", "null"]}},
            "required": ["error_signature", "behavior_id"], "additionalProperties": False,
        },
        "error_signature": {"type": ["string", "null"]},
        "operation": {"type": "string", "enum": [
            "add_step", "replace_step", "change_tool", "expand_search",
            "require_verification", "escalate_approval",
        ]},
        "instruction": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "evidence_event_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "task_type", "behavior_ids", "repository", "trigger", "error_signature",
        "operation", "instruction", "confidence", "evidence_event_ids",
    ],
    "additionalProperties": False,
}
