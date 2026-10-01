from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from .memory_service import MemoryService
from .mcp_server import MemoryMCPPolicy
from .models import ClientRole
from .policy import MemoryAccessError, RevisionConflictError

_ROLES = "reader", "writer", "approver", "administrator"


def default_database_path() -> Path:
    configured = os.getenv("MEMORYCORE_DB")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".memorycore" / "memorycore.db"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="memorycore")
    parser.add_argument("--db", type=Path, default=default_database_path())
    parser.add_argument("--database-url", help="PostgreSQL URL; overrides --db")
    parser.add_argument("--client", default=None,
                        help="client identity for this operation (default: MEMORYCORE_CLIENT_ID)")
    parser.add_argument("--role", choices=_ROLES, default=None,
                        help="client role for this operation (default: MEMORYCORE_CLIENT_ROLE)")
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("init", help="create or initialize the SQLite database")
    subcommands.add_parser("doctor", help="verify SQLite and FTS5 health")
    subcommands.add_parser("check", help="integrity and foreign-key check")

    serve = subcommands.add_parser("serve", help="run the optional stdio MCP server")
    serve_http = subcommands.add_parser("serve-http", help="run the HTTP MCP server")
    for command in (serve, serve_http):
        if command is serve_http:
            command.add_argument("--host", default="127.0.0.1")
            command.add_argument("--port", type=int, default=8000)

    add = subcommands.add_parser("add", help="add a memory (duplicate-safe)")
    _add_memory_arguments(add)

    get = subcommands.add_parser("get", help="retrieve one memory by ID")
    get.add_argument("memory_id")

    search = subcommands.add_parser("search", help="full-text search within a project")
    search.add_argument("query")
    search.add_argument("--project", required=True)
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--type", dest="memory_type", default=None)
    search.add_argument("--status", default="active")

    update = subcommands.add_parser("update", help="update a memory with revision conflict detection")
    update.add_argument("memory_id")
    update.add_argument("--content")
    update.add_argument("--summary")
    update.add_argument("--tag", dest="tags", action="append", default=None)
    update.add_argument("--metadata")
    update.add_argument("--expected-revision", type=int, default=None,
                        help="fail with a conflict error if the stored revision differs")

    review = subcommands.add_parser("review", help="automated exact-source review of a pending candidate")
    review.add_argument("memory_id")
    review.add_argument("--expected-revision", type=int, required=True)
    review.add_argument("--content-sha256", required=True)

    for name, help_text in (
        ("approve", "approve a pending memory (approver/administrator)"),
        ("reject", "reject a pending memory (approver/administrator)"),
        ("archive", "archive a memory (approver/administrator)"),
    ):
        command = subcommands.add_parser(name, help=help_text)
        command.add_argument("memory_id")

    history = subcommands.add_parser("history", help="audit history for one memory")
    history.add_argument("memory_id")
    history.add_argument("--limit", type=int, default=100)

    projects = subcommands.add_parser("projects", help="list known project IDs")

    backup = subcommands.add_parser("backup", help="online SQLite backup")
    backup.add_argument("destination")

    restore = subcommands.add_parser("restore", help="restore a backup into this database path")
    restore.add_argument("source")

    export_cmd = subcommands.add_parser("export", help="full-fidelity JSONL export")
    export_cmd.add_argument("destination")

    import_cmd = subcommands.add_parser("import", help="full-fidelity JSONL import")
    import_cmd.add_argument("source")

    project = subcommands.add_parser("project", help="render an Obsidian projection for a project")
    project.add_argument("project_id")
    project.add_argument("--vault", required=True,
                         help="Obsidian vault root; must be inside MEMORYCORE_ALLOWED_VAULT_ROOTS")
    return parser


def _add_memory_arguments(add: argparse.ArgumentParser) -> None:
    add.add_argument("--project", required=True)
    add.add_argument("--type", dest="memory_type", required=True,
                     choices=("fact", "decision", "preference", "procedure", "correction", "note"))
    add.add_argument("--content", required=True)
    add.add_argument("--summary")
    add.add_argument("--tag", dest="tags", action="append", default=None)
    add.add_argument("--metadata", default=None, help="JSON object with arbitrary provenance")
    add.add_argument("--session")
    add.add_argument("--source", dest="source_type", default="manual_import")
    add.add_argument("--source-uri")
    add.add_argument("--source-id")
    add.add_argument("--confidence", type=float, default=None)
    add.add_argument("--status", default=None,
                     help="initial status (default: role policy decides pending/active)")


def _policy_from_args(args: argparse.Namespace) -> MemoryMCPPolicy:
    base = MemoryMCPPolicy.from_environment()
    if not args.client and not args.role:
        return base
    return MemoryMCPPolicy(
        client_id=args.client or base.client_id,
        client_role=args.role or base.client_role,
        allowed_projects=set(base.allowed_projects) if base.allowed_projects is not None else None,
        read_only=base.read_only,
        require_approval=base.require_approval,
        model_provider=base.model_provider,
        model_name=base.model_name,
    )


def _parse_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("--metadata must be a JSON object")
    return parsed


def _emit(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))


