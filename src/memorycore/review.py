"""Bounded automated review against operator-controlled source decisions.

This verifies exact records, not semantic inferences. The source manifest is
configured by the service operator and is never supplied by an MCP caller.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .database import SQLiteDatabase
from .models import ClientRole, Memory
from .policy import ClientPolicy, MemoryAccessError, RevisionConflictError

if TYPE_CHECKING:
    from .memory_service import MemoryService


def content_sha256(content: str) -> str:
    """Hash exact UTF-8 content; duplicate normalization is not review evidence."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _load_sources() -> tuple[list[dict[str, Any]], str]:
    configured = os.getenv("MEMORYCORE_REVIEW_SOURCES_FILE")
    if not configured:
        raise ValueError("automated review requires MEMORYCORE_REVIEW_SOURCES_FILE")
    with Path(configured).expanduser().open("rb") as handle:
        raw = handle.read(1_048_577)
    if len(raw) > 1_048_576:
        raise ValueError("review source manifest exceeds 1 MiB")
    document = json.loads(raw)
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("review source manifest requires schema_version 1")
    decisions = document.get("decisions")
    if not isinstance(decisions, list):
        raise ValueError("review source manifest requires a decisions list")
    seen = set()
    for entry in decisions:
        required = ("project_id", "memory_type", "content", "source_type", "source_uri", "source_id")
        if not isinstance(entry, dict) or any(
            not isinstance(entry.get(key), str) or not entry[key].strip() for key in required
        ):
            raise ValueError("each trusted decision requires project, type, content and source identity")
        key = tuple(entry[field] for field in ("project_id", "source_type", "source_uri", "source_id"))
        if key in seen:
            raise ValueError("ambiguous source identity in review manifest")
        seen.add(key)
        replacement = entry.get("supersedes")
        if replacement is not None and (
            not isinstance(replacement, dict)
            or not isinstance(replacement.get("memory_id"), str)
            or not replacement["memory_id"]
            or type(replacement.get("revision")) is not int
            or replacement["revision"] < 0
        ):
            raise ValueError("supersedes requires memory_id and a nonnegative revision")
    return decisions, hashlib.sha256(raw).hexdigest()


def _evaluate(memory: Memory, decisions: list[dict[str, Any]]) -> dict[str, Any]:
    identity = ("project_id", "source_type", "source_uri", "source_id")
    entry = next((item for item in decisions if all(
        getattr(memory, key) == item[key] for key in identity
    )), None)
    if entry is None or memory.source_type == "llm_inference":
        return {"verdict": "needs_validation", "reason": "no trusted source decision"}
    # Also verify fields that affect displayed context or retrieval ranking.
    defaults: dict[str, Any] = {"summary": None, "tags": [], "metadata": {}, "confidence": None}
    fields = ("memory_type", "content", *defaults)
    mismatches = [key for key in fields if getattr(memory, key) != entry.get(key, defaults.get(key))]
    if mismatches:
        return {"verdict": "rejected", "reason": "source decision mismatch", "fields": mismatches}
    return {"verdict": "confirmed", "reason": "exact trusted source decision",
            "supersedes": entry.get("supersedes")}


def review_candidate(service: MemoryService, policy: ClientPolicy, memory_id: str, *,
                     expected_revision: int, expected_content_sha256: str) -> dict[str, Any]:
    policy.require_role(ClientRole.APPROVER, ClientRole.ADMINISTRATOR)
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("expected_revision must be a nonnegative integer")
    database = service.database
    if not isinstance(database, SQLiteDatabase):
        raise ValueError("source-backed automated review currently requires SQLite")
    memory = service.get_memory(memory_id)
    if memory is None:
        raise ValueError("memory not found")
    policy.check_project(memory.project_id)
    if memory.client_id == policy.client_id:
        raise MemoryAccessError("a client cannot review its own memory")
    decisions, source_digest = _load_sources()
    request = {"memory_id": memory_id, "expected_revision": expected_revision,
               "content_sha256": expected_content_sha256, "source_manifest_sha256": source_digest,
               "reviewer": policy.client_id}
    event_id = "review-" + content_sha256(json.dumps(request, sort_keys=True))
    previous = database.get_event(event_id)
    if previous is not None:
        return {**previous["details"], "memory": memory.to_dict(), "replayed": True}
    if memory.revision != expected_revision:
        raise RevisionConflictError(memory_id, memory.revision, expected_revision)
    if content_sha256(memory.content) != expected_content_sha256:
        raise ValueError("candidate content hash does not match reviewed content")
    if memory.status != "pending":
        raise ValueError("only pending candidates can be reviewed")
    outcome = _evaluate(memory, decisions)
    target = outcome.get("supersedes")
    if target is not None:
        original = service.get_memory(target["memory_id"])
        if original is None or original.id == memory.id:
            raise ValueError("superseded memory must be a distinct existing record")
        policy.check_project(original.project_id)
        if original.project_id != memory.project_id or original.memory_type != memory.memory_type:
            raise ValueError("replacement must stay within the same project and memory type")
    new_state = {"confirmed": "active", "rejected": "rejected"}.get(outcome["verdict"], "pending")
    event = service._event(memory_id=memory.id, project_id=memory.project_id,
        event_type="memory_reviewed", client_id=policy.client_id,
        previous_state="pending", new_state=new_state,
        details={**request, **outcome, "source_uri": memory.source_uri, "source_id": memory.source_id})
    event["id"] = event_id
    # Recheck the complete candidate snapshot under the database write lock.
    # Candidate validation cannot authorize a different revision or payload.
    applied = database.apply_review(memory, event, supersedes=target)
    return {**applied["details"], "memory": service.get_memory(memory_id).to_dict(),
            "replayed": applied["replayed"]}
