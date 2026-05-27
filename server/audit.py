"""Append-only Audit Trail for Memory Core.

Provides immutable audit logging for all read/write operations.
Integrates with storage layer to record all memory operations.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger(__name__)


class AuditAction(Enum):
    """Audit action types."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    UPDATE = "update"


class AuditEntityType(Enum):
    """Entity types for audit logging."""
    MEMORY = "memory"
    PROJECT = "project"
    CONFIG = "config"
    USER = "user"


@dataclass
class AuditEntry:
    """Represents an audit log entry."""
    audit_id: str
    timestamp: str
    action: AuditAction
    entity_type: AuditEntityType
    entity_id: str
    project_id: Optional[str] = None
    user_id: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "audit_id": self.audit_id,
            "timestamp": self.timestamp,
            "action": self.action.value,
            "entity_type": self.entity_type.value,
            "entity_id": self.entity_id,
            "project_id": self.project_id,
            "user_id": self.user_id,
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
        }


class AuditLogger:
    """Append-only audit logger.
    
    Records all operations on memory records and other entities.
    Integrates with the storage layer for persistence.
    """

    def __init__(self, storage: Any = None):
        """Initialize audit logger.
        
        Args:
            storage: Optional storage backend for persistence.
                    If None, logs are kept in memory only.
        """
        self.storage = storage
        self._in_memory_logs: List[AuditEntry] = []

    def log(
        self,
        action: AuditAction,
        entity_type: AuditEntityType,
        entity_id: str,
        user_id: str = "",
        project_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditEntry:
        """Log an audit entry.
        
        Args:
            action: The action being performed
            entity_type: The type of entity being acted upon
            entity_id: The ID of the entity
            user_id: The user performing the action
            project_id: The project context (if applicable)
            details: Additional details about the action
            ip_address: Client IP address
            user_agent: Client user agent
            
        Returns:
            The created AuditEntry
        """
        entry = AuditEntry(
            audit_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow().isoformat(),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            project_id=project_id,
            user_id=user_id,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        # Store in memory
        self._in_memory_logs.append(entry)
        
        # Persist to storage if available
        if self.storage:
            try:
                self.storage.log_audit(
                    action=action.value if hasattr(action, 'value') else action,
                    entity_type=entity_type.value if hasattr(entity_type, 'value') else entity_type,
                    entity_id=entity_id,
                    user_id=user_id,
                    project_id=project_id,
                    details=details,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            except Exception as e:
                logger.error(f"Failed to persist audit log: {e}")
        
        action_str = action.value if hasattr(action, 'value') else action
        entity_type_str = entity_type.value if hasattr(entity_type, 'value') else entity_type
        logger.debug(f"Audit: {action_str} on {entity_type_str}:{entity_id} by {user_id}")
        
        return entry

    def log_memory_read(
        self,
        memory_id: str,
        user_id: str,
        project_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        """Log a memory read operation."""
        return self.log(
            action=AuditAction.READ,
            entity_type=AuditEntityType.MEMORY,
            entity_id=memory_id,
            user_id=user_id,
            project_id=project_id,
            details=details,
        )

    def log_memory_write(
        self,
        memory_id: str,
        user_id: str,
        project_id: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        """Log a memory write operation."""
        return self.log(
            action=AuditAction.WRITE,
            entity_type=AuditEntityType.MEMORY,
            entity_id=memory_id,
            user_id=user_id,
            project_id=project_id,
            details=details,
        )

    def log_memory_update(
        self,
        memory_id: str,
        user_id: str,
        project_id: str,
        changes: Dict[str, Any],
    ) -> AuditEntry:
        """Log a memory update operation."""
        return self.log(
            action=AuditAction.UPDATE,
            entity_type=AuditEntityType.MEMORY,
            entity_id=memory_id,
            user_id=user_id,
            project_id=project_id,
            details={"changes": changes},
        )

    def log_memory_delete(
        self,
        memory_id: str,
        user_id: str,
        project_id: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        """Log a memory delete operation."""
        return self.log(
            action=AuditAction.DELETE,
            entity_type=AuditEntityType.MEMORY,
            entity_id=memory_id,
            user_id=user_id,
            project_id=project_id,
            details=details,
        )

    def log_search(
        self,
        user_id: str,
        project_id: Optional[str] = None,
        query: Optional[str] = None,
        results_count: int = 0,
    ) -> AuditEntry:
        """Log a search operation."""
        return self.log(
            action=AuditAction.READ,
            entity_type=AuditEntityType.MEMORY,
            entity_id="search",
            user_id=user_id,
            project_id=project_id,
            details={
                "query": query,
                "results_count": results_count,
            },
        )

    def log_project_context(
        self,
        project_id: str,
        user_id: str,
        memories_count: int = 0,
    ) -> AuditEntry:
        """Log a get_project_context operation."""
        return self.log(
            action=AuditAction.READ,
            entity_type=AuditEntityType.PROJECT,
            entity_id=project_id,
            user_id=user_id,
            project_id=project_id,
            details={"memories_count": memories_count},
        )

    def log_open_raw(
        self,
        memory_id: str,
        user_id: str,
        project_id: str,
    ) -> AuditEntry:
        """Log an open_raw operation."""
        return self.log(
            action=AuditAction.READ,
            entity_type=AuditEntityType.MEMORY,
            entity_id=memory_id,
            user_id=user_id,
            project_id=project_id,
            details={"operation": "open_raw"},
        )

    def get_logs(
        self,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
        action: Optional[AuditAction] = None,
        limit: int = 100,
    ) -> List[AuditEntry]:
        """Get audit log entries.
        
        If storage is configured, fetches from storage.
        Otherwise returns in-memory logs.
        """
        if self.storage:
            # Fetch from storage
            action_str = action.value if action else None
            logs, _ = self.storage.get_audit_logs(
                project_id=project_id,
                user_id=user_id,
                action=action_str,
                limit=limit,
            )
            return [
                AuditEntry(
                    audit_id=str(log.audit_id),
                    timestamp=log.timestamp,
                    action=AuditAction(log.action),
                    entity_type=AuditEntityType(log.entity_type),
                    entity_id=log.entity_id,
                    project_id=log.project_id,
                    user_id=log.user_id,
                    details=log.details,
                    ip_address=log.ip_address,
                    user_agent=log.user_agent,
                )
                for log in logs
            ]
        else:
            # Return in-memory logs with filtering
            logs = self._in_memory_logs
            
            if project_id:
                logs = [l for l in logs if l.project_id == project_id]
            if user_id:
                logs = [l for l in logs if l.user_id == user_id]
            if action:
                logs = [l for l in logs if l.action == action]
            
            return logs[:limit]

    def clear_in_memory(self) -> None:
        """Clear in-memory logs (for testing)."""
        self._in_memory_logs.clear()
