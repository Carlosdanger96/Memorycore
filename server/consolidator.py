"""Memorycore Consolidator - Perplexity-inspired memory card creation.

Turns raw conversations, task logs, and source notes into durable memory cards.

Workflow:
1. Extract useful memory from raw input
2. Classify type (fact, decision, correction, procedure, source, task_result, preference)
3. Generate summary
4. Create memory card
5. Link evidence
6. Mark old memories as superseded if needed
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
import re

from server.controller import MemoryController, MemoryType, MemoryStatus


@dataclass
class ConsolidationResult:
    memory: MemoryController.MemoryRecord
    superseded_ids: List[str]
    evidence_links: List[str]


class MemoryConsolidator:
    """Consolidates raw input into memory cards."""

    def __init__(self, controller: MemoryController):
        self.controller = controller
        self.classification_keywords = {
            MemoryType.DECISION: ['decide', 'chose', 'selected', 'decision', 'go with',
                                'pick', 'opt for', 'settle on', 'choose'],
            MemoryType.CORRECTION: ['fix', 'correction', 'wrong', 'error', 'mistake',
                                   'bug', 'incorrect', 'should be', 'was wrong'],
            MemoryType.PROCEDURE: ['step', 'procedure', 'how to', 'process', 'method',
                                  'instructions', 'recipe', 'algorithm', 'workflow'],
            MemoryType.SOURCE: ['source', 'from', 'reference', 'link', 'url', 'citation',
                               'according', 'see', 'documentation'],
            MemoryType.TASK_RESULT: ['result', 'outcome', 'succeeded', 'failed', 'completed',
                                     'finished', 'success', 'failure', 'tried', 'attempted'],
            MemoryType.PREFERENCE: ['prefer', 'like', 'want', 'setting', 'config',
                                    'configuration', 'preference', 'favorite'],
        }

    def consolidate(self, raw_input: str, project_id: str,
                   source_ref: str, created_by: str = "system") -> ConsolidationResult:
        """Main consolidation entry point."""
        memory_type = self._classify_memory_type(raw_input)
        summary = self._generate_summary(raw_input)
        tags = self._extract_tags(raw_input)

        memory = self.controller.add_memory(
            project_id=project_id,
            content=raw_input,
            memory_type=memory_type,
            summary=summary,
            evidence=[source_ref],
            created_by=created_by,
            tags=tags
        )

        superseded_ids = self._find_superseded_memories(
            project_id, memory_type, summary, raw_input
        )

        for old_id in superseded_ids:
            self.controller.update_memory(old_id, status=MemoryStatus.SUPERSEDED)

        return ConsolidationResult(
            memory=memory,
            superseded_ids=superseded_ids,
            evidence_links=[source_ref]
        )

    def _classify_memory_type(self, text: str) -> str:
        """Classify raw input into one of 7 memory types."""
        text_lower = text.lower()

        for mem_type, keywords in self.classification_keywords.items():
            if any(kw in text_lower for kw in keywords):
                return mem_type

        return MemoryType.FACT

    def _generate_summary(self, text: str, max_length: int = 200) -> str:
        """Generate a concise summary."""
        if not text:
            return ""
        sentences = [s.strip() for s in text.split('.') if s.strip()]
        if sentences:
            summary = sentences[0]
            if len(summary) <= max_length:
                return summary
        return text[:max_length].rsplit(' ', 1)[0] + "..." if len(text) > max_length else text

    def _extract_tags(self, text: str) -> List[str]:
        """Extract tags from text."""
        tags = set()
        hashtags = re.findall(r'#(w+)', text)
        tags.update(hashtags)
        return list(tags)

    def _find_superseded_memories(self, project_id: str, memory_type: str,
                                  summary: str, raw_input: str) -> List[str]:
        """Find memories that should be superseded."""
        existing = self.controller.search_memories(
            project_id=project_id,
            memory_type=memory_type,
            query=summary,
            limit=20
        )

        superseded = []
        for mem in existing:
            if mem.memory_id is None:
                continue
            if mem.status in [MemoryStatus.SUPERSEDED, MemoryStatus.ARCHIVED]:
                continue
            if (summary.lower() in mem.summary.lower() or
                mem.summary.lower() in summary.lower() or
                summary.lower() in mem.content.lower() or
                mem.content.lower() in summary.lower()):
                superseded.append(mem.memory_id)
        return superseded

    def consolidate_batch(self, items: List[Dict[str, str]]) -> List[ConsolidationResult]:
        """Consolidate multiple raw inputs."""
        results = []
        for item in items:
            result = self.consolidate(
                raw_input=item['raw_input'],
                project_id=item['project_id'],
                source_ref=item['source_ref'],
                created_by=item.get('created_by', 'system')
            )
            results.append(result)
        return results
