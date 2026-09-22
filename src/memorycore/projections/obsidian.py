"""One-way Obsidian Markdown projection for ordinary shared memories.

The projection is generated from the canonical SQLite store and never mutates
canonical state. Editing or moving the generated Markdown changes nothing in
Memorycore. Adapted from the PR #11 projection writer patterns: allowed-root
checks, generated-file warnings, idempotent writes, and a provenance manifest.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..database import SQLiteDatabase
from ..models import MemoryStatus

_NOTICE = (
    "> Generated projection. Editing or moving this Markdown file does not "
    "mutate canonical Memorycore state."
)

_STATUS_DIRECTORIES = {
    "pending": "Pending",
    "active": "Active",
    "rejected": "Rejected",
    "archived": "Archived",
    "superseded": "Archived",
    "contradicted": "Archived",
}


class ObsidianProjection:
    def __init__(self, database: SQLiteDatabase, allowed_roots: list[str | Path]) -> None:
        self.database = database
        self.allowed_roots = tuple(Path(item).expanduser().resolve() for item in allowed_roots)
        if not self.allowed_roots:
            raise ValueError("Obsidian projection requires an explicit allowed vault root")

    def project(self, vault_root: str | Path, *, project_id: str) -> dict[str, Any]:
        vault = Path(vault_root).expanduser().resolve()
        if not any(
            vault == allowed or vault.is_relative_to(allowed) for allowed in self.allowed_roots
        ):
            raise ValueError("vault path is outside the configured allowed roots")
        root = vault / "90_Memorycore" / _safe(project_id)
        written, unchanged = [], []
        memories = [
            memory for memory in self.database.all_memories()
            if memory.project_id == project_id
        ]
        links = [link for link in self.database.all_links()
                 if any(link["from_memory_id"] == memory.id or link["to_memory_id"] == memory.id
                        for memory in memories)]
        memory_ids = {memory.id for memory in memories}
        for memory in memories:
            directory = _STATUS_DIRECTORIES.get(memory.status, "Active")
            path = root / directory / f"{_safe(memory.id)}.md"
            related = [link for link in links
                       if link["from_memory_id"] == memory.id or link["to_memory_id"] == memory.id]
            self._write(path, self._render_memory(memory, related, directory, memory_ids),
                        written, unchanged)
        self._write(root / "Dashboard.md", self._render_dashboard(project_id, memories),
                    written, unchanged)
        manifest = self._frontmatter("provenance", "projection-manifest", {
            "project_id": project_id,
            "status": "generated",
            "record_count": len(memories),
            "generated_at": _latest(memories),
        })
        manifest += "\n" + _NOTICE + "\n\n# Projection manifest\n\n"
        manifest += (
            f"- Project: `{project_id}`\n"
            f"- Memories: {len(memories)}\n"
            f"- Generated files: {len(written) + len(unchanged)}\n"
            "- Canonical source: Memorycore SQLite through MemoryService\n"
        )
        self._write(root / "Provenance" / "projection-manifest.md", manifest, written, unchanged)
        return {"root": str(root), "memory_count": len(memories),
                "written": sorted(written), "unchanged": sorted(unchanged)}

    def _render_memory(self, memory: Any, links: list[dict[str, Any]],
                       directory: str, memory_ids: set[str]) -> str:
        body = self._frontmatter("memory", memory.id, {
            "project_id": memory.project_id,
            "memory_type": memory.memory_type,
            "status": memory.status,
            "revision": memory.revision,
            "confidence": memory.confidence,
            "client_id": memory.client_id,
            "created_by": memory.created_by,
            "updated_by": memory.updated_by,
            "source_type": memory.source_type,
            "created_at": memory.created_at,
            "updated_at": memory.updated_at,
        })
        body += "\n" + _NOTICE + "\n\n"
        body += f"# {memory.summary or memory.content[:80]}\n\n"
        body += memory.content + "\n"
        if memory.tags:
            body += "\n" + "\n".join(f"- #{_safe(tag)}" for tag in memory.tags) + "\n"
        if links:
            body += "\n## Relations\n\n"
            for link in links:
                other = (link["to_memory_id"] if link["from_memory_id"] == memory.id
                         else link["from_memory_id"])
                target = f"../{_STATUS_DIRECTORIES.get('active', 'Active')}/{_safe(other)}.md"
                body += f"- {link['relation_type']}: [[{target}|{other}]]\n"
        events = self.database.list_events(memory.id, 500)
        if events:
            body += "\n## Audit history\n\n"
            for event in events:
                actor = event.get("client_id") or "system"
                transition = ""
                if event.get("previous_state") or event.get("new_state"):
                    transition = f" `{event.get('previous_state') or '∅'}` → `{event.get('new_state') or '∅'}`"
                body += f"- `{event['event_type']}` — {event['created_at']} — actor: `{actor}`{transition}\n"
        return body

    def _render_dashboard(self, project_id: str, memories: list[Any]) -> str:
        statuses: dict[str, int] = {}
        for memory in memories:
            statuses[memory.status] = statuses.get(memory.status, 0) + 1
        body = self._frontmatter("dashboard", f"{_safe(project_id)}-dashboard", {
            "project_id": project_id,
            "status": "generated",
            "record_count": len(memories),
            "generated_at": _latest(memories),
        })
        body += "\n" + _NOTICE + "\n\n"
        body += f"# Memorycore — {project_id}\n\n"
        body += f"- Total memories: **{len(memories)}**\n"
        for status in MemoryStatus:
            body += f"- {status.value}: **{statuses.get(status.value, 0)}**\n"
        body += "\n## Recent active memories\n\n"
        active = sorted((m for m in memories if m.status == "active"),
                        key=lambda m: m.updated_at, reverse=True)[:10]
        body += "\n".join(
            f"- [[{_STATUS_DIRECTORIES['active']}/{_safe(m.id)}.md|{m.summary or m.content[:60]}]]"
            for m in active
        ) or "- None"
        body += "\n"
        return body

    @staticmethod
    def _frontmatter(record_type: str, record_id: str, values: dict[str, Any]) -> str:
        fields = {
            "memorycore_type": record_type,
            "memorycore_id": record_id,
            "canonical_source": "memorycore",
            **values,
        }
        return "---\n" + "\n".join(
            f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in fields.items()
        ) + "\n---"

    @staticmethod
    def _write(path: Path, content: str, written: list[str], unchanged: list[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_text(encoding="utf-8") == content:
            unchanged.append(str(path))
            return
        path.write_text(content, encoding="utf-8")
        written.append(str(path))


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-")[:160] or "untitled"


def _latest(memories: list[Any]) -> str:
    return max((m.updated_at for m in memories), default="1970-01-01T00:00:00+00:00")
