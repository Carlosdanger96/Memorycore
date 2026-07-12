"""
Memorycore command-line interface.

Provides commands for database initialization, health checks, and MCP server.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Sequence

from .memory_service import MemoryService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def default_database_path() -> Path:
    """Get the default database path from environment or user home."""
    configured = os.getenv("MEMORYCORE_DB")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".memorycore" / "memorycore.db"


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="memorycore",
        description="Memorycore - Local-first SQLite memory service for LLMs and agents",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=default_database_path(),
        help="Path to the SQLite database file",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    
    subcommands = parser.add_subparsers(dest="command", required=True)
    
    # init command
    subcommands.add_parser(
        "init",
        help="Create or initialize the SQLite database",
    )
    
    # doctor command
    subcommands.add_parser(
        "doctor",
        help="Verify SQLite and FTS5 health",
    )
    
    # stats command
    subcommands.add_parser(
        "stats",
        help="Show database statistics",
    )
    
    # backup command
    backup_parser = subcommands.add_parser(
        "backup",
        help="Create a backup of the database",
    )
    backup_parser.add_argument(
        "backup_path",
        type=Path,
        help="Path to save the backup file",
    )
    
    # restore command
    restore_parser = subcommands.add_parser(
        "restore",
        help="Restore the database from a backup",
    )
    restore_parser.add_argument(
        "backup_path",
        type=Path,
        help="Path to the backup file",
    )
    
    # projects command
    subcommands.add_parser(
        "projects",
        help="List all project IDs in the database",
    )
    
    # serve command (MCP)
    subcommands.add_parser(
        "serve",
        help="Run the optional stdio MCP server",
    )
    
    return parser


def configure_logging(verbose: bool = False) -> None:
    """Configure logging based on verbosity level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.getLogger("memorycore").setLevel(level)


def run_init(database_path: Path) -> dict[str, object]:
    """Initialize the database."""
    logger.info(f"Initializing database: {database_path}")
    service = MemoryService(database_path)
    try:
        health = service.health()
        health["command"] = "init"
        health["message"] = "Database initialized successfully"
        return health
    finally:
        service.close()


def run_doctor(database_path: Path) -> dict[str, object]:
    """Check database health."""
    logger.info(f"Checking database health: {database_path}")
    service = MemoryService(database_path)
    try:
        health = service.health()
        health["command"] = "doctor"
        
        # Additional health checks
        if health.get("ok"):
            health["message"] = "Database is healthy"
        else:
            health["message"] = "Database health check failed"
        
        return health
    finally:
        service.close()


def run_stats(database_path: Path, project_id: str | None = None) -> dict[str, object]:
    """Get database statistics."""
    logger.info(f"Getting database statistics: {database_path}")
    service = MemoryService(database_path)
    try:
        stats = service.get_stats(project_id)
        stats["command"] = "stats"
        stats["database"] = str(database_path)
        return stats
    finally:
        service.close()


def run_backup(database_path: Path, backup_path: Path) -> dict[str, object]:
    """Create a database backup."""
    logger.info(f"Creating backup from {database_path} to {backup_path}")
    service = MemoryService(database_path)
    try:
        success = service.backup(backup_path)
        if success:
            return {
                "ok": True,
                "command": "backup",
                "database": str(database_path),
                "backup": str(backup_path),
                "message": "Backup created successfully",
            }
        else:
            return {
                "ok": False,
                "command": "backup",
                "database": str(database_path),
                "backup": str(backup_path),
                "message": "Backup failed",
            }
    finally:
        service.close()


def run_restore(database_path: Path, backup_path: Path) -> dict[str, object]:
    """Restore database from backup."""
    logger.info(f"Restoring {database_path} from {backup_path}")
    service = MemoryService(database_path)
    try:
        success = service.restore(backup_path)
        if success:
            return {
                "ok": True,
                "command": "restore",
                "database": str(database_path),
                "backup": str(backup_path),
                "message": "Database restored successfully",
            }
        else:
            return {
                "ok": False,
                "command": "restore",
                "database": str(database_path),
                "backup": str(backup_path),
                "message": "Restore failed",
            }
    except Exception as e:
        return {
            "ok": False,
            "command": "restore",
            "database": str(database_path),
            "backup": str(backup_path),
            "message": str(e),
        }
    finally:
        service.close()


def run_projects(database_path: Path) -> dict[str, object]:
    """List all projects in the database."""
    logger.info(f"Listing projects from {database_path}")
    service = MemoryService(database_path)
    try:
        projects = service.list_projects()
        return {
            "ok": True,
            "command": "projects",
            "database": str(database_path),
            "count": len(projects),
            "projects": projects,
        }
    finally:
        service.close()


def main(argv: Sequence[str] | None = None) -> int:
    """
    Main entry point for the CLI.
    
    Args:
        argv: Command line arguments (defaults to sys.argv)
        
    Returns:
        int: Exit code (0 for success, non-zero for failure)
    """
    args = build_parser().parse_args(argv)
    
    # Configure logging
    configure_logging(args.verbose)
    
    # Handle MCP server separately
    if args.command == "serve":
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
        run_server(args.db)
        return 0
    
    # Handle other commands
    try:
        if args.command == "init":
            result = run_init(args.db)
        elif args.command == "doctor":
            result = run_doctor(args.db)
        elif args.command == "stats":
            result = run_stats(args.db)
        elif args.command == "backup":
            result = run_backup(args.db, args.backup_path)
        elif args.command == "restore":
            result = run_restore(args.db, args.backup_path)
        elif args.command == "projects":
            result = run_projects(args.db)
        else:
            print(f"Unknown command: {args.command}", file=sys.stderr)
            return 1
        
        # Output result as JSON
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0 if result.get("ok", False) else 1
        
    except Exception as e:
        logger.error(f"Command failed: {e}", exc_info=True)
        error_result = {
            "ok": False,
            "command": args.command,
            "error": str(e),
        }
        print(json.dumps(error_result, indent=2, sort_keys=True, default=str), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
