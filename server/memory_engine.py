"""Memory Engine for Memory Core.

Core memory operations implementing the memory schema:
- memory_id, project_id, content, source_refs, created_at, created_by, tags, confidence, status

Provides the business logic layer between MCP Gateway and Storage.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import logging

logger = logging.getLogger(__name__)


# Memory status constants
class MemoryStatus:
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    ARCHIVED = "archived"


@dataclass
class MemoryRecord:
    """Memory record data structure."""
    memory_id: str
    project_id: str
    content: str
    source_refs: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_by: str = ""
    tags: List[str] = field(default_factory=list)
    confidence: float = 0.0
    status: str = MemoryStatus.CANDIDATE

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "memory_id": self.memory_id,
            "project_id": self.project_id,
            "content": self.content,
            "source_refs": self.source_refs,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "tags": self.tags,
            "confidence": self.confidence,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryRecord":
        """Create MemoryRecord from dictionary."""
        return cls(
            memory_id=data.get("memory_id", str(uuid.uuid4())),
            project_id=data["project_id"],
            content=data["content"],
            source_refs=data.get("source_refs", []),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            created_by=data.get("created_by", ""),
            tags=data.get("tags", []),
            confidence=data.get("confidence", 0.0),
            status=data.get("status", MemoryStatus.CANDIDATE),
        )


@dataclass
class SearchResult:
    """Search result with pagination."""
    results: List[MemoryRecord]
    total: int
    limit: int
    offset: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "results": [r.to_dict() for r in self.results],
            "total": self.total,
            "limit": self.limit,
            "offset": self.offset,
        }


@dataclass
class ProjectContext:
    """Project context with aggregated memory information."""
    project_id: str
    project_name: str
    memory_count: int
    accepted_count: int
    candidate_count: int
    archived_count: int
    recent_memories: List[MemoryRecord]
    tags: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "memory_count": self.memory_count,
            "accepted_count": self.accepted_count,
            "candidate_count": self.candidate_count,
            "archived_count": self.archived_count,
            "recent_memories": [m.to_dict() for m in self.recent_memories],
            "tags": self.tags,
        }


class MemoryEngine:
    """Core memory operations engine.
    
    Implements business logic for memory operations:
    - Search with filters
    - Write candidates
    - Get project context
    - Open raw memory content
    - Audit operations
    
    Integrates with Storage and Policy layers.
    """

    def __init__(self, storage: Any, audit_logger: Any = None, policy_enforcer: Any = None):
        """Initialize memory engine.
        
        Args:
            storage: Storage backend for persistence
            audit_logger: Audit logger for recording operations
            policy_enforcer: Policy enforcer for access control
        """
        self.storage = storage
        self.audit_logger = audit_logger
        self.policy_enforcer = policy_enforcer

    def search(
        self,
        query: Optional[str] = None,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0,
        user_id: str = "",
    ) -> SearchResult:
        """Search memory records.
        
        Args:
            query: Full-text search query
            project_id: Filter by project ID
            status: Filter by status (candidate, accepted, archived)
            tags: Filter by tags
            limit: Maximum results
            offset: Pagination offset
            user_id: User performing the search
            
        Returns:
            SearchResult with matching memories
        """
        # Enforce policy if available
        if self.policy_enforcer and project_id:
            self.policy_enforcer.require_read_access(user_id, project_id)
        
        # Perform search
        results, total = self.storage.search_memories(
            project_id=project_id,
            query=query,
            status=status,
            tags=tags,
            limit=limit,
            offset=offset,
        )
        
        # Log the search
        if self.audit_logger:
            self.audit_logger.log_search(
                user_id=user_id,
                project_id=project_id,
                query=query,
                results_count=len(results),
            )
        
        return SearchResult(
            results=results,
            total=total,
            limit=limit,
            offset=offset,
        )

    def write_candidate(
        self,
        project_id: str,
        content: str,
        source_refs: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        confidence: float = 0.0,
        user_id: str = "",
        memory_id: Optional[str] = None,
    ) -> MemoryRecord:
        """Write a new memory candidate.
        
        Args:
            project_id: The project to associate with
            content: The memory content
            source_refs: Source references for the memory
            tags: Tags for categorization
            confidence: Confidence score (0.0 to 1.0)
            user_id: User creating the candidate
            memory_id: Optional memory ID (generated if not provided)
            
        Returns:
            The created MemoryRecord
            
        Raises:
            PermissionError: If user lacks write permission
        """
        # Enforce policy
        if self.policy_enforcer:
            self.policy_enforcer.require_write_access(user_id, project_id)
        
        # Generate memory ID if not provided
        if not memory_id:
            memory_id = f"m_{uuid.uuid4().hex[:12]}"
        
        # Create memory record
        record = MemoryRecord(
            memory_id=memory_id,
            project_id=project_id,
            content=content,
            source_refs=source_refs or [],
            created_at=datetime.utcnow().isoformat(),
            created_by=user_id,
            tags=tags or [],
            confidence=confidence,
            status=MemoryStatus.CANDIDATE,
        )
        
        # Store the record
        stored = self.storage.create_memory(record)
        
        # Log the write
        if self.audit_logger:
            self.audit_logger.log_memory_write(
                memory_id=memory_id,
                user_id=user_id,
                project_id=project_id,
                details={"status": "candidate"},
            )
        
        return stored

    def get_project_context(
        self,
        project_id: str,
        user_id: str = "",
        limit: int = 50,
    ) -> ProjectContext:
        """Get comprehensive context for a project.
        
        Args:
            project_id: The project ID
            user_id: User requesting context
            limit: Maximum number of recent memories to include
            
        Returns:
            ProjectContext with aggregated information
            
        Raises:
            PermissionError: If user lacks read permission
        """
        # Enforce policy
        if self.policy_enforcer:
            self.policy_enforcer.require_read_access(user_id, project_id)
        
        # Get all memories for the project
        all_memories = self.storage.get_memories_by_project(project_id, limit=1000)
        
        # Count by status
        accepted_count = sum(1 for m in all_memories if m.status == MemoryStatus.ACCEPTED)
        candidate_count = sum(1 for m in all_memories if m.status == MemoryStatus.CANDIDATE)
        archived_count = sum(1 for m in all_memories if m.status == MemoryStatus.ARCHIVED)
        
        # Get recent memories (sorted by created_at, most recent first)
        recent_memories = sorted(
            all_memories[:limit],
            key=lambda m: m.created_at,
            reverse=True
        )
        
        # Collect all unique tags
        all_tags = set()
        for m in all_memories:
            all_tags.update(m.tags)
        tags = sorted(list(all_tags))
        
        # Get project info
        project_info = self.storage.get_project(project_id) or {}
        project_name = project_info.get("name", project_id)
        
        # Log the context retrieval
        if self.audit_logger:
            self.audit_logger.log_project_context(
                project_id=project_id,
                user_id=user_id,
                memories_count=len(all_memories),
            )
        
        return ProjectContext(
            project_id=project_id,
            project_name=project_name,
            memory_count=len(all_memories),
            accepted_count=accepted_count,
            candidate_count=candidate_count,
            archived_count=archived_count,
            recent_memories=recent_memories,
            tags=tags,
        )

    def open_raw(
        self,
        memory_id: str,
        user_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Get raw memory content by ID.
        
        Args:
            memory_id: The memory ID
            user_id: User requesting the memory
            
        Returns:
            Raw memory data as dictionary, or None if not found
            
        Raises:
            PermissionError: If user lacks read permission for the project
        """
        # Get the memory record
        record = self.storage.get_memory(memory_id)
        if not record:
            return None
        
        # Enforce policy
        if self.policy_enforcer:
            self.policy_enforcer.require_read_access(user_id, record.project_id)
        
        # Log the access
        if self.audit_logger:
            self.audit_logger.log_open_raw(
                memory_id=memory_id,
                user_id=user_id,
                project_id=record.project_id,
            )
        
        return record.to_dict()

    def get_memory(
        self,
        memory_id: str,
        user_id: str = "",
    ) -> Optional[MemoryRecord]:
        """Get a memory record by ID with access control.
        
        Args:
            memory_id: The memory ID
            user_id: User requesting the memory
            
        Returns:
            MemoryRecord or None if not found or access denied
        """
        record = self.storage.get_memory(memory_id)
        if not record:
            return None
        
        # Enforce policy
        if self.policy_enforcer:
            try:
                self.policy_enforcer.require_read_access(user_id, record.project_id)
            except PermissionError:
                return None
        
        return record

    def update_memory_status(
        self,
        memory_id: str,
        new_status: str,
        user_id: str = "",
    ) -> Optional[MemoryRecord]:
        """Update memory status (candidate -> accepted -> archived).
        
        Args:
            memory_id: The memory ID
            new_status: New status (candidate, accepted, archived)
            user_id: User performing the update
            
        Returns:
            Updated MemoryRecord or None
            
        Raises:
            PermissionError: If user lacks write permission
        """
        record = self.storage.get_memory(memory_id)
        if not record:
            return None
        
        # Enforce policy
        if self.policy_enforcer:
            self.policy_enforcer.require_write_access(user_id, record.project_id)
        
        # Validate status transition
        valid_transitions = {
            MemoryStatus.CANDIDATE: [MemoryStatus.ACCEPTED, MemoryStatus.ARCHIVED],
            MemoryStatus.ACCEPTED: [MemoryStatus.ARCHIVED],
            MemoryStatus.ARCHIVED: [],  # No transitions from archived
        }
        
        if new_status not in valid_transitions.get(record.status, []):
            raise ValueError(f"Invalid status transition: {record.status} -> {new_status}")
        
        # Update the record
        updated = self.storage.update_memory(memory_id, {"status": new_status})
        
        # Log the update
        if self.audit_logger:
            self.audit_logger.log_memory_update(
                memory_id=memory_id,
                user_id=user_id,
                project_id=record.project_id,
                changes={"status": {"old": record.status, "new": new_status}},
            )
        
        return updated

    def accept_candidate(
        self,
        memory_id: str,
        user_id: str = "",
    ) -> Optional[MemoryRecord]:
        """Accept a candidate memory (transition to accepted).
        
        Args:
            memory_id: The memory ID
            user_id: User performing the acceptance
            
        Returns:
            Updated MemoryRecord or None
        """
        return self.update_memory_status(
            memory_id=memory_id,
            new_status=MemoryStatus.ACCEPTED,
            user_id=user_id,
        )

    def archive_memory(
        self,
        memory_id: str,
        user_id: str = "",
    ) -> Optional[MemoryRecord]:
        """Archive a memory.
        
        Args:
            memory_id: The memory ID
            user_id: User performing the archival
            
        Returns:
            Updated MemoryRecord or None
        """
        return self.update_memory_status(
            memory_id=memory_id,
            new_status=MemoryStatus.ARCHIVED,
            user_id=user_id,
        )

    def get_audit_log(
        self,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        requester_id: str = "",
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get audit log entries.
        
        Args:
            project_id: Filter by project ID
            user_id: Filter by user ID
            action: Filter by action type
            limit: Maximum results
            offset: Pagination offset
            requester_id: User requesting the audit log
            
        Returns:
            Tuple of (audit entries, total count)
            
        Raises:
            PermissionError: If user lacks audit permission
        """
        # Enforce audit policy
        if self.policy_enforcer:
            # Audit access requires special permission
            allowed, reason = self.policy_enforcer.engine.check(
                requester_id, "audit", project_id
            )
            if not allowed:
                raise PermissionError(f"Audit access denied: {reason}")
        
        # Get audit logs from storage
        if self.audit_logger and self.audit_logger.storage:
            logs, total = self.audit_logger.storage.get_audit_logs(
                project_id=project_id,
                user_id=user_id,
                action=action,
                limit=limit,
                offset=offset,
            )
            return [log.to_dict() for log in logs], total
        else:
            # Fallback to in-memory logs
            logs = self.audit_logger.get_logs(
                project_id=project_id,
                user_id=user_id,
                limit=limit,
            )
            return [log.to_dict() for log in logs], len(logs)

    def import_memories(
        self,
        memories: List[Dict[str, Any]],
        user_id: str = "",
    ) -> List[MemoryRecord]:
        """Import multiple memories from JSONL or similar format.
        
        Args:
            memories: List of memory dictionaries
            user_id: User performing the import
            
        Returns:
            List of created MemoryRecords
        """
        created = []
        for data in memories:
            record = MemoryRecord.from_dict(data)
            # Ensure user_id is set
            if not record.created_by:
                record.created_by = user_id
            
            # Create the memory
            stored = self.storage.create_memory(record)
            created.append(stored)
            
            # Log the import
            if self.audit_logger:
                self.audit_logger.log_memory_write(
                    memory_id=record.memory_id,
                    user_id=user_id,
                    project_id=record.project_id,
                    details={"operation": "import"},
                )
        
        return created
