"""JSONL Audit Trail for Memory Core.

Provides append-only audit logging in JSONL format for all memory operations.
This is the primary audit implementation for the new CozoDB-based architecture.
"""

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import logging

logger = logging.getLogger(__name__)


class AuditAction(Enum):
    """Audit action types."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    UPDATE = "update"
    SEARCH = "search"
    SUPERSEDE = "supersede"
    CONTRADICT = "contradict"
    RESOLVE = "resolve"


class AuditEntityType(Enum):
    """Entity types for audit logging."""
    MEMORY = "memory"
    PROJECT = "project"
    SOURCE = "source"
    LINK = "link"
    CHAIN = "chain"


@dataclass
class AuditEntry:
    """Represents an audit log entry."""
    audit_id: str
    timestamp: str
    action: str
    entity_type: str
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
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "project_id": self.project_id,
            "user_id": self.user_id,
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditEntry":
        """Create AuditEntry from dictionary."""
        return cls(
            audit_id=data.get("audit_id", ""),
            timestamp=data.get("timestamp", ""),
            action=data.get("action", ""),
            entity_type=data.get("entity_type", ""),
            entity_id=data.get("entity_id", ""),
            project_id=data.get("project_id"),
            user_id=data.get("user_id", ""),
            details=data.get("details", {}),
            ip_address=data.get("ip_address"),
            user_agent=data.get("user_agent"),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "AuditEntry":
        """Create AuditEntry from JSON string."""
        return cls.from_dict(json.loads(json_str))


class JSONLAuditLogger:
    """Append-only audit logger using JSONL format.
    
    Writes each audit entry as a single line in a JSONL file.
    Supports file rotation and querying of audit logs.
    """

    def __init__(
        self,
        log_path: str = "audit.jsonl",
        max_file_size: int = 10 * 1024 * 1024,  # 10MB default
        max_files: int = 10,
    ):
        """Initialize JSONL audit logger.
        
        Args:
            log_path: Path to the audit log file
            max_file_size: Maximum size of each log file before rotation
            max_files: Maximum number of rotated log files to keep
        """
        self.log_path = Path(log_path)
        self.max_file_size = max_file_size
        self.max_files = max_files
        self._file_handle = None
        
        # Ensure directory exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Open file in append mode
        self._open_file()

    def _open_file(self) -> None:
        """Open the audit log file in append mode."""
        try:
            self._file_handle = open(self.log_path, 'a', encoding='utf-8')
        except Exception as e:
            logger.error(f"Failed to open audit log file: {e}")
            raise

    def _close_file(self) -> None:
        """Close the audit log file."""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None

    def _rotate_if_needed(self) -> None:
        """Rotate log file if it exceeds max size."""
        if not self._file_handle:
            return
        
        try:
            # Get current file size
            self._file_handle.flush()
            file_size = self.log_path.stat().st_size
            
            if file_size >= self.max_file_size:
                self._close_file()
                
                # Rotate files
                for i in range(self.max_files - 1, 0, -1):
                    old_path = self.log_path.with_suffix(f".{i}.jsonl")
                    new_path = self.log_path.with_suffix(f".{i + 1}.jsonl")
                    if old_path.exists():
                        if new_path.exists():
                            new_path.unlink()
                        old_path.rename(new_path)
                
                # Rename current to .1.jsonl
                rotated_path = self.log_path.with_suffix(".1.jsonl")
                if rotated_path.exists():
                    rotated_path.unlink()
                self.log_path.rename(rotated_path)
                
                # Open new file
                self._open_file()
                logger.info(f"Rotated audit log file")
        except Exception as e:
            logger.error(f"Failed to rotate audit log: {e}")

    def log(
        self,
        action: str,
        entity_type: str,
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
        
        # Write to file
        try:
            self._rotate_if_needed()
            self._file_handle.write(entry.to_json() + '\n')
            self._file_handle.flush()
            
            logger.debug(f"Audit: {action} on {entity_type}:{entity_id} by {user_id}")
            return entry
            
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
            raise

    def log_memory_read(
        self,
        memory_id: str,
        user_id: str,
        project_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        """Log a memory read operation."""
        return self.log(
            action=AuditAction.READ.value,
            entity_type=AuditEntityType.MEMORY.value,
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
            action=AuditAction.WRITE.value,
            entity_type=AuditEntityType.MEMORY.value,
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
            action=AuditAction.UPDATE.value,
            entity_type=AuditEntityType.MEMORY.value,
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
            action=AuditAction.DELETE.value,
            entity_type=AuditEntityType.MEMORY.value,
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
            action=AuditAction.SEARCH.value,
            entity_type=AuditEntityType.MEMORY.value,
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
            action=AuditAction.READ.value,
            entity_type=AuditEntityType.PROJECT.value,
            entity_id=project_id,
            user_id=user_id,
            project_id=project_id,
            details={"memories_count": memories_count},
        )

    def log_supersede(
        self,
        chain_id: str,
        user_id: str,
        project_id: str,
        old_memory_id: str,
        new_memory_id: str,
        reason: str,
    ) -> AuditEntry:
        """Log a supersede operation."""
        return self.log(
            action=AuditAction.SUPERSEDE.value,
            entity_type=AuditEntityType.CHAIN.value,
            entity_id=chain_id,
            user_id=user_id,
            project_id=project_id,
            details={
                "old_memory_id": old_memory_id,
                "new_memory_id": new_memory_id,
                "reason": reason,
            },
        )

    def log_contradict(
        self,
        chain_id: str,
        user_id: str,
        project_id: str,
        memory_a_id: str,
        memory_b_id: str,
        resolution_notes: str,
    ) -> AuditEntry:
        """Log a contradict operation."""
        return self.log(
            action=AuditAction.CONTRADICT.value,
            entity_type=AuditEntityType.CHAIN.value,
            entity_id=chain_id,
            user_id=user_id,
            project_id=project_id,
            details={
                "memory_a_id": memory_a_id,
                "memory_b_id": memory_b_id,
                "resolution_notes": resolution_notes,
            },
        )

    def get_logs(
        self,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        entity_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEntry]:
        """Get audit log entries with filters.
        
        Args:
            project_id: Filter by project ID
            user_id: Filter by user ID
            action: Filter by action type
            entity_type: Filter by entity type
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            List of AuditEntry objects
        """
        entries = []
        
        # Read all log files (current and rotated)
        log_files = [self.log_path]
        i = 1
        while True:
            rotated_path = self.log_path.with_suffix(f".{i}.jsonl")
            if rotated_path.exists():
                log_files.append(rotated_path)
                i += 1
            else:
                break
        
        # Read files in reverse order (newest first)
        for log_file in reversed(log_files):
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        
                        try:
                            entry = AuditEntry.from_json(line)
                            
                            # Apply filters
                            if project_id and entry.project_id != project_id:
                                continue
                            if user_id and entry.user_id != user_id:
                                continue
                            if action and entry.action != action:
                                continue
                            if entity_type and entry.entity_type != entity_type:
                                continue
                            
                            entries.append(entry)
                        except Exception as e:
                            logger.warning(f"Failed to parse audit entry: {e}")
                            continue
            except Exception as e:
                logger.error(f"Failed to read audit log file {log_file}: {e}")
                continue
        
        # Sort by timestamp (newest first) and apply pagination
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        
        return entries[offset:offset + limit]

    def get_logs_count(
        self,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        entity_type: Optional[str] = None,
    ) -> int:
        """Get the count of audit log entries matching filters.
        
        Args:
            project_id: Filter by project ID
            user_id: Filter by user ID
            action: Filter by action type
            entity_type: Filter by entity type
            
        Returns:
            Count of matching entries
        """
        count = 0
        
        # Read all log files
        log_files = [self.log_path]
        i = 1
        while True:
            rotated_path = self.log_path.with_suffix(f".{i}.jsonl")
            if rotated_path.exists():
                log_files.append(rotated_path)
                i += 1
            else:
                break
        
        for log_file in log_files:
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        
                        try:
                            entry = AuditEntry.from_json(line)
                            
                            # Apply filters
                            if project_id and entry.project_id != project_id:
                                continue
                            if user_id and entry.user_id != user_id:
                                continue
                            if action and entry.action != action:
                                continue
                            if entity_type and entry.entity_type != entity_type:
                                continue
                            
                            count += 1
                        except Exception as e:
                            logger.warning(f"Failed to parse audit entry: {e}")
                            continue
            except Exception as e:
                logger.error(f"Failed to read audit log file {log_file}: {e}")
                continue
        
        return count

    def get_logs_with_total(
        self,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        entity_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[AuditEntry], int]:
        """Get audit log entries with total count.
        
        Args:
            project_id: Filter by project ID
            user_id: Filter by user ID
            action: Filter by action type
            entity_type: Filter by entity type
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            Tuple of (entries, total_count)
        """
        entries = self.get_logs(
            project_id=project_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            limit=limit,
            offset=offset,
        )
        
        total = self.get_logs_count(
            project_id=project_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
        )
        
        return entries, total

    def close(self) -> None:
        """Close the audit logger."""
        self._close_file()
        logger.info("JSONL audit logger closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        """Destructor to ensure file is closed."""
        self.close()
