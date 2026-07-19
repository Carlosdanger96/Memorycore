from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
from typing import Sequence

from memorycore.demo.runner import run_demo


def _verify(report: dict) -> int:
    required = {
        "ok", "failed_trajectory_id", "successful_trajectory_id", "correction_id",
        "retrieved_correction_ids", "finding_id", "projection_root",
        "correction_outcome_event_id", "correction_use_count", "correction_success_count",
        "repository_revision", "revision_decision_id", "duration_seconds",
        "projected_file_count",
    }
    missing = required - report.keys()
    if (missing or not report.get("ok") or
            report.get("correction_id") not in report.get("retrieved_correction_ids", []) or
            report.get("correction_use_count") != 1 or
            report.get("correction_success_count") != 1 or
            report.get("projected_file_count", 0) < 14):
        print(json.dumps({"ok": False, "missing": sorted(missing)}, indent=2))
        return 1
    print(json.dumps({
        "ok": True, "behavior_count": report["behavior_count"],
        "projected_file_count": report["projected_file_count"],
        "failed_trajectory_id": report["failed_trajectory_id"],
        "successful_trajectory_id": report["successful_trajectory_id"],
    }, indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Omni Memory Harness demo evidence")
    parser.add_argument("--report", type=Path, help="verify an existing demo-report.json")
    args = parser.parse_args(argv)
    if args.report:
        return _verify(json.loads(args.report.read_text(encoding="utf-8")))
    with tempfile.TemporaryDirectory(prefix="omni-memory-verify-") as directory:
        return _verify(run_demo(Path(directory)))


if __name__ == "__main__":
    raise SystemExit(main())
