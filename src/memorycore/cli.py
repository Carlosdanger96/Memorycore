from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from .memory_service import MemoryService


def default_database_path() -> Path:
    configured = os.getenv("MEMORYCORE_DB")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".memorycore" / "memorycore.db"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="memorycore")
    parser.add_argument("--db", type=Path, default=default_database_path())
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("init", help="create or initialize the SQLite database")
    subcommands.add_parser("doctor", help="verify SQLite and FTS5 health")
    subcommands.add_parser("serve", help="run the optional stdio MCP server")
    service = subcommands.add_parser("serve-http", help="run the central Streamable HTTP MCP service")
    service.add_argument("--host", default=os.getenv("MEMORYCORE_HOST", "127.0.0.1"))
    service.add_argument("--port", type=int, default=int(os.getenv("MEMORYCORE_PORT", "8000")))
    backup = subcommands.add_parser("backup", help="create a consistent SQLite backup")
    backup.add_argument("destination", type=Path)
    export = subcommands.add_parser("export", help="export memories and audit events as JSONL")
    export.add_argument("destination", type=Path)
    importer = subcommands.add_parser("import", help="import memory records from JSONL")
    importer.add_argument("source", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command in {"serve", "serve-http"}:
        try:
            from .mcp_server import run_server
        except ModuleNotFoundError as exc:
            if exc.name == "mcp":
                print(
                    "MCP support is optional. Install it with: pip install -e \".[mcp]\"",
                    file=sys.stderr,
                )
                return 2
            raise
        if args.command == "serve-http":
            run_server(args.db, transport="streamable-http", host=args.host, port=args.port)
        else:
            run_server(args.db, transport="stdio")
        return 0

    service = MemoryService(args.db)
    try:
        if args.command == "backup":
            service.backup(args.destination)
            print(json.dumps({"ok": True, "backup": str(args.destination)}, indent=2))
            return 0
        if args.command == "export":
            count = service.export_jsonl(args.destination)
            print(json.dumps({"ok": True, "export": str(args.destination), "memory_count": count}, indent=2))
            return 0
        if args.command == "import":
            count = service.import_jsonl(args.source)
            print(json.dumps({"ok": True, "import": str(args.source), "memory_count": count}, indent=2))
            return 0
        result = service.health()
        result["command"] = args.command
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1
    finally:
        service.close()


if __name__ == "__main__":
    raise SystemExit(main())
