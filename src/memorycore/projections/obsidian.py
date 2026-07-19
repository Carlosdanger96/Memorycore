from __future__ import annotations

from collections import Counter
from pathlib import Path
import json
import re
from typing import Any

from ..database import SQLiteDatabase
from ..omni_models import OmniRecordType


_NOTICE = "> Generated projection. Editing or moving this Markdown file does not mutate canonical Memorycore state."


class ObsidianProjection:
    def __init__(self, database: SQLiteDatabase, allowed_roots: list[str | Path]) -> None:
        self.database = database
        self.allowed_roots = tuple(Path(item).expanduser().resolve() for item in allowed_roots)
        if not self.allowed_roots:
            raise ValueError("Obsidian projection requires an explicit allowed vault root")

    def project(self, vault_root: str | Path, *, project_id: str) -> dict[str, Any]:
        vault = Path(vault_root).expanduser().resolve()
        if not any(vault == allowed or vault.is_relative_to(allowed) for allowed in self.allowed_roots):
            raise ValueError("vault path is outside the configured allowed roots")
        root = vault / "90_LLM_Exchange" / "Omni Memory Harness"
        directories = [
            "Behaviors", "Trajectories", "Corrections/Inbox", "Corrections/Active",
            "Corrections/Rejected", "Corrections/Archived", "Conflicts", "Decisions", "Provenance",
        ]
        for directory in directories:
            (root / directory).mkdir(parents=True, exist_ok=True)
        written, unchanged = [], []
        behaviors = self.database.list_omni_records(OmniRecordType.BEHAVIOR.value, project_id, limit=10_000)
        trajectories = self.database.list_omni_records(OmniRecordType.TRAJECTORY.value, project_id, limit=10_000)
        corrections = self.database.list_omni_records(OmniRecordType.CORRECTION.value, project_id, limit=10_000)
        findings = self.database.list_omni_records(OmniRecordType.AUDIT_FINDING.value, project_id, limit=10_000)
        for record in behaviors:
            path = root / "Behaviors" / f"{self._safe(record['behavior_id'])}.md"
            body = self._frontmatter("behavior", record["behavior_id"], record) + "\n" + _NOTICE + "\n\n"
            body += f"# {record['name']}\n\n{record['description']}\n\n## Entrypoints\n\n"
            body += "\n".join(
                f"- `{entry['path']}:{entry['start_line']}` — `{entry['symbol']}`"
                for entry in record["entrypoints"]
            ) or "- None"
            body += "\n\n## Tests\n\n" + ("\n".join(f"- `{item}`" for item in record["tests"]) or "- None") + "\n"
            self._write(path, body, written, unchanged)
        for record in trajectories:
            path = root / "Trajectories" / f"{self._safe(record['trajectory_id'])}.md"
            events = self.database.list_omni_events(record["trajectory_id"])
            body = self._frontmatter("trajectory", record["trajectory_id"], record) + "\n" + _NOTICE + "\n\n"
            body += f"# {record['task_description']}\n\n- Outcome: **{record['outcome']}**\n- Task type: `{record['task_type']}`\n"
            body += "\n## Event sequence\n\n" + ("\n".join(
                f"{event['sequence']}. `{event['event_type']}` — behaviors: " +
                ", ".join(f"[[../Behaviors/{self._safe(item)}|{item}]]" for item in event["behavior_ids"])
                for event in events
            ) or "No events recorded.") + "\n"
            self._write(path, body, written, unchanged)
        status_paths = {
            "pending_review": "Corrections/Inbox", "active": "Corrections/Active",
            "rejected": "Corrections/Rejected", "archived": "Corrections/Archived",
            "superseded": "Corrections/Archived",
        }
        for record in corrections:
            directory = status_paths.get(record["status"], "Corrections/Inbox")
            path = root / directory / f"{self._safe(record['correction_id'])}.md"
            body = self._frontmatter("correction", record["correction_id"], record) + "\n" + _NOTICE + "\n\n"
            body += f"# {record['operation']}\n\n{record['instruction']}\n\n## Evidence\n\n"
            body += "\n".join(
                f"- [[../../Trajectories/{self._safe(item)}|{item}]]"
                for item in record["evidence_trajectory_ids"]
            ) + "\n"
            successful = record.get("successful_trajectory_ids", [])
            body += "\n## Successful reuse\n\n" + ("\n".join(
                f"- [[../../Trajectories/{self._safe(item)}|{item}]]"
                for item in successful
            ) or "- None") + "\n"
            body += (
                f"\n## Reuse metrics\n\n- Uses: **{record.get('use_count', 0)}**"
                f"\n- Successes: **{record.get('success_count', 0)}**"
                f"\n- Failures: **{record.get('failure_count', 0)}**\n"
            )
            events = self.database.list_omni_correction_events(record["correction_id"])
            body += "\n## Immutable lifecycle\n\n" + ("\n".join(
                f"- `{item['event_type']}` — `{item['created_at']}` — actor: `{item.get('actor') or 'system'}`"
                + (f" — [[../../Trajectories/{self._safe(item['trajectory_id'])}|trajectory]]"
                   if item.get("trajectory_id") else "")
                for item in events
            ) or "- None") + "\n"
            self._write(path, body, written, unchanged)
        for record in findings:
            path = root / "Conflicts" / f"{self._safe(record['finding_id'])}.md"
            body = self._frontmatter("audit_finding", record["finding_id"], record) + "\n" + _NOTICE + "\n\n"
            body += f"# {record['finding_type']}\n\n{record['explanation']}\n\n## Affected memories\n\n"
            body += "\n".join(f"- `{item}`" for item in record["affected_memory_ids"]) + "\n"
            body += "\n## Proposed record\n\n```json\n" + json.dumps(record["proposed_record"], indent=2) + "\n```\n"
            self._write(path, body, written, unchanged)
            for event in self.database.list_omni_revision_events(record["finding_id"]):
                decision = root / "Decisions" / f"{self._safe(event['event_id'])}.md"
                decision_body = self._frontmatter("decision", event["event_id"], {
                    "repository": "Memorycore", "source_revision": "canonical",
                    "status": event["event_type"], "confidence": 1.0,
                    "updated_at": event["created_at"],
                }) + "\n" + _NOTICE + "\n\n"
                decision_body += f"# {event['event_type']}\n\n- Finding: [[../Conflicts/{self._safe(record['finding_id'])}|{record['finding_id']}]]\n- Reviewer: `{event['reviewer']}`\n"
                self._write(decision, decision_body, written, unchanged)
        dashboard = self._dashboard(behaviors, trajectories, corrections, findings)
        self._write(root / "Dashboard.md", dashboard, written, unchanged)
        provenance = self._frontmatter("provenance", "projection-manifest", {
            "repository": "Memorycore", "source_revision": "canonical", "status": "generated",
            "confidence": 1.0, "updated_at": max(
                [item.get("updated_at") or item.get("created_at") or item.get("started_at") or "" for item in behaviors + trajectories + corrections + findings] or [""]
            ),
        }) + "\n" + _NOTICE + "\n\n# Projection manifest\n\n"
        provenance += f"- Project: `{project_id}`\n- Generated files: {len(written) + len(unchanged)}\n- Canonical source: Memorycore SQLite through MemoryService\n"
        self._write(root / "Provenance" / "projection-manifest.md", provenance, written, unchanged)
        return {"root": str(root), "written": sorted(written), "unchanged": sorted(unchanged)}

    def _dashboard(self, behaviors: list[dict[str, Any]], trajectories: list[dict[str, Any]],
                   corrections: list[dict[str, Any]], findings: list[dict[str, Any]]) -> str:
        outcomes = Counter(item["outcome"] for item in trajectories)
        statuses = Counter(item["status"] for item in corrections)
        open_conflicts = sum(1 for item in findings if item["status"] == "pending_review")
        correction_uses = sum(int(item.get("use_count", 0)) for item in corrections)
        correction_successes = sum(int(item.get("success_count", 0)) for item in corrections)
        reuse_rate = (correction_successes / correction_uses) if correction_uses else 0.0
        generated_at = max(
            [item.get("updated_at") or item.get("created_at") or item.get("started_at") or ""
             for item in behaviors + trajectories + corrections + findings] or ["1970-01-01T00:00:00+00:00"]
        )
        body = self._frontmatter("dashboard", "omni-dashboard", {
            "repository": "Memorycore", "source_revision": "canonical", "status": "generated",
            "confidence": 1.0, "updated_at": generated_at,
        }) + "\n" + _NOTICE + "\n\n# Omni Memory Harness\n\n"
        body += f"- Behaviors: **{len(behaviors)}**\n- Successful trajectories: **{outcomes['success']}**\n"
        body += f"- Failed trajectories: **{outcomes['failed']}**\n- Pending corrections: **{statuses['pending_review']}**\n"
        body += f"- Active corrections: **{statuses['active']}**\n- Open conflicts: **{open_conflicts}**\n"
        body += f"- Correction reuse success: **{correction_successes}/{correction_uses} ({reuse_rate:.0%})**\n"
        body += "\n## Trajectories\n\n" + ("\n".join(
            f"- [[Trajectories/{self._safe(item['trajectory_id'])}|{item['task_description']}]] — {item['outcome']}"
            for item in trajectories[:10]
        ) or "- None") + "\n"
        return body

    @staticmethod
    def _frontmatter(record_type: str, record_id: str, record: dict[str, Any]) -> str:
        values = {
            "omni_type": record_type, "omni_id": record_id,
            "canonical_source": "memorycore", "repository": record.get("repository") or "Memorycore",
            "revision": record.get("source_revision") or "canonical",
            "status": record.get("status") or record.get("outcome") or "active",
            "confidence": record.get("confidence", 1.0),
            "generated_at": record.get("updated_at") or record.get("created_at") or record.get("started_at") or "generated",
        }
        return "---\n" + "\n".join(f"{key}: {json.dumps(value)}" for key, value in values.items()) + "\n---"

    @staticmethod
    def _safe(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")[:160]

    @staticmethod
    def _write(path: Path, content: str, written: list[str], unchanged: list[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_text(encoding="utf-8") == content:
            unchanged.append(str(path))
            return
        path.write_text(content, encoding="utf-8")
        written.append(str(path))
