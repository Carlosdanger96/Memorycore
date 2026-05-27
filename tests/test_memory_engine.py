"""Tests for Memory Engine module."""

import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.storage import Storage, MemoryRecord
from server.memory_engine import MemoryEngine, MemoryStatus, SearchResult, ProjectContext
from server.audit import AuditLogger
from server.policy import PolicyEnforcer


class TestMemoryEngine(unittest.TestCase):
    """Test cases for MemoryEngine."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_memorycore.db")
        
        # Create storage
        self.storage = Storage(db_path=self.db_path)
        
        # Create audit logger
        self.audit_logger = AuditLogger(storage=self.storage)
        
        # Create policy enforcer
        self.policy_enforcer = PolicyEnforcer(
            storage=self.storage,
            audit_logger=self.audit_logger,
        )
        
        # Create memory engine
        self.engine = MemoryEngine(
            storage=self.storage,
            audit_logger=self.audit_logger,
            policy_enforcer=self.policy_enforcer,
        )
        
        # Create test project
        self.storage.create_project(
            project_id="test_project",
            name="Test Project",
            created_by="admin",
        )
        
        # Create test user
        self.storage.create_user(
            user_id="test_user",
            username="testuser",
        )
        
        # Grant writer role
        self.storage.grant_role(
            user_id="test_user",
            project_id="test_project",
            role_name="writer",
            assigned_by="admin",
        )

    def tearDown(self):
        """Clean up test fixtures."""
        self.storage.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        os.rmdir(self.temp_dir)

    def test_write_candidate(self):
        """Test writing a memory candidate."""
        record = self.engine.write_candidate(
            project_id="test_project",
            content="Test memory content",
            source_refs=["source1", "source2"],
            tags=["tag1", "tag2"],
            confidence=0.8,
            user_id="test_user",
        )
        
        self.assertIsNotNone(record)
        self.assertEqual(record.project_id, "test_project")
        self.assertEqual(record.content, "Test memory content")
        self.assertEqual(record.status, MemoryStatus.CANDIDATE)
        self.assertEqual(record.created_by, "test_user")
        self.assertEqual(record.source_refs, ["source1", "source2"])
        self.assertEqual(record.tags, ["tag1", "tag2"])
        self.assertEqual(record.confidence, 0.8)

    def test_write_candidate_with_id(self):
        """Test writing a candidate with custom ID."""
        record = self.engine.write_candidate(
            project_id="test_project",
            content="Test with custom ID",
            user_id="test_user",
            memory_id="custom_001",
        )
        
        self.assertEqual(record.memory_id, "custom_001")

    def test_search(self):
        """Test searching memories."""
        # Create some test memories
        for i in range(5):
            self.engine.write_candidate(
                project_id="test_project",
                content=f"Test content {i}",
                tags=["test", f"tag_{i % 2}"],
                user_id="test_user",
            )
        
        # Search all
        result = self.engine.search(
            project_id="test_project",
            user_id="test_user",
        )
        
        self.assertEqual(result.total, 5)
        self.assertEqual(len(result.results), 5)
        
        # Search with tag filter
        result = self.engine.search(
            project_id="test_project",
            tags=["tag_0"],
            user_id="test_user",
        )
        
        self.assertEqual(result.total, 3)  # tag_0 appears in memories 0, 2, 4
        
        # Search with limit
        result = self.engine.search(
            project_id="test_project",
            limit=2,
            user_id="test_user",
        )
        
        self.assertEqual(len(result.results), 2)
        self.assertEqual(result.total, 5)

    def test_get_project_context(self):
        """Test getting project context."""
        # Create some memories
        for i in range(3):
            self.engine.write_candidate(
                project_id="test_project",
                content=f"Test content {i}",
                tags=["test"],
                user_id="test_user",
            )
        
        # Accept one memory
        memories = self.storage.get_memories_by_project("test_project")
        if memories:
            self.engine.accept_candidate(memories[0].memory_id, user_id="test_user")
        
        context = self.engine.get_project_context(
            project_id="test_project",
            user_id="test_user",
        )
        
        self.assertEqual(context.project_id, "test_project")
        self.assertEqual(context.memory_count, 3)
        self.assertEqual(context.candidate_count, 2)
        self.assertEqual(context.accepted_count, 1)
        self.assertEqual(context.archived_count, 0)
        self.assertIn("test", context.tags)

    def test_open_raw(self):
        """Test opening raw memory content."""
        # Create a memory
        record = self.engine.write_candidate(
            project_id="test_project",
            content="Raw content",
            user_id="test_user",
        )
        
        # Open raw
        raw = self.engine.open_raw(
            memory_id=record.memory_id,
            user_id="test_user",
        )
        
        self.assertIsNotNone(raw)
        self.assertEqual(raw["content"], "Raw content")
        self.assertEqual(raw["memory_id"], record.memory_id)

    def test_open_raw_not_found(self):
        """Test opening non-existent memory."""
        raw = self.engine.open_raw(
            memory_id="nonexistent",
            user_id="test_user",
        )
        self.assertIsNone(raw)

    def test_accept_candidate(self):
        """Test accepting a candidate memory."""
        # Create a candidate
        record = self.engine.write_candidate(
            project_id="test_project",
            content="Candidate to accept",
            user_id="test_user",
        )
        
        # Accept it
        accepted = self.engine.accept_candidate(
            memory_id=record.memory_id,
            user_id="test_user",
        )
        
        self.assertIsNotNone(accepted)
        self.assertEqual(accepted.status, MemoryStatus.ACCEPTED)

    def test_archive_memory(self):
        """Test archiving a memory."""
        # Create a candidate
        record = self.engine.write_candidate(
            project_id="test_project",
            content="Candidate to archive",
            user_id="test_user",
        )
        
        # Archive it
        archived = self.engine.archive_memory(
            memory_id=record.memory_id,
            user_id="test_user",
        )
        
        self.assertIsNotNone(archived)
        self.assertEqual(archived.status, MemoryStatus.ARCHIVED)

    def test_update_memory_status(self):
        """Test updating memory status."""
        # Create a candidate
        record = self.engine.write_candidate(
            project_id="test_project",
            content="Test",
            user_id="test_user",
        )
        
        # Update to accepted
        updated = self.engine.update_memory_status(
            memory_id=record.memory_id,
            new_status=MemoryStatus.ACCEPTED,
            user_id="test_user",
        )
        
        self.assertEqual(updated.status, MemoryStatus.ACCEPTED)
        
        # Update to archived
        updated = self.engine.update_memory_status(
            memory_id=record.memory_id,
            new_status=MemoryStatus.ARCHIVED,
            user_id="test_user",
        )
        
        self.assertEqual(updated.status, MemoryStatus.ARCHIVED)

    def test_invalid_status_transition(self):
        """Test invalid status transition."""
        # Create and accept a memory
        record = self.engine.write_candidate(
            project_id="test_project",
            content="Test",
            user_id="test_user",
        )
        self.engine.accept_candidate(record.memory_id, user_id="test_user")
        
        # Try to go back to candidate (invalid)
        with self.assertRaises(ValueError):
            self.engine.update_memory_status(
                memory_id=record.memory_id,
                new_status=MemoryStatus.CANDIDATE,
                user_id="test_user",
            )

    def test_import_memories(self):
        """Test importing multiple memories."""
        memories = [
            {
                "memory_id": f"import_{i}",
                "project_id": "test_project",
                "content": f"Imported content {i}",
                "tags": ["imported"],
            }
            for i in range(3)
        ]
        
        imported = self.engine.import_memories(
            memories=memories,
            user_id="test_user",
        )
        
        self.assertEqual(len(imported), 3)
        
        # Verify they were stored
        for record in imported:
            fetched = self.storage.get_memory(record.memory_id)
            self.assertIsNotNone(fetched)

    def test_get_memory(self):
        """Test getting a memory by ID."""
        record = self.engine.write_candidate(
            project_id="test_project",
            content="Test get",
            user_id="test_user",
        )
        
        fetched = self.engine.get_memory(
            memory_id=record.memory_id,
            user_id="test_user",
        )
        
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.memory_id, record.memory_id)

    def test_get_memory_not_found(self):
        """Test getting non-existent memory."""
        fetched = self.engine.get_memory(
            memory_id="nonexistent",
            user_id="test_user",
        )
        self.assertIsNone(fetched)


class TestMemoryEngineWithoutPolicy(unittest.TestCase):
    """Test MemoryEngine without policy enforcement."""

    def setUp(self):
        """Set up test fixtures without policy."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_memorycore.db")
        
        self.storage = Storage(db_path=self.db_path)
        self.audit_logger = AuditLogger(storage=self.storage)
        
        # No policy enforcer
        self.engine = MemoryEngine(
            storage=self.storage,
            audit_logger=self.audit_logger,
            policy_enforcer=None,
        )
        
        self.storage.create_project(
            project_id="test_project",
            name="Test Project",
            created_by="admin",
        )

    def tearDown(self):
        """Clean up test fixtures."""
        self.storage.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        os.rmdir(self.temp_dir)

    def test_write_without_policy(self):
        """Test writing without policy enforcement."""
        # Should work without policy
        record = self.engine.write_candidate(
            project_id="test_project",
            content="No policy test",
            user_id="any_user",
        )
        
        self.assertIsNotNone(record)

    def test_search_without_policy(self):
        """Test searching without policy enforcement."""
        self.engine.write_candidate(
            project_id="test_project",
            content="Test",
            user_id="any_user",
        )
        
        result = self.engine.search(
            project_id="test_project",
            user_id="any_user",
        )
        
        self.assertEqual(result.total, 1)


