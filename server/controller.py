"""Memorycore Controller - Primary interface to CozoDB.

This module provides the main controller class that implements all memory operations
using CozoDB as the primary memory store.

Architecture: LLM client -> Mojo MCP server -> Memorycore controller -> CozoDB
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import logging

logger = logging.getLogger(__name__)


# Constants
class MemoryStatus:
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    ARCHIVED = "archived"
    REJECTED = "rejected"


class MemoryType:
    FACT = "fact"
    DECISION = "decision"
    DESIGN = "design"
    TASK = "task"
    REFERENCE = "reference"
    WARNING = "warning"
    EXPERIMENT = "experiment"


class LinkType:
    RELATED = "related"
    DERIVED = "derived"
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    REFERENCES = "references"
    DEPENDS_ON = "depends_on"


@dataclass
class MemoryRecord:
    """Memory record matching CozoDB schema."""
    memory_id: str
    project_id: str
    content: str
    source_refs: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_by: str = ""
    tags: List[str] = field(default_factory=list)
    confidence: float = 0.0
    status: str = MemoryStatus.CANDIDATE
    memory_type: str = MemoryType.FACT
    summary: str = ""
    raw_evidence_ref: str = ""
    trust_score: float = 0.0
    approval_status: str = MemoryStatus.CANDIDATE
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    version: int = 1

    def to_dict(self) -> Dict[str, Any]:
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
            "memory_type": self.memory_type,
            "summary": self.summary,
            "raw_evidence_ref": self.raw_evidence_ref,
            "trust_score": self.trust_score,
            "approval_status": self.approval_status,
            "updated_at": self.updated_at,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryRecord":
        return cls(
            memory_id=data.get("memory_id", str(uuid.uuid4())),
            project_id=data.get("project_id", ""),
            content=data.get("content", ""),
            source_refs=data.get("source_refs", []),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            created_by=data.get("created_by", ""),
            tags=data.get("tags", []),
            confidence=data.get("confidence", 0.0),
            status=data.get("status", MemoryStatus.CANDIDATE),
            memory_type=data.get("memory_type", MemoryType.FACT),
            summary=data.get("summary", ""),
            raw_evidence_ref=data.get("raw_evidence_ref", ""),
            trust_score=data.get("trust_score", 0.0),
            approval_status=data.get("approval_status", MemoryStatus.CANDIDATE),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat()),
            version=data.get("version", 1),
        )


@dataclass
class SearchResult:
    """Search result with pagination."""
    results: List[MemoryRecord]
    total: int
    limit: int
    offset: int
    scores: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "results": [r.to_dict() for r in self.results],
            "total": self.total,
            "limit": self.limit,
            "offset": self.offset,
            "scores": self.scores,
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


class CozoDBError(Exception):
    """Base exception for CozoDB errors."""
    pass


class MemoryController:
    """Primary controller for memory operations using CozoDB.
    
    Implements core CRUD, search, and advanced operations.
    """

    def __init__(
        self,
        db_path: str = "memorycore.cozo",
        schema_path: Optional[str] = None,
        audit_logger: Optional[Any] = None,
    ):
        """Initialize the memory controller.
        
        Args:
            db_path: Path to CozoDB database file
            schema_path: Path to CozoDB schema file
            audit_logger: Optional audit logger
        """
        self.db_path = db_path
        self.schema_path = schema_path or "cozodb/schema.cozo"
        self.audit_logger = audit_logger
        self._db = None
        self._cozo = None
        
        self._initialize_db()

    def _initialize_db(self) -> None:
        """Initialize CozoDB connection and load schema."""
        try:
            import cozo
            self._cozo = cozo
        except ImportError:
            raise CozoDBError(
                "CozoDB Python library is required. Install with: pip install cozo"
            )
        
        try:
            with open(self.schema_path, 'r') as f:
                schema = f.read()
            
            self._db = self._cozo.Db(self.db_path, schema)
            logger.info(f"CozoDB initialized at: {self.db_path}")
        except FileNotFoundError:
            raise CozoDBError(f"Schema file not found: {self.schema_path}")
        except Exception as e:
            raise CozoDBError(f"Failed to initialize CozoDB: {e}")

    def close(self) -> None:
        """Close the database connection."""
        self._db = None
        logger.info("CozoDB connection closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # ========================================================================
    # CORE CRUD OPERATIONS
    # ========================================================================

    def add_memory(
        self,
        project_id: str,
        content: str,
        created_by: str = "",
        source_refs: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        confidence: float = 0.0,
        memory_type: str = MemoryType.FACT,
        summary: str = "",
        raw_evidence_ref: str = "",
        trust_score: float = 0.0,
        status: str = MemoryStatus.CANDIDATE,
        memory_id: Optional[str] = None,
    ) -> MemoryRecord:
        """Add a new memory record."""
        if not memory_id:
            memory_id = f"m_{uuid.uuid4().hex[:12]}"
        
        record = MemoryRecord(
            memory_id=memory_id,
            project_id=project_id,
            content=content,
            source_refs=source_refs or [],
            created_at=datetime.utcnow().isoformat(),
            created_by=created_by,
            tags=tags or [],
            confidence=confidence,
            status=status,
            memory_type=memory_type,
            summary=summary,
            raw_evidence_ref=raw_evidence_ref,
            trust_score=trust_score,
            approval_status=status,
            updated_at=datetime.utcnow().isoformat(),
            version=1,
        )
        
        try:
            self._db.run(
                "?[memory_id, project_id, content, source_refs, created_at, created_by, "
                "tags, confidence, status, memory_type, summary, raw_evidence_ref, "
                "trust_score, approval_status, updated_at, version] :put memories",
                record.to_dict()
            )
            
            if self.audit_logger:
                self.audit_logger.log_memory_write(
                    memory_id=record.memory_id,
                    user_id=created_by,
                    project_id=project_id,
                    details={"status": status, "type": memory_type},
                )
            
            logger.info(f"Added memory: {record.memory_id} to project: {project_id}")
            return record
            
        except Exception as e:
            logger.error(f"Failed to add memory: {e}")
            raise CozoDBError(f"Failed to add memory: {e}")

    def get_memory(self, memory_id: str) -> Optional[MemoryRecord]:
        """Get a memory record by ID."""
        try:
            result = self._db.query(
                "memories[memory_id, project_id, content, source_refs, created_at, "
                "created_by, tags, confidence, status, memory_type, summary, "
                "raw_evidence_ref, trust_score, approval_status, updated_at, version] "
                "where memory_id == $memory_id",
                {"memory_id": memory_id}
            )
            
            rows = list(result)
            if not rows:
                return None
            
            row = rows[0]
            return MemoryRecord(
                memory_id=row["memory_id"],
                project_id=row["project_id"],
                content=row["content"],
                source_refs=row["source_refs"],
                created_at=row["created_at"],
                created_by=row["created_by"],
                tags=row["tags"],
                confidence=row["confidence"],
                status=row["status"],
                memory_type=row["memory_type"],
                summary=row["summary"],
                raw_evidence_ref=row["raw_evidence_ref"],
                trust_score=row["trust_score"],
                approval_status=row["approval_status"],
                updated_at=row["updated_at"],
                version=row["version"],
            )
            
        except Exception as e:
            logger.error(f"Failed to get memory {memory_id}: {e}")
            raise CozoDBError(f"Failed to get memory: {e}")

    def update_memory(
        self,
        memory_id: str,
        updates: Dict[str, Any],
        user_id: str = "",
    ) -> Optional[MemoryRecord]:
        """Update a memory record."""
        existing = self.get_memory(memory_id)
        if not existing:
            return None
        
        # Build update parameters
        params = {"memory_id": memory_id}
        set_clauses = []
        
        for key, value in updates.items():
            if hasattr(existing, key):
                set_clauses.append(f"{key} = ${key}")
                params[key] = value
        
        if not set_clauses:
            return existing
        
        # Update version and timestamp
        set_clauses.append("version = $version")
        set_clauses.append("updated_at = $updated_at")
        params["version"] = existing.version + 1
        params["updated_at"] = datetime.utcnow().isoformat()
        
        try:
            self._db.run(
                f"?[memory_id, project_id, content, source_refs, created_at, "
                f"created_by, tags, confidence, status, memory_type, summary, "
                f"raw_evidence_ref, trust_score, approval_status, updated_at, version] "
                f":put memories :where memory_id == $memory_id :set {", ".".join(set_clauses), "}",
                params
            )
            
            if self.audit_logger:
                self.audit_logger.log_memory_update(
                    memory_id=memory_id,
                    user_id=user_id,
                    project_id=existing.project_id,
                    changes=updates,
                )
            
            return self.get_memory(memory_id)
            
        except Exception as e:
            logger.error(f"Failed to update memory {memory_id}: {e}")
            raise CozoDBError(f"Failed to update memory: {e}")

    def delete_memory(self, memory_id: str, user_id: str = "") -> bool:
        """Delete a memory record."""
        existing = self.get_memory(memory_id)
        if not existing:
            return False
        
        try:
            self._db.run(
                "?[memory_id] :delete memories :where memory_id == $memory_id",
                {"memory_id": memory_id}
            )
            
            if self.audit_logger:
                self.audit_logger.log_memory_delete(
                    memory_id=memory_id,
                    user_id=user_id,
                    project_id=existing.project_id,
                )
            
            logger.info(f"Deleted memory: {memory_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete memory {memory_id}: {e}")
            raise CozoDBError(f"Failed to delete memory: {e}")

    # ========================================================================
    # SEARCH OPERATIONS
    # ========================================================================

    def search_memories(
        self,
        query: Optional[str] = None,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        tags: Optional[List[str]] = None,
        memory_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        user_id: str = "",
    ) -> SearchResult:
        """Search memory records with filters."""
        try:
            conditions = []
            params = {}
            
            if project_id:
                conditions.append("project_id == $project_id")
                params["project_id"] = project_id
            
            if status:
                conditions.append("status == $status")
                params["status"] = status
            
            if memory_type:
                conditions.append("memory_type == $memory_type")
                params["memory_type"] = memory_type
            
            if tags:
                for i, tag in enumerate(tags):
                    conditions.append(f"$tag_{i} in tags")
                    params[f"tag_{i}"] = tag
            
            where_clause = " and ".join(conditions) if conditions else "true"
            
            # Count total
            count_result = self._db.query(
                f"count(memories[memory_id] :where {where_clause})",
                params
            )
            total = list(count_result)[0]["count(memories[memory_id])"] if count_result else 0
            
            # Build search query
            if query:
                # Use FTS search function
                search_params = {
                    "query": query,
                    "project_id": project_id,
                    "status": status,
                    "tags": tags,
                    "limit": limit,
                    "offset": offset,
                }
                
                result = self._db.query(
                    "ft_search_memories[query: $query, project_id: $project_id, "
                    "status: $status, tags: $tags, limit: $limit, offset: $offset]",
                    search_params
                )
                rows = list(result)
                
                results = []
                scores = []
                for row in rows:
                    results.append(MemoryRecord(
                        memory_id=row.get("memory_id", ""),
                        project_id=row.get("project_id", ""),
                        content=row.get("content", ""),
                        source_refs=row.get("source_refs", []),
                        created_at=row.get("created_at", ""),
                        created_by=row.get("created_by", ""),
                        tags=row.get("tags", []),
                        confidence=row.get("confidence", 0.0),
                        status=row.get("status", MemoryStatus.CANDIDATE),
                        memory_type=row.get("memory_type", MemoryType.FACT),
                        summary=row.get("summary", ""),
                        raw_evidence_ref=row.get("raw_evidence_ref", ""),
                        trust_score=row.get("trust_score", 0.0),
                        approval_status=row.get("approval_status", MemoryStatus.CANDIDATE),
                        updated_at=row.get("updated_at", ""),
                        version=row.get("version", 1),
                    ))
                    scores.append(row.get("score", 1.0))
                
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
                    scores=scores,
                )
            else:
                # Regular filtered query
                params["limit"] = limit
                params["offset"] = offset
                
                result = self._db.query(
                    f"memories[memory_id, project_id, content, source_refs, created_at, "
                    f"created_by, tags, confidence, status, memory_type, summary, "
                    f"raw_evidence_ref, trust_score, approval_status, updated_at, version] "
                    f":where {where_clause} :limit $limit :offset $offset",
                    params
                )
                rows = list(result)
                
                results = []
                for row in rows:
                    results.append(MemoryRecord(
                        memory_id=row["memory_id"],
                        project_id=row["project_id"],
                        content=row["content"],
                        source_refs=row["source_refs"],
                        created_at=row["created_at"],
                        created_by=row["created_by"],
                        tags=row["tags"],
                        confidence=row["confidence"],
                        status=row["status"],
                        memory_type=row["memory_type"],
                        summary=row["summary"],
                        raw_evidence_ref=row["raw_evidence_ref"],
                        trust_score=row["trust_score"],
                        approval_status=row["approval_status"],
                        updated_at=row["updated_at"],
                        version=row["version"],
                    ))
                
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
            
        except Exception as e:
            logger.error(f"Failed to search memories: {e}")
            raise CozoDBError(f"Failed to search memories: {e}")

    def list_by_project(
        self,
        project_id: str,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        user_id: str = "",
    ) -> SearchResult:
        """List all memories for a specific project."""
        return self.search_memories(
            project_id=project_id,
            status=status,
            limit=limit,
            offset=offset,
            user_id=user_id,
        )

    # ========================================================================
    # ADVANCED OPERATIONS
    # ========================================================================

    def supersede(
        self,
        old_memory_id: str,
        new_memory_id: str,
        reason: str,
        created_by: str = "",
    ) -> Dict[str, Any]:
        """Create a supersession chain - new memory replaces old memory."""
        chain_id = f"sc_{uuid.uuid4().hex[:12]}"
        
        try:
            # Insert supersession chain
            self._db.run(
                "?[chain_id, old_memory_id, new_memory_id, reason, created_at, "
                "created_by, is_active] :put supersession_chains",
                {
                    "chain_id": chain_id,
                    "old_memory_id": old_memory_id,
                    "new_memory_id": new_memory_id,
                    "reason": reason,
                    "created_at": datetime.utcnow().isoformat(),
                    "created_by": created_by,
                    "is_active": True,
                }
            )
            
            # Create memory link
            link_id = f"link_{uuid.uuid4().hex[:12]}"
            self._db.run(
                "?[link_id, from_memory_id, to_memory_id, link_type, created_at, "
                "created_by, strength, description] :put memory_links",
                {
                    "link_id": link_id,
                    "from_memory_id": new_memory_id,
                    "to_memory_id": old_memory_id,
                    "link_type": LinkType.SUPERSEDES,
                    "created_at": datetime.utcnow().isoformat(),
                    "created_by": created_by,
                    "strength": 1.0,
                    "description": f"Supersedes: {reason}",
                }
            )
            
            if self.audit_logger:
                project_id = self._get_project_id(new_memory_id)
                self.audit_logger.log(
                    action="supersede",
                    entity_type="memory",
                    entity_id=chain_id,
                    user_id=created_by,
                    project_id=project_id,
                    details={
                        "old_memory_id": old_memory_id,
                        "new_memory_id": new_memory_id,
                        "reason": reason,
                    },
                )
            
            logger.info(f"Created supersession chain: {chain_id}")
            return {
                "chain_id": chain_id,
                "old_memory_id": old_memory_id,
                "new_memory_id": new_memory_id,
                "reason": reason,
            }
            
        except Exception as e:
            logger.error(f"Failed to create supersession chain: {e}")
            raise CozoDBError(f"Failed to create supersession chain: {e}")

    def contradict(
        self,
        memory_a_id: str,
        memory_b_id: str,
        resolution_notes: str = "",
        created_by: str = "",
    ) -> Dict[str, Any]:
        """Create a contradiction chain - two memories contradict each other."""
        chain_id = f"cc_{uuid.uuid4().hex[:12]}"
        
        try:
            # Insert contradiction chain
            self._db.run(
                "?[chain_id, memory_a_id, memory_b_id, resolution, resolution_notes, "
                "created_at, created_by, resolved_at, resolved_by] :put contradiction_chains",
                {
                    "chain_id": chain_id,
                    "memory_a_id": memory_a_id,
                    "memory_b_id": memory_b_id,
                    "resolution": "unresolved",
                    "resolution_notes": resolution_notes,
                    "created_at": datetime.utcnow().isoformat(),
                    "created_by": created_by,
                    "resolved_at": "",
                    "resolved_by": "",
                }
            )
            
            # Create memory links in both directions
            for from_id, to_id in [(memory_a_id, memory_b_id), (memory_b_id, memory_a_id)]:
                link_id = f"link_{uuid.uuid4().hex[:12]}"
                self._db.run(
                    "?[link_id, from_memory_id, to_memory_id, link_type, created_at, "
                    "created_by, strength, description] :put memory_links",
                    {
                        "link_id": link_id,
                        "from_memory_id": from_id,
                        "to_memory_id": to_id,
                        "link_type": LinkType.CONTRADICTS,
                        "created_at": datetime.utcnow().isoformat(),
                        "created_by": created_by,
                        "strength": 1.0,
                        "description": f"Contradicts: {resolution_notes}",
                    }
                )
            
            if self.audit_logger:
                project_id = self._get_project_id(memory_a_id)
                self.audit_logger.log(
                    action="contradict",
                    entity_type="memory",
                    entity_id=chain_id,
                    user_id=created_by,
                    project_id=project_id,
                    details={
                        "memory_a_id": memory_a_id,
                        "memory_b_id": memory_b_id,
                        "resolution_notes": resolution_notes,
                    },
                )
            
            logger.info(f"Created contradiction chain: {chain_id}")
            return {
                "chain_id": chain_id,
                "memory_a_id": memory_a_id,
                "memory_b_id": memory_b_id,
                "resolution_notes": resolution_notes,
            }
            
        except Exception as e:
            logger.error(f"Failed to create contradiction chain: {e}")
            raise CozoDBError(f"Failed to create contradiction chain: {e}")

    # ========================================================================
    # CONTEXT RETRIEVAL
    # ========================================================================

    def retrieve_context(
        self,
        project_id: str,
        query: Optional[str] = None,
        limit: int = 50,
        user_id: str = "",
    ) -> ProjectContext:
        """Retrieve comprehensive context for a project."""
        # Get project info
        project = self._get_project(project_id)
        project_name = project.get("name", project_id) if project else project_id
        
        # Get all memories for the project
        if query:
            search_result = self.search_memories(
                project_id=project_id,
                query=query,
                limit=1000,
                user_id=user_id,
            )
            all_memories = search_result.results
        else:
            all_memories = self.list_by_project(
                project_id=project_id,
                limit=1000,
                user_id=user_id,
            ).results
        
        # Count by status
        accepted_count = sum(1 for m in all_memories if m.status == MemoryStatus.ACCEPTED)
        candidate_count = sum(1 for m in all_memories if m.status == MemoryStatus.CANDIDATE)
        archived_count = sum(1 for m in all_memories if m.status == MemoryStatus.ARCHIVED)
        
        # Get recent memories
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

    # ========================================================================
    # PROJECT OPERATIONS
    # ========================================================================

    def create_project(
        self,
        project_id: str,
        name: str,
        description: str = "",
        created_by: str = "",
    ) -> Dict[str, Any]:
        """Create a new project."""
        try:
            self._db.run(
                "?[project_id, name, description, created_at, created_by, is_active] :put projects",
                {
                    "project_id": project_id,
                    "name": name,
                    "description": description,
                    "created_at": datetime.utcnow().isoformat(),
                    "created_by": created_by,
                    "is_active": True,
                }
            )
            
            if self.audit_logger:
                self.audit_logger.log(
                    action="create",
                    entity_type="project",
                    entity_id=project_id,
                    user_id=created_by,
                    details={"name": name, "description": description},
                )
            
            logger.info(f"Created project: {project_id}")
            return {
                "project_id": project_id,
                "name": name,
                "description": description,
            }
            
        except Exception as e:
            logger.error(f"Failed to create project: {e}")
            raise CozoDBError(f"Failed to create project: {e}")

    def _get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get a project by ID."""
        try:
            result = self._db.query(
                "projects[project_id, name, description, created_at, created_by, is_active] "
                "where project_id == $project_id",
                {"project_id": project_id}
            )
            rows = list(result)
            return dict(rows[0]) if rows else None
        except Exception as e:
            logger.error(f"Failed to get project {project_id}: {e}")
            return None

    def _get_project_id(self, memory_id: str) -> Optional[str]:
        """Get the project ID for a memory."""
        memory = self.get_memory(memory_id)
        return memory.project_id if memory else None

    def health_check(self) -> Dict[str, Any]:
        """Perform a health check on the database."""
        try:
            result = self._db.query("1 + 1")
            test_result = list(result)[0]["1 + 1"] if result else None
            
            return {
                "status": "healthy",
                "database": self.db_path,
                "test_query": test_result == 2,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
            }
