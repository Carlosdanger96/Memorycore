"""PostgreSQL parity against a disposable database when a server is available."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest

from memorycore.memory_service import MemoryService


@pytest.fixture
def postgres_url():
    configured = os.getenv("MEMORYCORE_TEST_POSTGRES_URL")
    if not configured:
        pytest.skip("set MEMORYCORE_TEST_POSTGRES_URL for PostgreSQL integration")
    sqlalchemy = pytest.importorskip("sqlalchemy")
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    admin_url = make_url(configured).set(database="postgres")
    name = "memorycore_test_" + uuid4().hex[:12]
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f"CREATE DATABASE {name}"))
    try:
        yield str(make_url(configured).set(database=name))
    finally:
        with admin.connect() as connection:
            connection.execute(text(f"DROP DATABASE {name} WITH (FORCE)"))
        admin.dispose()


def test_postgres_shared_lifecycle_and_history(postgres_url):
    service = MemoryService(postgres_url)
    first = service.add_memory(
        project_id="alpha", memory_type="decision", content="Use one shared memory service",
        status="pending", client_id="writer",
    )
    service.add_memory(
        project_id="beta", memory_type="decision", content="Use one shared memory service"
    )
    assert service.search_memory(query="shared memory", project_id="alpha") == []
    service.approve_memory(first.id, approved_by="reviewer")
    replacement = service.correct_memory(
        first.id, content="Use one durable shared memory service", updated_by="reviewer"
    )
    assert [memory.id for memory in service.search_memory(
        query="durable shared memory", project_id="alpha"
    )] == [replacement.id]
    assert service.get_memory(first.id).status == "superseded"
    assert service.get_memory_links(first.id)[0]["to_memory_id"] == first.id
    assert [event["event_type"] for event in service.get_memory_history(first.id)] == [
        "memory_created", "memory_approved", "memory_superseded"
    ]
    proposed = service.add_memory(
        project_id="alpha", memory_type="decision",
        content="Use one reliable durable shared memory service", status="pending"
    )
    assert service.duplicate_candidates(
        project_id="alpha", content=proposed.content
    )[0]["memory_id"] == replacement.id
    with pytest.raises(ValueError, match=replacement.id):
        service.approve_memory(proposed.id, approved_by="reviewer")
    assert service.get_memory(proposed.id).status == "pending"
    service.close()

    reopened = MemoryService(postgres_url)
    try:
        assert reopened.get_memory(replacement.id).status == "active"
        assert reopened.get_memory_links(first.id)[0]["from_memory_id"] == replacement.id
    finally:
        reopened.close()


def test_postgres_concurrent_exact_writes(postgres_url):
    MemoryService(postgres_url).close()
    barrier = Barrier(2)

    def write():
        service = MemoryService(postgres_url)
        try:
            barrier.wait(timeout=5)
            try:
                service.add_memory(
                    project_id="alpha", memory_type="fact", content="One durable fact"
                )
                return "created"
            except ValueError as exc:
                assert "duplicate" in str(exc)
                return "blocked"
        finally:
            service.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: write(), range(2))) == ["blocked", "created"]


def test_postgres_jsonl_recovery_preserves_relationships(postgres_url, tmp_path):
    from sqlalchemy import text

    service = MemoryService(postgres_url)
    first = service.add_memory(
        project_id="alpha", memory_type="fact", content="Source fact"
    )
    replacement = service.correct_memory(
        first.id, content="Corrected source fact", updated_by="reviewer"
    )
    service.record_access_denial(
        client_id="writer", operation="memory_search", project_id="beta",
        reason="project_not_allowed",
    )
    before = service.database.snapshot_records()
    export = tmp_path / "postgres.jsonl"
    assert service.export_jsonl(export) == 2
    service.close()


    # Only the disposable test database is cleared. The versioned JSONL file
    # then exercises the same restore contract as SQLite.
    service = MemoryService(postgres_url)
    with service.database.engine.begin() as connection:
        connection.execute(text("DELETE FROM access_events"))
        connection.execute(text("DELETE FROM memory_links"))
        connection.execute(text("DELETE FROM memory_events"))
        connection.execute(text("DELETE FROM memories"))
    assert service.import_jsonl(export) == 2
    after = service.database.snapshot_records()
    assert [item.to_dict() for item in after[0]] == [item.to_dict() for item in before[0]]
    assert after[1:] == before[1:]
    assert service.get_memory(replacement.id).status == "active"
    service.close()


def test_postgres_existing_schema_upgrade_preserves_records_and_audit(postgres_url):
    from sqlalchemy import create_engine, text

    service = MemoryService(postgres_url)
    created = service.add_memory(project_id="alpha", memory_type="fact",
                                 content="Existing PostgreSQL fact",
                                 source_type="document", source_uri="notes/old.md")
    service.close()

    # Model an older deployed schema in the disposable database. The migration
    # runner must recreate supporting tables and ordering without data loss.
    engine = create_engine(postgres_url)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE access_events"))
        connection.execute(text("DROP TABLE memory_links"))
        connection.execute(text("ALTER TABLE memory_events DROP COLUMN event_order"))
        connection.execute(text("DROP TABLE schema_migrations"))
    engine.dispose()

    reopened = MemoryService(postgres_url)
    try:
        assert reopened.get_memory(created.id).source_uri == "notes/old.md"
        assert reopened.get_memory_history(created.id)[0]["event_type"] == "memory_created"
        assert reopened.search_memory(query="PostgreSQL fact", project_id="alpha")[0].id == created.id
        with reopened.database.engine.connect() as connection:
            versions = connection.execute(text("SELECT version FROM schema_migrations ORDER BY version")).scalars().all()
        assert versions == [1, 2]
    finally:
        reopened.close()


def test_postgres_rejects_changed_migration_checksum(postgres_url):
    from sqlalchemy import create_engine, text

    MemoryService(postgres_url).close()
    engine = create_engine(postgres_url)
    with engine.begin() as connection:
        connection.execute(text("UPDATE schema_migrations SET checksum='tampered' WHERE version=2"))
    engine.dispose()
    with pytest.raises(RuntimeError, match="migration checksum mismatch"):
        MemoryService(postgres_url)


def test_explicit_psycopg_url_uses_postgres_adapter(postgres_url):
    service = MemoryService(postgres_url.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        assert service.health()["ok"] is True
        assert service.database.__class__.__name__ == "PostgresDatabase"
    finally:
        service.close()
