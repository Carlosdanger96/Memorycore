from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)
_TYPE_WEIGHT = {"correction": 30, "decision": 25, "preference": 20, "fact": 15, "procedure": 10, "note": 5}


@dataclass(frozen=True, slots=True)
class RankedMemory:
    memory: Any
    score: float
    reasons: tuple[str, ...]


def build_fts_query(query: str) -> str:
    """Convert user text into a conservative FTS5 AND query."""
    tokens = _TOKEN_RE.findall(query.strip())
    return " AND ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)


def render_context(memories: list[dict[str, object]]) -> str:
    blocks: list[str] = []
    for item in memories:
        label = item.get("summary") or item.get("content")
        blocks.append(
            f"[{item.get('memory_type')}:{item.get('id')}] {label}\n"
            f"{item.get('content')}"
        )
    return "\n\n".join(blocks)


def rank_memories(query: str, memories: Iterable[Any], limit: int) -> list[RankedMemory]:
    """Rank already scoped candidates without any hidden model or embedding call."""
    normalized_query = _normalize(query)
    query_tokens = set(_TOKEN_RE.findall(normalized_query))
    ranked: list[RankedMemory] = []
    for memory in memories:
        content = _normalize(memory.content)
        summary = _normalize(memory.summary or "")
        tags = {_normalize(tag) for tag in memory.tags}
        score, reasons = 0.0, []
        if normalized_query and content == normalized_query:
            score += 1000
            reasons.append("exact_content_match")
        if normalized_query and summary == normalized_query:
            score += 700
            reasons.append("exact_summary_match")
        matched = query_tokens & set(_TOKEN_RE.findall(content + " " + summary))
        if matched:
            score += 100 * len(matched) / max(len(query_tokens), 1)
            reasons.append("content_terms:" + ",".join(sorted(matched)))
        matched_tags = query_tokens & tags
        if matched_tags:
            score += 40 * len(matched_tags)
            reasons.append("tag_match:" + ",".join(sorted(matched_tags)))
        type_weight = _TYPE_WEIGHT.get(memory.memory_type, 0)
        score += type_weight
        reasons.append("memory_type:" + memory.memory_type)
        if memory.confidence is not None:
            score += float(memory.confidence) * 10
            reasons.append("confidence")
        try:
            score += datetime.fromisoformat(memory.updated_at).timestamp() / 1e12
        except ValueError:
            pass
        ranked.append(RankedMemory(memory, score, tuple(reasons)))
    return sorted(ranked, key=lambda item: (-item.score, item.memory.id))[:limit]


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())
