"""Deterministic candidate detection shared by storage adapters."""

import re
from collections.abc import Iterable, Mapping
from typing import Any


def find_candidates(rows: Iterable[Mapping[str, Any]], content: str) -> list[dict[str, Any]]:
    normalized = " ".join(content.casefold().split())
    tokens = set(re.findall(r"\w+", normalized))
    matches = []
    for row in rows:
        candidate = " ".join(str(row["content"]).casefold().split())
        if candidate == normalized:
            matches.append({"memory_id": row["id"], "reason": "exact", "score": 1.0})
            continue
        other = set(re.findall(r"\w+", candidate))
        if min(len(tokens), len(other)) < 4:
            continue
        overlap = len(tokens & other) / len(tokens | other)
        if overlap >= 0.8:
            matches.append({"memory_id": row["id"], "reason": "probable",
                            "score": round(overlap, 4)})
    return sorted(matches, key=lambda item: (-item["score"], item["memory_id"]))
