from __future__ import annotations

import re
from typing import Any


_SECRET_KEY = re.compile(
    r"authorization|api[_-]?key|password|passwd|cookie|secret|token", re.IGNORECASE,
)
_SECRET_VALUE = re.compile(
    r"(?i)(bearer\s+)[a-z0-9._~+/-]{8,}|(sk-[a-z0-9_-]{8,})|"
    r"((?:api[_-]?key|password|token|secret)\s*[:=]\s*)\S+"
)


def redact(value: Any) -> Any:
    """Recursively remove common credential keys and inline secret values."""
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _SECRET_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _SECRET_VALUE.sub(
            lambda match: (match.group(1) or match.group(3) or "") + "[REDACTED]",
            value,
        )
    return value


def bounded_redact(value: Any, *, max_string: int = 4000, max_items: int = 100) -> Any:
    """Redact and cap provider-bound structures without cutting serialized JSON."""
    value = redact(value)
    if isinstance(value, dict):
        return {
            str(key)[:200]: bounded_redact(item, max_string=max_string, max_items=max_items)
            for key, item in list(value.items())[:max_items]
        }
    if isinstance(value, list):
        return [
            bounded_redact(item, max_string=max_string, max_items=max_items)
            for item in value[:max_items]
        ]
    if isinstance(value, str):
        return value[:max_string]
    return value