def _fail(message: str, code: int = 1) -> int:
    print(json.dumps({"ok": False, "error": message}, indent=2), file=sys.stderr)
    return code


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    database_target = args.database_url or args.db
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
            run_server(database_target, transport="streamable-http", host=args.host, port=args.port)
        else:
            run_server(database_target, transport="stdio")
        return 0

    service = MemoryService(database_target)
    try:
        if args.command == "init":
            result = service.health()
            result["ok"] = True
            result["command"] = "init"
            _emit(result)
            return 0
        if args.command == "doctor":
            result = service.health()
            result["command"] = "doctor"
            _emit(result)
            return 0 if result["ok"] else 1
        if args.command == "check":
            result = {"ok": True, "command": "check", **service.integrity_check()}
            _emit(result)
            return 0 if result["integrity"] == "ok" and result["foreign_key_violations"] == 0 else 1

        if args.command == "backup":
            service.backup(args.destination)
            _emit({"ok": True, "backup": str(args.destination)})
            return 0
        if args.command == "restore":
            service.restore(args.source)
            restored = service.health()
            _emit({"ok": True, "restored_from": str(args.source), **restored})
            return 0
        if args.command == "export":
            count = service.export_jsonl(args.destination)
            _emit({"ok": True, "export": str(args.destination), "memory_count": count})
            return 0
        if args.command == "import":
            count = service.import_jsonl(args.source)
            _emit({"ok": True, "import": str(args.source), "memory_count": count})
            return 0

        if args.command == "project":
            from .projections.obsidian import ObsidianProjection
            allowed = {item for item in os.getenv("MEMORYCORE_ALLOWED_VAULT_ROOTS", "").split(os.pathsep)
                       if item}
            if not allowed:
                return _fail("Obsidian projection requires MEMORYCORE_ALLOWED_VAULT_ROOTS")
            projection = ObsidianProjection(service.database, sorted(allowed))
            result = projection.project(args.vault, project_id=args.project_id)
            _emit({"ok": True, **result})
            return 0

        policy = _policy_from_args(args)

        if args.command == "review":
            result = service.review_memory(args.memory_id, policy=policy,
                expected_revision=args.expected_revision, expected_content_sha256=args.content_sha256)
            _emit(result)
            return 0

        if args.command == "add":
            policy.require_role(ClientRole.WRITER, ClientRole.APPROVER, ClientRole.ADMINISTRATOR)
            policy.check_project(args.project)
            result = service.add_memory_or_duplicate(
                project_id=args.project, memory_type=args.memory_type,
                content=args.content, summary=args.summary, tags=args.tags,
                created_by=policy.client_id, metadata=_parse_metadata(args.metadata),
                client_id=policy.client_id, model_provider=policy.model_provider,
                model_name=policy.model_name, session_id=args.session,
                source_type=args.source_type, source_uri=args.source_uri,
                source_id=args.source_id, confidence=args.confidence,
                status=args.status or policy.creation_status())
            record = dict(result["memory"])
            record["duplicate"] = result["duplicate"]
            record["duplicate_of"] = record["id"] if result["duplicate"] else None
            _emit(record)
            return 0

        if args.command == "get":
            memory = service.get_memory(args.memory_id)
            if memory is None:
                return _fail(f"memory not found: {args.memory_id}")
            policy.check_project(memory.project_id)
            _emit(memory.to_dict())
            return 0

        if args.command == "search":
            policy.check_project(args.project)
            results = service.search_memory(query=args.query, project_id=args.project,
                                            limit=args.limit, memory_type=args.memory_type,
                                            status=args.status)
            _emit({"ok": True, "count": len(results), "memories": [m.to_dict() for m in results]})
            return 0

        if args.command == "update":
            policy.require_role(ClientRole.WRITER, ClientRole.APPROVER, ClientRole.ADMINISTRATOR)
            existing = service.get_memory(args.memory_id)
            if existing is None:
                return _fail(f"memory not found: {args.memory_id}")
            policy.check_project(existing.project_id)
            if policy.client_role == "writer" and (
                existing.status != "pending" or existing.client_id != policy.client_id
            ):
                return _fail("writers may only update their own pending memories")
            try:
                updated = service.update_memory(
                    args.memory_id, content=args.content, summary=args.summary,
                    tags=args.tags, metadata=_parse_metadata(args.metadata),
                    updated_by=policy.client_id, expected_revision=args.expected_revision)
            except RevisionConflictError as error:
                return _fail(f"revision conflict: {error}", code=3)
            if updated is None:
                return _fail(f"memory not found: {args.memory_id}")
            _emit(updated.to_dict())
            return 0

        if args.command in {"approve", "reject", "archive"}:
            policy.require_role(ClientRole.APPROVER, ClientRole.ADMINISTRATOR)
            existing = service.get_memory(args.memory_id)
            if existing is None:
                return _fail(f"memory not found: {args.memory_id}")
            policy.check_project(existing.project_id)
            if args.command == "approve":
                if existing.client_id == policy.client_id:
                    return _fail("a client cannot approve its own memory")
                updated = service.approve_memory(args.memory_id, approved_by=policy.client_id)
            elif args.command == "reject":
                updated = service.reject_memory(args.memory_id, rejected_by=policy.client_id)
            else:
                updated = service.archive_memory(args.memory_id)
            _emit(updated.to_dict() if updated else {"ok": False})
            return 0

        if args.command == "history":
            memory = service.get_memory(args.memory_id)
            if memory is None:
                return _fail(f"memory not found: {args.memory_id}")
            policy.check_project(memory.project_id)
            events = service.get_memory_history(args.memory_id, args.limit)
            _emit({"ok": True, "count": len(events), "events": events})
            return 0

        if args.command == "projects":
            _emit({"ok": True, "projects": service.database.list_projects()})
            return 0

        return _fail(f"unknown command: {args.command}", code=2)
    except MemoryAccessError as error:
        return _fail(str(error), code=4)
    except RevisionConflictError as error:
        return _fail(str(error), code=3)
    except OSError as error:
        return _fail(str(error))
    except (ValueError, KeyError) as error:
        return _fail(str(error))
    finally:
        service.close()


if __name__ == "__main__":
    raise SystemExit(main())
