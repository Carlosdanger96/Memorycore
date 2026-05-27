"""Tests for Audit module."""

import os
import tempfile
import unittest
from unittest.mock import Mock

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.audit import AuditLogger, AuditEntry, AuditAction, AuditEntityType
from server.storage import Storage


class TestAuditLogger(unittest.TestCase):
    """Test cases for AuditLogger."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_memorycore.db")
        
        self.storage = Storage(db_path=self.db_path)
        self.audit_logger = AuditLogger(storage=self.storage)

    def tearDown(self):
        """Clean up test fixtures."""
        self.storage.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        os.rmdir(self.temp_dir)

    def test_log_memory_read(self):
        """Test logging a memory read operation."""
        entry = self.audit_logger.log_memory_read(
            memory_id="test_001",
            user_id="test_user",
            project_id="test_project",
        )
        
        self.assertEqual(entry.action, AuditAction.READ)
        self.assertEqual(entry.entity_type, AuditEntityType.MEMORY)
        self.assertEqual(entry.entity_id, "test_001")
        self.assertEqual(entry.user_id, "test_user")
        self.assertEqual(entry.project_id, "test_project")

    def test_log_memory_write(self):
        """Test logging a memory write operation."""
        entry = self.audit_logger.log_memory_write(
            memory_id="test_001",
            user_id="test_user",
            project_id="test_project",
        )
        
        self.assertEqual(entry.action, AuditAction.WRITE)
        self.assertEqual(entry.entity_type, AuditEntityType.MEMORY)
        self.assertEqual(entry.entity_id, "test_001")

    def test_log_memory_update(self):
        """Test logging a memory update operation."""
        entry = self.audit_logger.log_memory_update(
            memory_id="test_001",
            user_id="test_user",
            project_id="test_project",
            changes={"status": "accepted"},
        )
        
        self.assertEqual(entry.action, AuditAction.UPDATE)
        self.assertEqual(entry.details["changes"], {"status": "accepted"})

    def test_log_memory_delete(self):
        """Test logging a memory delete operation."""
        entry = self.audit_logger.log_memory_delete(
            memory_id="test_001",
            user_id="test_user",
            project_id="test_project",
        )
        
        self.assertEqual(entry.action, AuditAction.DELETE)

    def test_log_search(self):
        """Test logging a search operation."""
        entry = self.audit_logger.log_search(
            user_id="test_user",
            project_id="test_project",
            query="test query",
            results_count=10,
        )
        
        self.assertEqual(entry.action, AuditAction.READ)
        self.assertEqual(entry.entity_id, "search")
        self.assertEqual(entry.details["query"], "test query")
        self.assertEqual(entry.details["results_count"], 10)

    def test_log_project_context(self):
        """Test logging a get_project_context operation."""
        entry = self.audit_logger.log_project_context(
            project_id="test_project",
            user_id="test_user",
            memories_count=5,
        )
        
        self.assertEqual(entry.action, AuditAction.READ)
        self.assertEqual(entry.entity_type, AuditEntityType.PROJECT)
        self.assertEqual(entry.entity_id, "test_project")
        self.assertEqual(entry.details["memories_count"], 5)

    def test_log_open_raw(self):
        """Test logging an open_raw operation."""
        entry = self.audit_logger.log_open_raw(
            memory_id="test_001",
            user_id="test_user",
            project_id="test_project",
        )
        
        self.assertEqual(entry.action, AuditAction.READ)
        self.assertEqual(entry.details["operation"], "open_raw")

    def test_get_logs_from_storage(self):
        """Test getting logs from storage."""
        # Log some entries
        self.audit_logger.log_memory_write(
            memory_id="test_001",
            user_id="test_user",
            project_id="test_project",
        )
        self.audit_logger.log_memory_read(
            memory_id="test_001",
            user_id="test_user",
            project_id="test_project",
        )
        
        # Get logs
        logs = self.audit_logger.get_logs(project_id="test_project")
        
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0].action, AuditAction.WRITE)
        self.assertEqual(logs[1].action, AuditAction.READ)

    def test_get_logs_filtered(self):
        """Test getting filtered logs."""
        # Log entries for different users
        self.audit_logger.log_memory_write(
            memory_id="test_001",
            user_id="user1",
            project_id="test_project",
        )
        self.audit_logger.log_memory_write(
            memory_id="test_002",
            user_id="user2",
            project_id="test_project",
        )
        
        # Get logs for user1 only
        logs = self.audit_logger.get_logs(user_id="user1")
        
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].user_id, "user1")

    def test_clear_in_memory(self):
        """Test clearing in-memory logs."""
        # Log some entries
        self.audit_logger.log_memory_write(
            memory_id="test_001",
            user_id="test_user",
            project_id="test_project",
        )
        
        # Clear in-memory logs
        self.audit_logger.clear_in_memory()
        
        # Get logs (should still work from storage)
        logs = self.audit_logger.get_logs()
        self.assertEqual(len(logs), 1)


class TestAuditLoggerWithoutStorage(unittest.TestCase):
    """Test AuditLogger without storage backend."""

    def setUp(self):
        """Set up test fixtures without storage."""
        self.audit_logger = AuditLogger(storage=None)

    def test_log_without_storage(self):
        """Test logging without storage."""
        entry = self.audit_logger.log(
            action=AuditAction.WRITE,
            entity_type=AuditEntityType.MEMORY,
            entity_id="test_001",
            user_id="test_user",
        )
        
        self.assertIsNotNone(entry)
        self.assertEqual(entry.action, AuditAction.WRITE)

    def test_get_logs_without_storage(self):
        """Test getting logs without storage."""
        self.audit_logger.log(
            action=AuditAction.WRITE,
            entity_type=AuditEntityType.MEMORY,
            entity_id="test_001",
            user_id="test_user",
        )
        self.audit_logger.log(
            action=AuditAction.READ,
            entity_type=AuditEntityType.MEMORY,
            entity_id="test_002",
            user_id="test_user",
        )
        
        logs = self.audit_logger.get_logs()
        
        self.assertEqual(len(logs), 2)


class TestAuditEntry(unittest.TestCase):
    """Test AuditEntry dataclass."""

    def test_to_dict(self):
        """Test converting AuditEntry to dictionary."""
        entry = AuditEntry(
            audit_id="test_001",
            timestamp="2024-01-01T00:00:00",
            action=AuditAction.WRITE,
            entity_type=AuditEntityType.MEMORY,
            entity_id="memory_001",
            project_id="test_project",
            user_id="test_user",
            details={"test": "value"},
            ip_address="127.0.0.1",
            user_agent="Test Agent",
        )
        
        data = entry.to_dict()
        
        self.assertEqual(data["audit_id"], "test_001")
        self.assertEqual(data["action"], "write")
        self.assertEqual(data["entity_type"], "memory")
        self.assertEqual(data["entity_id"], "memory_001")
        self.assertEqual(data["project_id"], "test_project")
        self.assertEqual(data["user_id"], "test_user")
        self.assertEqual(data["details"], {"test": "value"})
        self.assertEqual(data["ip_address"], "127.0.0.1")
        self.assertEqual(data["user_agent"], "Test Agent")


if __name__ == "__main__":
    unittest.main()
