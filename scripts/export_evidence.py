from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False, env=env)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export reproducible Omni Memory Harness evidence")
    parser.add_argument("--output", type=Path, default=ROOT / "evidence")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "screenshots").mkdir(exist_ok=True)

    git_commands = {
        "revision.txt": ["git", "rev-parse", "HEAD"],
        "branch.txt": ["git", "branch", "--show-current"],
        "baseline-tag.txt": ["git", "tag", "--list", "hackathon-baseline-2026-07-19"],
        "commit-log.txt": ["git", "log", "--decorate", "--oneline", "--max-count=50"],
        "status.txt": ["git", "status", "--short", "--branch"],
    }
    for filename, command in git_commands.items():
        result = _run(command)
        (output / filename).write_text(result.stdout + result.stderr, encoding="utf-8")

    environment = dict(__import__("os").environ)
    environment["PYTHONPATH"] = str(ROOT / "src") + __import__("os").pathsep + environment.get("PYTHONPATH", "")
    tests = _run([sys.executable, "-m", "pytest", "-q"], env=environment)
    (output / "test-output.txt").write_text(tests.stdout + tests.stderr, encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="omni-evidence-demo-") as directory:
        demo = _run([
            sys.executable, "-m", "memorycore.demo.runner", "--workspace", directory,
        ], env=environment)
    (output / "demo-output.txt").write_text(demo.stdout + demo.stderr, encoding="utf-8")

    from memorycore.api.omni_routes import openapi_schema
    from memorycore.mcp_server import create_server
    from memorycore.memory_service import MemoryService

    (output / "openapi.json").write_text(json.dumps(openapi_schema(), indent=2), encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="omni-evidence-schema-") as directory:
        service = MemoryService(Path(directory) / "schema.db")
        try:
            tools = create_server(service)._tool_manager.list_tools()
            schema = [{"name": tool.name, "description": tool.description,
                       "parameters": tool.parameters} for tool in tools]
        finally:
            service.close()
    (output / "mcp-tools.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")

    packages = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        if name and name.lower() in {"memorycore", "mcp", "pytest", "pytest-asyncio", "sqlalchemy", "psycopg"}:
            packages.append({"name": name, "version": distribution.version,
                             "license": distribution.metadata.get("License")})
    (output / "dependencies.json").write_text(json.dumps(sorted(packages, key=lambda item: item["name"].lower()), indent=2), encoding="utf-8")

    for filename in [
        "BEFORE_HACKATHON.md", "HACKATHON_CHANGES.md", "CODEX_COLLABORATION.md",
        "THIRD_PARTY_NOTICES.md", "TESTING.md", "DEMO_SCRIPT.md",
    ]:
        shutil.copy2(ROOT / filename, output / filename)
    (output / "CODEX_SESSION_ID.txt").write_text("REQUIRED — run /feedback and record the actual session ID here.\n", encoding="utf-8")
    (output / "screenshots" / "README.md").write_text("Add actual screenshots or recordings here. Do not fabricate evidence.\n", encoding="utf-8")
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "test_exit_code": tests.returncode, "demo_exit_code": demo.returncode,
        "files": sorted(str(path.relative_to(output)) for path in output.rglob("*") if path.is_file()),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), **manifest}, indent=2))
    return 0 if tests.returncode == 0 and demo.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
