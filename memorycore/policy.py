"""Policy Layer for Memory Core.

Implements project-scoped access control and role-based write permissions.
Enforces security model: Project-scoped access control, role-based write permissions.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class Role(Enum):
    """User roles for access control."""
    ADMIN = "admin"
    WRITER = "writer"
    READER = "reader"
    AUDITOR = "auditor"


class Permission(Enum):
    """Permission types."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    ADMIN = "admin"
    AUDIT = "audit"


@dataclass
class PolicyContext:
    """Context for policy decisions."""
    user_id: str
    project_id: Optional[str] = None
    action: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    roles: List[str] = None
    
    def __post_init__(self):
        if self.roles is None:
            self.roles = []


@dataclass
class PolicyDecision:
    """Result of a policy check."""
    allowed: bool
    reason: str = ""
    required_roles: List[str] = None
    
    def __post_init__(self):
        if self.required_roles is None:
            self.required_roles = []


class PolicyEngine:
    """Policy engine for access control.
    
    Implements role-based access control with project scoping.
    """

    # Role hierarchy: admin > writer > reader
    # auditor is special - only has audit read access
    ROLE_HIERARCHY = {
        Role.ADMIN: 4,
        Role.WRITER: 3,
        Role.READER: 2,
        Role.AUDITOR: 1,
    }

    # Permission matrix: role -> set of permissions
    ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
        Role.ADMIN: {Permission.READ, Permission.WRITE, Permission.DELETE, Permission.ADMIN, Permission.AUDIT},
        Role.WRITER: {Permission.READ, Permission.WRITE},
        Role.READER: {Permission.READ},
        Role.AUDITOR: {Permission.AUDIT},
    }

    # Action to permission mapping
    ACTION_PERMISSION_MAP: Dict[str, Permission] = {
        "search": Permission.READ,
        "write_candidate": Permission.WRITE,
        "get_project_context": Permission.READ,
        "open_raw": Permission.READ,
        "audit": Permission.AUDIT,
        "read": Permission.READ,
        "write": Permission.WRITE,
        "delete": Permission.DELETE,
        "update": Permission.WRITE,
    }

    def __init__(self, storage: Any = None):
        """Initialize policy engine.
        
        Args:
            storage: Storage backend for fetching user roles.
        """
        self.storage = storage

    def check(
        self,
        user_id: str,
        action: str,
        project_id: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> PolicyDecision:
        """Check if a user is allowed to perform an action.
        
        Args:
            user_id: The user ID
            action: The action to perform
            project_id: The project context (optional)
            entity_id: The entity ID (optional)
            
        Returns:
            PolicyDecision with allowed status and reason
        """
        # Map action to permission
        permission = self.ACTION_PERMISSION_MAP.get(action)
        if permission is None:
            return PolicyDecision(
                allowed=False,
                reason=f"Unknown action: {action}",
            )

        # Special case: audit action only requires auditor role
        if action == "audit":
            return self._check_audit_access(user_id, project_id)

        # For project-scoped actions, check project access
        if project_id:
            return self._check_project_access(user_id, project_id, permission)
        
        # For global actions (no project), check if user has admin role globally
        return self._check_global_access(user_id, permission)

    def _check_project_access(
        self,
        user_id: str,
        project_id: str,
        permission: Permission,
    ) -> PolicyDecision:
        """Check access for a project-scoped action."""
        # Get user's roles for this project
        if self.storage:
            roles = self.storage.get_user_roles(user_id, project_id)
        else:
            # For testing without storage, assume no roles
            roles = []
        
        # Check if user has any role for this project
        if not roles:
            return PolicyDecision(
                allowed=False,
                reason=f"User {user_id} has no access to project {project_id}",
                required_roles=self._get_required_roles(permission),
            )
        
        # Check if any role grants the required permission
        for role_name in roles:
            try:
                role = Role(role_name)
                if permission in self.ROLE_PERMISSIONS.get(role, set()):
                    return PolicyDecision(allowed=True)
            except ValueError:
                logger.warning(f"Unknown role: {role_name}")
                continue
        
        return PolicyDecision(
            allowed=False,
            reason=f"User {user_id} lacks permission {permission.value} for project {project_id}",
            required_roles=self._get_required_roles(permission),
        )

    def _check_global_access(
        self,
        user_id: str,
        permission: Permission,
    ) -> PolicyDecision:
        """Check access for global (non-project-scoped) actions."""
        # Only admin has global access
        if permission == Permission.ADMIN:
            if self.storage:
                # Check if user has admin role for any project or globally
                all_roles = self.storage.get_user_roles(user_id)
                if Role.ADMIN.value in all_roles:
                    return PolicyDecision(allowed=True)
            return PolicyDecision(
                allowed=False,
                reason=f"User {user_id} requires admin role for global {permission.value}",
                required_roles=[Role.ADMIN.value],
            )
        
        return PolicyDecision(
            allowed=False,
            reason=f"Global {permission.value} requires project context",
        )

    def _check_audit_access(
        self,
        user_id: str,
        project_id: Optional[str] = None,
    ) -> PolicyDecision:
        """Check access for audit operations."""
        if self.storage:
            if project_id:
                # Check project-level auditor role
                roles = self.storage.get_user_roles(user_id, project_id)
                if Role.AUDITOR.value in roles or Role.ADMIN.value in roles:
                    return PolicyDecision(allowed=True)
            else:
                # Check global auditor access
                all_roles = self.storage.get_user_roles(user_id)
                if Role.AUDITOR.value in all_roles or Role.ADMIN.value in all_roles:
                    return PolicyDecision(allowed=True)
        
        return PolicyDecision(
            allowed=False,
            reason=f"User {user_id} requires auditor or admin role for audit access",
            required_roles=[Role.AUDITOR.value, Role.ADMIN.value],
        )

    def _get_required_roles(self, permission: Permission) -> List[str]:
        """Get roles that have the required permission."""
        required = []
        for role, perms in self.ROLE_PERMISSIONS.items():
            if permission in perms:
                required.append(role.value)
        return sorted(required, key=lambda r: self.ROLE_HIERARCHY.get(Role(r), 0), reverse=True)

    def get_user_permissions(
        self,
        user_id: str,
        project_id: Optional[str] = None,
    ) -> Set[Permission]:
        """Get all permissions for a user in a project context."""
        permissions = set()
        
        if self.storage:
            if project_id:
                roles = self.storage.get_user_roles(user_id, project_id)
            else:
                roles = self.storage.get_user_roles(user_id)
            
            for role_name in roles:
                try:
                    role = Role(role_name)
                    permissions.update(self.ROLE_PERMISSIONS.get(role, set()))
                except ValueError:
                    continue
        
        return permissions

    def is_project_admin(self, user_id: str, project_id: str) -> bool:
        """Check if user is an admin for a project."""
        if self.storage:
            roles = self.storage.get_user_roles(user_id, project_id)
            return Role.ADMIN.value in roles
        return False

    def is_project_writer(self, user_id: str, project_id: str) -> bool:
        """Check if user is a writer for a project."""
        if self.storage:
            roles = self.storage.get_user_roles(user_id, project_id)
            return Role.WRITER.value in roles or Role.ADMIN.value in roles
        return False

    def is_project_reader(self, user_id: str, project_id: str) -> bool:
        """Check if user is a reader for a project."""
        if self.storage:
            roles = self.storage.get_user_roles(user_id, project_id)
            return Role.READER.value in roles or Role.WRITER.value in roles or Role.ADMIN.value in roles
        return False

    def can_write_to_project(self, user_id: str, project_id: str) -> bool:
        """Check if user can write to a project."""
        return self.is_project_writer(user_id, project_id)

    def can_read_from_project(self, user_id: str, project_id: str) -> bool:
        """Check if user can read from a project."""
        return self.is_project_reader(user_id, project_id)

    def validate_project_access(
        self,
        user_id: str,
        project_id: str,
        action: str,
    ) -> Tuple[bool, str]:
        """Validate project access for a specific action.
        
        Returns:
            Tuple of (allowed, reason)
        """
        decision = self.check(user_id, action, project_id)
        return decision.allowed, decision.reason


class PolicyEnforcer:
    """High-level policy enforcer that integrates with storage and audit.
    
    Provides a convenient interface for enforcing policies across the system.
    """

    def __init__(self, storage: Any = None, audit_logger: Any = None):
        """Initialize policy enforcer.
        
        Args:
            storage: Storage backend
            audit_logger: Audit logger for recording policy decisions
        """
        self.engine = PolicyEngine(storage)
        self.storage = storage
        self.audit_logger = audit_logger

    def enforce(
        self,
        user_id: str,
        action: str,
        project_id: Optional[str] = None,
        entity_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """Enforce policy for an action.
        
        Args:
            user_id: The user ID
            action: The action to perform
            project_id: The project context
            entity_id: The entity ID
            context: Additional context
            
        Returns:
            Tuple of (allowed, reason)
        """
        decision = self.engine.check(user_id, action, project_id, entity_id)
        
        # Log the policy decision
        if self.audit_logger:
            self.audit_logger.log(
                action="policy_check",
                entity_type="policy",
                entity_id=f"{user_id}:{action}:{project_id or 'global'}",
                user_id=user_id,
                project_id=project_id,
                details={
                    "allowed": decision.allowed,
                    "reason": decision.reason,
                    "action": action,
                    "context": context,
                },
            )
        
        return decision.allowed, decision.reason

    def require_project_access(
        self,
        user_id: str,
        project_id: str,
        action: str,
    ) -> None:
        """Require project access, raise exception if not allowed.
        
        Args:
            user_id: The user ID
            project_id: The project ID
            action: The action to perform
            
        Raises:
            PermissionError: If access is denied
        """
        allowed, reason = self.enforce(user_id, action, project_id)
        if not allowed:
            raise PermissionError(f"Access denied: {reason}")

    def require_write_access(self, user_id: str, project_id: str) -> None:
        """Require write access to a project.
        
        Raises:
            PermissionError: If write access is denied
        """
        self.require_project_access(user_id, project_id, "write_candidate")

    def require_read_access(self, user_id: str, project_id: str) -> None:
        """Require read access to a project.
        
        Raises:
            PermissionError: If read access is denied
        """
        self.require_project_access(user_id, project_id, "search")
