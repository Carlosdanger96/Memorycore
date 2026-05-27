"""Tests for MemoryController with CozoDB backend."""

import os
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "server"))

from controller import MemoryController, MemoryRecord, MemoryStatus, MemoryType
from audit_jsonl import JSONLAuditLogger


class TestMemoryController(unittest.TestCase):
    """Test cases for MemoryController."""

    def setUp(self):
        """Set up test fixtures."""
        # Create temporary directory for test database
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_memorycore.cozo")
        self.schema_path = os.path.join(
            Path(__file__).parent.parent, "cozodb", "schema.cozo"
        )
        self.audit_path = os.path.join(self.test_dir, "test_audit.jsonl")
        
        # Initialize audit logger
        self.audit_logger = JSONLAuditLogger(log_path=self.audit_path)
        
        # Initialize controller
        self.controller = MemoryController(
            db_path=self.db_path,
            schema_path=self.schema_path,
            audit_logger=self.audit_logger,
        )

    def tearDown(self):
        """Clean up test fixtures."""
        self.controller.close()
        self.audit_logger.close()
        
        # Clean up temporary files
        for file in os.listdir(self.test_dir):
            os.remove(os.path.join(self.test_dir, file))
        os.rmdir(self.test_dir)

    def test_health_check(self):
        """Test database health check."""
        health = self.controller.health_check()
        self.assertEqual(health["status"], "healthy")
        self.assertIn("database", health)

    def test_create_project(self):
        """Test creating a project."""
        result = self.controller.create_project(
            project_id="test_project",
            name="Test Project",
            description="A test project",
            created_by="test_user",
        )
        
        self.assertEqual(result["project_id"], "test_project")
        self.assertEqual(result["name"], "Test Project")

    def test_add_memory(self):
        """Test adding a memory."""
        # First create a project
        self.controller.create_project(
            project_id="test_project",
            name="Test Project",
            created_by="test_user",
        )
        
        # Add a memory
        record = self.controller.add_memory(
            project_id="test_project",
            content="This is a test memory",
            created_by="test_user",
            tags=["test", "memory"],
            confidence=0.9,
            memory_type=MemoryType.FACT,
            status=MemoryStatus.CANDIDATE,
        )
        
        self.assertIsNotNone(record.memory_id)
        self.assertEqual(record.project_id, "test_project")
        self.assertEqual(record.content, "This is a test memory")
        self.assertEqual(record.created_by, "test_user")
        self.assertEqual(record.tags, ["test", "memory"])
        self.assertEqual(record.confidence, 0.9)
        self.assertEqual(record.memory_type, MemoryType.FACT)
        self.assertEqual(record.status, MemoryStatus.CANDIDATE)

    def test_get_memory(self):
        """Test getting a memory by ID."""
        # Create project and add memory
        self.controller.create_project(
            project_id="test_project",
            name="Test Project",
            created_by="test_user",
        )
        
        record = self.controller.add_memory(
            project_id="test_project",
            content="Test memory",
            created_by="test_user",
        )
        
        # Get the memory
        retrieved = self.controller.get_memory(record.memory_id)
        
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.memory_id, record.memory_id)
        self.assertEqual(retrieved.content, "Test memory")

    def test_get_memory_not_found(self):
        """Test getting a non-existent memory."""
        result = self.controller.get_memory("nonexistent_id")
        self.assertIsNone(result)

    def test_list_by_project(self):
        """Test listing memories by project."""
        # Create project
        self.controller.create_project(
            project_id="test_project",
            name="Test Project",
            created_by="test_user",
        )
        
        # Add multiple memories
        for i in range(5):
            self.controller.add_memory(
                project_id="test_project",
                content=f"Test memory {i}",
                created_by="test_user",
            )
        
        # List memories
        result = self.controller.list_by_project(
            project_id="test_project",
            limit=10,
        )
        
        self.assertEqual(result.total, 5)
        self.assertEqual(len(result.results), 5)

    def test_search_memories(self):
        """Test searching memories with FTS."""
        # Create project
        self.controller.create_project(
            project_id="test_project",
            name="Test Project",
            created_by="test_user",
        )
        
        # Add memories with different content
        self.controller.add_memory(
            project_id="test_project",
            content="This is about Python programming",
            created_by="test_user",
            tags=["python", "programming"],
        )
        
        self.controller.add_memory(
            project_id="test_project",
            content="This is about JavaScript programming",
            created_by="test_user",
            tags=["javascript", "programming"],
        )
        
        self.controller.add_memory(
            project_id="test_project",
            content="This is about cooking recipes",
            created_by="test_user",
            tags=["cooking", "recipes"],
        )
        
        # Search for "Python"
        result = self.controller.search_memories(
            query="Python",
            project_id="test_project",
        )
        
        self.assertGreaterEqual(result.total, 1)
        # Check that we got the Python memory
        python_memories = [r for r in result.results if "Python" in r.content]
        self.assertGreater(len(python_memories), 0)

    def test_search_with_tags(self):
        """Test searching memories by tags."""
        # Create project
        self.controller.create_project(
            project_id="test_project",
            name="Test Project",
            created_by="test_user",
        )
        
        # Add memories with different tags
        self.controller.add_memory(
            project_id="test_project",
            content="Memory with tag1",
            created_by="test_user",
            tags=["tag1", "common"],
        )
        
        self.controller.add_memory(
            project_id="test_project",
            content="Memory with tag2",
            created_by="test_user",
            tags=["tag2", "common"],
        )
        
        # Search for tag1
        result = self.controller.search_memories(
            tags=["tag1"],
            project_id="test_project",
        )
        
        self.assertEqual(result.total, 1)
        self.assertEqual(len(result.results), 1)
        self.assertIn("tag1", result.results[0].tags)

    def test_supersede(self):
        """Test creating a supersession chain."""
        # Create project and memories
        self.controller.create_project(
            project_id="test_project",
            name="Test Project",
            created_by="test_user",
        )
        
        old_memory = self.controller.add_memory(
            project_id="test_project",
            content="Old memory",
            created_by="test_user",
        )
        
        new_memory = self.controller.add_memory(
            project_id="test_project",
            content="New memory",
            created_by="test_user",
        )
        
        # Create supersession chain
        result = self.controller.supersede(
            old_memory_id=old_memory.memory_id,
            new_memory_id=new_memory.memory_id,
            reason="Updated information",
            created_by="test_user",
        )
        
        self.assertIn("chain_id", result)
        self.assertEqual(result["old_memory_id"], old_memory.memory_id)
        self.assertEqual(result["new_memory_id"], new_memory.memory_id)
        self.assertEqual(result["reason"], "Updated information")

    def test_contradict(self):
        """Test creating a contradiction chain."""
        # Create project and memories
        self.controller.create_project(
            project_id="test_project",
            name="Test Project",
            created_by="test_user",
        )
        
        memory_a = self.controller.add_memory(
            project_id="test_project",
            content="Memory A says X is true",
            created_by="test_user",
        )
        
        memory_b = self.controller.add_memory(
            project_id="test_project",
            content="Memory B says X is false",
            created_by="test_user",
        )
        
        # Create contradiction chain
        result = self.controller.contradict(
            memory_a_id=memory_a.memory_id,
            memory_b_id=memory_b.memory_id,
            resolution_notes="These memories contradict each other",
            created_by="test_user",
        )
        
        self.assertIn("chain_id", result)
        self.assertEqual(result["memory_a_id"], memory_a.memory_id)
        self.assertEqual(result["memory_b_id"], memory_b.memory_id)

    def test_retrieve_context(self):
        """Test retrieving project context."""
        # Create project
        self.controller.create_project(
            project_id="test_project",
            name="Test Project",
            description="A test project",
            created_by="test_user",
        )
        
        # Add memories
        for i in range(3):
            self.controller.add_memory(
                project_id="test_project",
                content=f"Memory {i}",
                created_by="test_user",
                tags=[f"tag{i}", "common"],
                status=MemoryStatus.ACCEPTED if i % 2 == 0 else MemoryStatus.CANDIDATE,
            )
        
        # Retrieve context
        context = self.controller.retrieve_context(
            project_id="test_project",
            limit=10,
        )
        
        self.assertEqual(context.project_id, "test_project")
        self.assertEqual(context.project_name, "Test Project")
        self.assertEqual(context.memory_count, 3)
        self.assertEqual(context.accepted_count, 2)  # 2 accepted, 1 candidate
        self.assertEqual(context.candidate_count, 1)
        self.assertEqual(len(context.recent_memories), 3)
        self.assertIn("common", context.tags)

    def test_update_memory(self):
        """Test updating a memory."""
        # Create project and memory
        self.controller.create_project(
            project_id="test_project",
            name="Test Project",
            created_by="test_user",
        )
        
        record = self.controller.add_memory(
            project_id="test_project",
            content="Original content",
            created_by="test_user",
            status=MemoryStatus.CANDIDATE,
        )
        
        # Update the memory
        updated = self.controller.update_memory(
            memory_id=record.memory_id,
            updates={"content": "Updated content", "status": MemoryStatus.ACCEPTED},
            user_id="test_user",
        )
        
        self.assertIsNotNone(updated)
        self.assertEqual(updated.content, "Updated content")
        self.assertEqual(updated.status, MemoryStatus.ACCEPTED)
        self.assertEqual(updated.version, 2)  # Version should be incremented

    def test_delete_memory(self):
        """Test deleting a memory."""
        # Create project and memory
        self.controller.create_project(
            project_id="test_project",
            name="Test Project",
            created_by="test_user",
        )
        
        record = self.controller.add_memory(
            project_id="test_project",
            content="To be deleted",
            created_by="test_user",
        )
        
        # Delete the memory
        result = self.controller.delete_memory(
            memory_id=record.memory_id,
            user_id="test_user",
        )
        
        self.assertTrue(result)
        
        # Verify it's gone
        retrieved = self.controller.get_memory(record.memory_id)
        self.assertIsNone(retrieved)


