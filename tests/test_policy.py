"""Tests for Policy module."""

import unittest
from unittest.mock import Mock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.policy import (
    PolicyEngine,
    PolicyEnforcer,
    PolicyContext,
    PolicyDecision,
    Role,
    Permission,
)


class TestPolicyEngine(unittest.TestCase):
    """Test cases for PolicyEngine."""

    def setUp(self):
        """Set up test fixtures."""
        # Create mock storage
        self.mock_storage = Mock()
        self.engine = PolicyEngine(storage=self.mock_storage)

    def test_check_unknown_action(self):
        """Test checking an unknown action."""
        decision = self.engine.check(
            user_id="test_user",
            action="unknown_action",
            project_id="test_project",
        )
        self.assertFalse(decision.allowed)
        self.assertIn("Unknown action", decision.reason)

    def test_check_search_permission(self):
        """Test checking search permission (requires read)."""
        # Mock storage to return roles
        self.mock_storage.get_user_roles.return_value = ["reader"]
        
        decision = self.engine.check(
            user_id="test_user",
            action="search",
            project_id="test_project",
        )
        self.assertTrue(decision.allowed)

    def test_check_write_candidate_permission(self):
        """Test checking write_candidate permission (requires write)."""
        # Mock storage to return roles
        self.mock_storage.get_user_roles.return_value = ["writer"]
        
        decision = self.engine.check(
            user_id="test_user",
            action="write_candidate",
            project_id="test_project",
        )
        self.assertTrue(decision.allowed)

    def test_check_write_candidate_denied(self):
        """Test write_candidate denied for reader."""
        self.mock_storage.get_user_roles.return_value = ["reader"]
        
        decision = self.engine.check(
            user_id="test_user",
            action="write_candidate",
            project_id="test_project",
        )
        self.assertFalse(decision.allowed)

    def test_check_admin_access(self):
        """Test admin has all permissions."""
        self.mock_storage.get_user_roles.return_value = ["admin"]
        
        # Test various actions
        for action in ["search", "write_candidate", "get_project_context", "open_raw"]:
            decision = self.engine.check(
                user_id="test_user",
                action=action,
                project_id="test_project",
            )
            self.assertTrue(decision.allowed, f"Admin should have {action} permission")

    def test_check_audit_access(self):
        """Test audit access requires auditor or admin."""
        # Test with auditor role
        self.mock_storage.get_user_roles.return_value = ["auditor"]
        decision = self.engine.check(
            user_id="test_user",
            action="audit",
            project_id="test_project",
        )
        self.assertTrue(decision.allowed)
        
        # Test with admin role
        self.mock_storage.get_user_roles.return_value = ["admin"]
        decision = self.engine.check(
            user_id="test_user",
            action="audit",
            project_id="test_project",
        )
        self.assertTrue(decision.allowed)
        
        # Test with writer role (should be denied)
        self.mock_storage.get_user_roles.return_value = ["writer"]
        decision = self.engine.check(
            user_id="test_user",
            action="audit",
            project_id="test_project",
        )
        self.assertFalse(decision.allowed)

    def test_check_no_roles(self):
        """Test user with no roles for project."""
        self.mock_storage.get_user_roles.return_value = []
        
        decision = self.engine.check(
            user_id="test_user",
            action="search",
            project_id="test_project",
        )
        self.assertFalse(decision.allowed)
        self.assertIn("no access", decision.reason)

    def test_get_user_permissions(self):
        """Test getting user permissions."""
        self.mock_storage.get_user_roles.return_value = ["writer", "reader"]
        
        permissions = self.engine.get_user_permissions(
            user_id="test_user",
            project_id="test_project",
        )
        
        self.assertIn(Permission.READ, permissions)
        self.assertIn(Permission.WRITE, permissions)
        self.assertNotIn(Permission.DELETE, permissions)

    def test_is_project_admin(self):
        """Test checking if user is project admin."""
        self.mock_storage.get_user_roles.return_value = ["admin"]
        self.assertTrue(self.engine.is_project_admin("test_user", "test_project"))
        
        self.mock_storage.get_user_roles.return_value = ["writer"]
        self.assertFalse(self.engine.is_project_admin("test_user", "test_project"))

    def test_is_project_writer(self):
        """Test checking if user is project writer."""
        self.mock_storage.get_user_roles.return_value = ["writer"]
        self.assertTrue(self.engine.is_project_writer("test_user", "test_project"))
        
        self.mock_storage.get_user_roles.return_value = ["reader"]
        self.assertFalse(self.engine.is_project_writer("test_user", "test_project"))

    def test_is_project_reader(self):
        """Test checking if user is project reader."""
        self.mock_storage.get_user_roles.return_value = ["reader"]
        self.assertTrue(self.engine.is_project_reader("test_user", "test_project"))
        
        self.mock_storage.get_user_roles.return_value = []
        self.assertFalse(self.engine.is_project_reader("test_user", "test_project"))


