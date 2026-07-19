from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from memorycore import MemoryService
from memorycore.audit import OpenAIResponsesAuditProvider


def main() -> int:
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set")
    with tempfile.TemporaryDirectory(prefix="memorycore-live-audit-") as directory:
        service = MemoryService(Path(directory) / "audit.db")
        try:
            service.add_memory(
                project_id="live-smoke", memory_type="procedure",
                content="Tool output verification is optional.",
                metadata={"claim_key": "verification_policy"},
            )
            service.add_memory(
                project_id="live-smoke", memory_type="procedure",
                content="Tool output verification is mandatory.",
                metadata={"claim_key": "verification_policy"},
            )
            provider = OpenAIResponsesAuditProvider.from_environment()
            findings = service.omni.audit_memories(project_id="live-smoke", provider=provider)
            result = {
                "ok": bool(findings), "model": provider.model,
                "finding_types": [item["finding_type"] for item in findings],
                "all_require_approval": all(item["requires_approval"] for item in findings),
                "originals_preserved": len(service.search_memory(
                    query="", project_id="live-smoke", status="active", limit=10,
                )) == 2,
            }
            print(json.dumps(result, indent=2))
            return 0 if result["ok"] and result["all_require_approval"] and result["originals_preserved"] else 1
        finally:
            service.close()


if __name__ == "__main__":
    raise SystemExit(main())
