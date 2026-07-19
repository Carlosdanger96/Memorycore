from __future__ import annotations

import json
from pathlib import Path
import tempfile

from memorycore.demo.runner import run_demo


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="omni-memory-verify-") as directory:
        report = run_demo(Path(directory))
        required = {
            "ok", "failed_trajectory_id", "successful_trajectory_id", "correction_id",
            "retrieved_correction_ids", "finding_id", "projection_root",
            "correction_outcome_event_id", "correction_success_count",
        }
        missing = required - report.keys()
        if (missing or not report["ok"] or
                report["correction_id"] not in report["retrieved_correction_ids"] or
                report.get("correction_success_count") != 1):
            print(json.dumps({"ok": False, "missing": sorted(missing)}, indent=2))
            return 1
        print(json.dumps({
            "ok": True, "behavior_count": report["behavior_count"],
            "projected_file_count": report["projected_file_count"],
            "failed_trajectory_id": report["failed_trajectory_id"],
            "successful_trajectory_id": report["successful_trajectory_id"],
        }, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