class TestPolicyEnforcer(unittest.TestCase):
    """Test cases for PolicyEnforcer."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_storage = Mock()
        self.mock_audit = Mock()
        self.enforcer = PolicyEnforcer(
            storage=self.mock_storage,
            audit_logger=self.mock_audit,
        )

    def test_enforce_allowed(self):
        """Test enforcing an allowed action."""
        self.mock_storage.get_user_roles.return_value = ["writer"]
        
        allowed, reason = self.enforcer.enforce(
            user_id="test_user",
            action="write_candidate",
            project_id="test_project",
        )
        
        self.assertTrue(allowed)

    def test_enforce_denied(self):
        """Test enforcing a denied action."""
        self.mock_storage.get_user_roles.return_value = ["reader"]
        
        allowed, reason = self.enforcer.enforce(
            user_id="test_user",
            action="write_candidate",
            project_id="test_project",
        )
        
        self.assertFalse(allowed)

    def test_require_project_access_allowed(self):
        """Test requiring project access when allowed."""
        self.mock_storage.get_user_roles.return_value = ["writer"]
        
        # Should not raise
        self.enforcer.require_project_access(
            user_id="test_user",
            project_id="test_project",
            action="write_candidate",
        )

    def test_require_project_access_denied(self):
        """Test requiring project access when denied."""
        self.mock_storage.get_user_roles.return_value = ["reader"]
        
        with self.assertRaises(PermissionError):
            self.enforcer.require_project_access(
                user_id="test_user",
                project_id="test_project",
                action="write_candidate",
            )

    def test_require_write_access(self):
        """Test requiring write access."""
        self.mock_storage.get_user_roles.return_value = ["writer"]
        
        # Should not raise
        self.enforcer.require_write_access("test_user", "test_project")

    def test_require_write_access_denied(self):
        """Test requiring write access when denied."""
        self.mock_storage.get_user_roles.return_value = ["reader"]
        
        with self.assertRaises(PermissionError):
            self.enforcer.require_write_access("test_user", "test_project")

    def test_require_read_access(self):
        """Test requiring read access."""
        self.mock_storage.get_user_roles.return_value = ["reader"]
        
        # Should not raise
        self.enforcer.require_read_access("test_user", "test_project")


class TestRoleHierarchy(unittest.TestCase):
    """Test role hierarchy and permissions."""

    def test_role_permissions(self):
        """Test role permission mappings."""
        # Admin has all permissions
        admin_perms = PolicyEngine.ROLE_PERMISSIONS[Role.ADMIN]
        self.assertIn(Permission.READ, admin_perms)
        self.assertIn(Permission.WRITE, admin_perms)
        self.assertIn(Permission.DELETE, admin_perms)
        self.assertIn(Permission.ADMIN, admin_perms)
        self.assertIn(Permission.AUDIT, admin_perms)
        
        # Writer has read and write
        writer_perms = PolicyEngine.ROLE_PERMISSIONS[Role.WRITER]
        self.assertIn(Permission.READ, writer_perms)
        self.assertIn(Permission.WRITE, writer_perms)
        self.assertNotIn(Permission.DELETE, writer_perms)
        
        # Reader has only read
        reader_perms = PolicyEngine.ROLE_PERMISSIONS[Role.READER]
        self.assertIn(Permission.READ, reader_perms)
        self.assertNotIn(Permission.WRITE, reader_perms)
        
        # Auditor has only audit
        auditor_perms = PolicyEngine.ROLE_PERMISSIONS[Role.AUDITOR]
        self.assertIn(Permission.AUDIT, auditor_perms)
        self.assertNotIn(Permission.READ, auditor_perms)

    def test_action_permission_map(self):
        """Test action to permission mapping."""
        mapping = PolicyEngine.ACTION_PERMISSION_MAP
        
        self.assertEqual(mapping["search"], Permission.READ)
        self.assertEqual(mapping["write_candidate"], Permission.WRITE)
        self.assertEqual(mapping["get_project_context"], Permission.READ)
        self.assertEqual(mapping["open_raw"], Permission.READ)
        self.assertEqual(mapping["audit"], Permission.AUDIT)


if __name__ == "__main__":
    unittest.main()