class TestMemoryRecord(unittest.TestCase):
    """Test cases for MemoryRecord dataclass."""

    def test_to_dict(self):
        """Test converting MemoryRecord to dictionary."""
        record = MemoryRecord(
            memory_id="test_id",
            project_id="test_project",
            content="Test content",
            created_by="test_user",
        )
        
        data = record.to_dict()
        
        self.assertEqual(data["memory_id"], "test_id")
        self.assertEqual(data["project_id"], "test_project")
        self.assertEqual(data["content"], "Test content")
        self.assertEqual(data["created_by"], "test_user")

    def test_from_dict(self):
        """Test creating MemoryRecord from dictionary."""
        data = {
            "memory_id": "test_id",
            "project_id": "test_project",
            "content": "Test content",
            "created_by": "test_user",
            "tags": ["tag1", "tag2"],
            "confidence": 0.8,
        }
        
        record = MemoryRecord.from_dict(data)
        
        self.assertEqual(record.memory_id, "test_id")
        self.assertEqual(record.project_id, "test_project")
        self.assertEqual(record.content, "Test content")
        self.assertEqual(record.created_by, "test_user")
        self.assertEqual(record.tags, ["tag1", "tag2"])
        self.assertEqual(record.confidence, 0.8)


if __name__ == "__main__":
    unittest.main()
