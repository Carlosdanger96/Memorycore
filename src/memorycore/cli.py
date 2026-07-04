from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .mcp_server import default_database_path, run_server
from .memory_service import MemoryService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="memorycore")
    parser.add_argument("--db", type=Path, default=default_database_path())
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("init", help="create or migrate the SQLite database")
    subcommands.add_parser("doctor", help="verify SQLite and FTS5 health")
    subcommands.add_parser("serve", help="run the stdio MCP server")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "serve":
        run_server(args.db)
        return 0
    service = MemoryService(args.db)
    try:
        result = service.health()
        result["command"] = args.command
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1
    finally:
        service.close()


if __name__ == "__main__":
    raise SystemExit(main())
