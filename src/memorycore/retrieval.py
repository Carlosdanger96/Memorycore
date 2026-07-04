from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


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