class TestSearchResult(unittest.TestCase):
    """Test SearchResult dataclass."""

    def test_to_dict(self):
        """Test converting SearchResult to dictionary."""
        records = [
            MemoryRecord(
                memory_id="test_001",
                project_id="test_project",
                content="Test 1",
            ),
            MemoryRecord(
                memory_id="test_002",
                project_id="test_project",
                content="Test 2",
            ),
        ]
        
        result = SearchResult(
            results=records,
            total=2,
            limit=10,
            offset=0,
        )
        
        data = result.to_dict()
        
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["limit"], 10)
        self.assertEqual(data["offset"], 0)
        self.assertEqual(len(data["results"]), 2)


class TestProjectContext(unittest.TestCase):
    """Test ProjectContext dataclass."""

    def test_to_dict(self):
        """Test converting ProjectContext to dictionary."""
        context = ProjectContext(
            project_id="test_project",
            project_name="Test Project",
            memory_count=10,
            accepted_count=5,
            candidate_count=3,
            archived_count=2,
            recent_memories=[],
            tags=["tag1", "tag2"],
        )
        
        data = context.to_dict()
        
        self.assertEqual(data["project_id"], "test_project")
        self.assertEqual(data["project_name"], "Test Project")
        self.assertEqual(data["memory_count"], 10)
        self.assertEqual(data["accepted_count"], 5)
        self.assertEqual(data["candidate_count"], 3)
        self.assertEqual(data["archived_count"], 2)
        self.assertEqual(data["tags"], ["tag1", "tag2"])


if __name__ == "__main__":
    unittest.main()
