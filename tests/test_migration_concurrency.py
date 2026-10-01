"""Schema startup must be atomic across independent Windows/spawn processes."""
import hashlib
import multiprocessing
import sqlite3

import pytest

from memorycore.database import SCHEMA_SQL, SQLiteDatabase, content_fingerprint


def _initialize_together(path, barrier):
    database = SQLiteDatabase(path)
    try:
        barrier.wait(timeout=30)
        database.initialize()
        database.initialize()
    finally:
        database.close()


@pytest.mark.parametrize("schema", ["fresh", "v01", "v02"])
def test_concurrent_initialization(tmp_path, schema):
    path = tmp_path / "shared.db"
    if schema != "fresh":
        with sqlite3.connect(path) as connection:
            if schema == "v01":
                connection.executescript("""
                    CREATE TABLE memories (
                        id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                        memory_type TEXT NOT NULL, content TEXT NOT NULL,
                        summary TEXT, tags TEXT NOT NULL DEFAULT '[]',
                        status TEXT NOT NULL DEFAULT 'active'
                            CHECK(status IN ('active','archived','superseded')),
                        created_by TEXT, metadata TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                    );
                """)
            else:
                connection.executescript(SCHEMA_SQL.replace(
                    "    revision INTEGER NOT NULL DEFAULT 0,\n", ""
                ).replace("    content_fingerprint TEXT,\n", ""))
                index_sql = "CREATE INDEX IF NOT EXISTS idx_memories_active_project_updated ON memories(project_id, updated_at DESC) WHERE status = 'active';"
                connection.execute(index_sql)
                connection.executemany(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?, 'legacy')",
                    [(1, "initial_storage", "embedded-v1"),
                     (2, "active_retrieval_index", hashlib.sha256(index_sql.encode()).hexdigest())],
                )
            connection.execute("""
                INSERT INTO memories (id, project_id, memory_type, content,
                                      created_at, updated_at)
                VALUES ('legacy', 'alpha', 'fact', 'Preserved legacy memory', 'then', 'then')
            """)

    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(8)
    processes = [context.Process(target=_initialize_together, args=(path, barrier))
                 for _ in range(8)]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=60)
        assert [process.exitcode for process in processes] == [0] * 8
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)

    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (2,), (3,)]
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        if schema != "fresh":
            assert connection.execute(
                "SELECT content, revision, content_fingerprint FROM memories"
            ).fetchone() == ("Preserved legacy memory", 0,
                            content_fingerprint("alpha", "fact", "Preserved legacy memory"))
            assert connection.execute(
                "SELECT id FROM memory_fts WHERE memory_fts MATCH 'Preserved'"
            ).fetchall() == [("legacy",)]


def test_failed_initialization_rolls_back_schema_and_migrations(tmp_path, monkeypatch):
    database = SQLiteDatabase(tmp_path / "rollback.db")
    original = database._apply_migrations

    def fail_after_migrations():
        original()
        raise RuntimeError("injected migration failure")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(database, "_apply_migrations", fail_after_migrations)
            with pytest.raises(RuntimeError, match="injected migration failure"):
                database.initialize()
        assert not database.connection.in_transaction
        assert database.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall() == []
        database.initialize()
        assert database.health()["ok"]
    finally:
        database.close()


def test_migration_checksum_mismatch_is_not_ignored(tmp_path):
    database = SQLiteDatabase(tmp_path / "checksum.db")
    try:
        database.initialize()
        database.connection.execute(
            "UPDATE schema_migrations SET checksum = 'invalid' WHERE version = 2"
        )
        database.connection.commit()
        with pytest.raises(RuntimeError, match="migration checksum mismatch for version 2"):
            database.initialize()
        assert not database.connection.in_transaction
    finally:
        database.close()
