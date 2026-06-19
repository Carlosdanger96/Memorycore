"""Memorycore Controller - Primary interface to CozoDB.

Simplified: Local-first memory substrate.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import cozo


# ============================================================================
# ENUMS (Simplified to 7 types, 4 statuses)
# ============================================================================

class MemoryType:
    FACT = "fact"
    DECISION = "decision"
    CORRECTION = "correction"
    PROCEDURE = "procedure"
    SOURCE = "source"
    TASK_RESULT = "task_result"
    PREFERENCE = "preference"

    @classmethod
    def values(cls):
        return [cls.FACT, cls.DECISION, cls.CORRECTION, cls.PROCEDURE,
                cls.SOURCE, cls.TASK_RESULT, cls.PREFERENCE]


class MemoryStatus:
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    STALE = "stale"
    ARCHIVED = "archived"

    @classmethod
    def values(cls):
        return [cls.ACTIVE, cls.SUPERSEDED, cls.STALE, cls.ARCHIVED]


class LinkType:
    RELATED = "related"
    DERIVED = "derived"
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    REFERENCES = "references"
    DEPENDS_ON = "depends_on"
