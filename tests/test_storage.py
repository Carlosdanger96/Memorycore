"""Tests for Storage module."""

import json
import os
import tempfile
import unittest
from datetime import datetime

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.storage import Storage, MemoryRecord, MemoryStatus, AuditRecord


class TestStorage(unittest.TestCase):
    """Test cases for Storage class."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a temporary database file
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_memorycore.db")
        self.storage = Storage(db_path=self.db_path)

    def tearDown(self):
        """Clean up test fixtures."""
        self.storage.close()
        # Clean up temp files
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        os.rmdir(self.temp_dir)

    def test_create_memory(self):
        """Test creating a memory record."""
        record = MemoryRecord(
            memory_id="test_001",
            project_id="test_project",
            content="Test content",
            source_refs=["source1", "source2"],
            created_at=datetime.utcnow().isoformat(),
            created_by="test_user",
            tags=["tag1", "tag2"],
            confidence=0.8,
            status=MemoryStatus.CANDIDATE,
        )
        
        created = self.storage.create_memory(record)
        
        self.assertEqual(created.memory_id, "test_001")
        self.assertEqual(created.project_id, "test_project")
        self.assertEqual(created.content, "Test content")

    def test_get_memory(self):
        """Test getting a memory record."""
        record = MemoryRecord(
            memory_id="test_002",
            project_id="test_project",
            content="Test content 2",
        )
        self.storage.create_memory(record)
        
        fetched = self.storage.get_memory("test_002")
        
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.memory_id, "test_002")
        self.assertEqual(fetched.content, "Test content 2")

    def test_get_memory_not_found(self):
        """Test getting a non-existent memory."""
        fetched = self.storage.get_memory("nonexistent")
        self.assertIsNone(fetched)

    def test_update_memory(self):
        """Test updating a memory record."""
        record = MemoryRecord(
            memory_id="test_003",
            project_id="test_project",
            content="Original content",
        )
        self.storage.create_memory(record)
        
        updated = self.storage.update_memory(
            "test_003",
            {"content": "Updated content", "status": MemoryStatus.ACCEPTED}
        )
        
        self.assertIsNotNone(updated)
        self.assertEqual(updated.content, "Updated content")
        self.assertEqual(updated.status, MemoryStatus.ACCEPTED)

    def test_delete_memory(self):
        """Test deleting a memory record."""
        record = MemoryRecord(
            memory_id="test_004",
            project_id="test_project",
            content="To be deleted",
        )
        self.storage.create_memory(record)
        
        deleted = self.storage.delete_memory("test_004")
        self.assertTrue(deleted)
        
        fetched = self.storage.get_memory("test_004")
        self.assertIsNone(fetched)

    def test_search_memories(self):
        """Test searching memory records."""
        # Create test memories
        for i in range(5):
            record = MemoryRecord(
                memory_id=f"test_search_{i}",
                project_id="test_project",
                content=f"Test content {i}",
                tags=["test", f"tag_{i % 2}"],
            )
            self.storage.create_memory(record)
        
        # Search by project
        results, total = self.storage.search_memories(project_id="test_project")
        self.assertEqual(total, 5)
        self.assertEqual(len(results), 5)
        
        # Search by tag
        results, total = self.storage.search_memories(tags=["tag_0"])
        self.assertEqual(total, 3)  # tag_0 appears in memories 0, 2, 4
        
        # Search with limit
        results, total = self.storage.search_memories(project_id="test_project", limit=2)
        self.assertEqual(len(results), 2)
        self.assertEqual(total, 5)

    def test_get_memories_by_project(self):
        """Test getting memories by project."""
        # Create memories in different projects
        for i in range(3):
            record = MemoryRecord(
                memory_id=f"proj1_{i}",
                project_id="project1",
                content=f"Project 1 content {i}",
            )
            self.storage.create_memory(record)
        
        for i in range(2):
            record = MemoryRecord(
                memory_id=f"proj2_{i}",
                project_id="project2",
                content=f"Project 2 content {i}",
            )
            self.storage.create_memory(record)
        
        proj1_memories = self.storage.get_memories_by_project("project1")
        self.assertEqual(len(proj1_memories), 3)
        
        proj2_memories = self.storage.get_memories_by_project("project2")
        self.assertEqual(len(proj2_memories), 2)

    def test_audit_log(self):
        """Test audit logging."""
        audit = self.storage.log_audit(
            action="write",
            entity_type="memory",
            entity_id="test_001",
            user_id="test_user",
            project_id="test_project",
            details={"test": "value"},
        )
        
        self.assertIsNotNone(audit)
        self.assertEqual(audit.action, "write")
        self.assertEqual(audit.entity_type, "memory")
        self.assertEqual(audit.entity_id, "test_001")
        
        # Get audit logs
        logs, total = self.storage.get_audit_logs(user_id="test_user")
        self.assertGreaterEqual(total, 1)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].action, "write")

    def test_project_operations(self):
        """Test project operations."""
        # Create project
        created = self.storage.create_project(
            project_id="test_project",
            name="Test Project",
            created_by="admin",
            description="A test project",
        )
        self.assertTrue(created)
        
        # Get project
        project = self.storage.get_project("test_project")
        self.assertIsNotNone(project)
        self.assertEqual(project["name"], "Test Project")
        
        # Check project exists
        self.assertTrue(self.storage.project_exists("test_project"))
        self.assertFalse(self.storage.project_exists("nonexistent"))

    def test_user_operations(self):
        """Test user operations."""
        # Create user
        created = self.storage.create_user(
            user_id="test_user",
            username="testuser",
            email="test@example.com",
        )
        self.assertTrue(created)
        
        # Get user
        user = self.storage.get_user("test_user")
        self.assertIsNotNone(user)
        self.assertEqual(user["username"], "testuser")
        
        # Check user exists
        self.assertTrue(self.storage.user_exists("test_user"))

    def test_role_operations(self):
        """Test role operations."""
        # Create user and project
        self.storage.create_user(user_id="test_user", username="testuser")
        self.storage.create_project(project_id="test_project", name="Test", created_by="admin")
        
        # Grant role
        granted = self.storage.grant_role(
            user_id="test_user",
            project_id="test_project",
            role_name="writer",
            assigned_by="admin",
        )
        self.assertTrue(granted)
        
        # Get user roles
        roles = self.storage.get_user_roles("test_user", "test_project")
        self.assertIn("writer", roles)
        
        # Check has role
        self.assertTrue(self.storage.has_role("test_user", "test_project", "writer"))
        self.assertFalse(self.storage.has_role("test_user", "test_project", "admin"))


class TestMemoryRecord(unittest.TestCase):
    """Test cases for MemoryRecord dataclass."""

    def test_to_dict(self):
        """Test converting MemoryRecord to dictionary."""
        record = MemoryRecord(
            memory_id="test_001",
            project_id="test_project",
            content="Test content",
            source_refs=["source1"],
            created_at="2024-01-01T00:00:00",
            created_by="test_user",
            tags=["tag1"],
            confidence=0.5,
            status=MemoryStatus.CANDIDATE,
        )
        
        data = record.to_dict()
        
        self.assertEqual(data["memory_id"], "test_001")
        self.assertEqual(data["project_id"], "test_project")
        self.assertEqual(data["content"], "Test content")
        self.assertEqual(data["source_refs"], ["source1"])
        self.assertEqual(data["tags"], ["tag1"])
        self.assertEqual(data["confidence"], 0.5)
        self.assertEqual(data["status"], MemoryStatus.CANDIDATE)




if __name__ == "__main__":
    unittest.main()
