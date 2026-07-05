"""
Memorycore service layer.

Provides the main interface for storing, retrieving, and managing memories.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .database import (
    DatabaseError,
    MemoryNotFoundError,
    SQLiteDatabase,
)
from .models import (
    Memory,
    MemoryStatus,
    MemoryType,
    ValidationError,
    validate_content,
    validate_created_by,
    validate_memory_id,
    validate_memory_type,
    validate_metadata,
    validate_project_id,
    validate_status,
    validate_tags,
)
from .retrieval import build_fts_query, render_context

logger = logging.getLogger(__name__)


def _now() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


class MemoryServiceError(Exception):
    """Base exception for MemoryService errors."""
    pass


class MemoryService:
    """
    Main service class for Memorycore.
    
    Provides a high-level interface for memory operations including:
    - Adding and retrieving memories
    - Searching with full-text search
    - Updating and archiving memories
    - Health checks and statistics
    
    Example:
        >>> service = MemoryService("data/memorycore.db")
        >>> memory = service.add_memory(
        ...     project_id="my-project",
        ...     memory_type="fact",
        ...     content="SQLite is the canonical store"
        ... )
        >>> results = service.search_memory(query="SQLite", project_id="my-project")
        >>> service.close()
    """

    def __init__(
        self,
        database_path: str | Path,
        *,
        on_memory_added: Callable[[Memory], None] | None = None,
        on_memory_updated: Callable[[Memory], None] | None = None,
        on_memory_archived: Callable[[Memory], None] | None = None,
    ) -> None:
        """
        Initialize the MemoryService.
        
        Args:
            database_path: Path to the SQLite database file
            on_memory_added: Optional callback when a memory is added
            on_memory_updated: Optional callback when a memory is updated
            on_memory_archived: Optional callback when a memory is archived
            
        Raises:
            MemoryServiceError: If service cannot be initialized
        """
        try:
            self.database = SQLiteDatabase(database_path)
            self.database.initialize()
            self._callbacks = {
                "added": on_memory_added,
                "updated": on_memory_updated,
                "archived": on_memory_archived,
            }
            logger.info("MemoryService initialized with database: %s", database_path)
        except DatabaseError as e:
            raise MemoryServiceError(f"Failed to initialize MemoryService: {e}") from e

    def close(self) -> None:
        """Close the database connection."""
        self.database.close()
        logger.info("MemoryService closed")

    def __enter__(self) -> "MemoryService":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    def add_memory(
        self,
        *,
        project_id: str,
        memory_type: str,
        content: str,
        summary: str | None = None,
        tags: list[str] | None = None,
        created_by: str | None = None,
        metadata: dict[str, Any] | None = None,
        memory_id: str | None = None,
    ) -> Memory:
        """
        Add a new memory to the database.
        
        Args:
            project_id: Unique identifier for the project scope
            memory_type: Type of memory (fact, decision, preference, etc.)
            content: The main content of the memory
            summary: Optional summary of the content
            tags: Optional list of tags for categorization
            created_by: Optional identifier for the creator
            metadata: Optional additional metadata dictionary
            memory_id: Optional custom ID (defaults to UUID)
            
        Returns:
            Memory: The created memory object
            
        Raises:
            ValidationError: If input validation fails
            MemoryServiceError: If memory cannot be added
        """
        try:
            # Validate inputs
            project_id = validate_project_id(project_id)
            content = validate_content(content)
            memory_type = validate_memory_type(memory_type)
            tags = validate_tags(tags)
            created_by = validate_created_by(created_by)
            metadata = validate_metadata(metadata)
            memory_id = validate_memory_id(memory_id)
            
            # Validate summary
            if summary is not None:
                summary = summary.strip()
                if summary and len(summary) > 10000:
                    raise ValidationError("summary must be 10000 characters or less")
            
            timestamp = _now()
            
            memory = self.database.add({
                "id": memory_id,
                "project_id": project_id,
                "memory_type": memory_type,
                "content": content,
                "summary": summary.strip() if summary else None,
                "tags": tags,
                "status": MemoryStatus.ACTIVE.value,
                "created_by": created_by,
                "metadata": metadata,
                "created_at": timestamp,
                "updated_at": timestamp,
            })
            
            logger.info("Memory added: id=%s, project_id=%s, memory_type=%s", 
                       memory.id, project_id, memory_type)
            
            # Trigger callback
            if self._callbacks["added"]:
                try:
                    self._callbacks["added"](memory)
                except Exception as e:
                    logger.error("Error in on_memory_added callback: %s", e)
            
            return memory
            
        except ValidationError:
            raise
        except Exception as e:
            raise MemoryServiceError(f"Failed to add memory: {e}") from e

    def add_memories(
        self,
        memories: list[dict[str, Any]],
    ) -> list[Memory]:
        """
        Add multiple memories in a batch operation.
        
        Args:
            memories: List of memory dictionaries with same parameters as add_memory
            
        Returns:
            list[Memory]: List of created memory objects
            
        Raises:
            ValidationError: If any input validation fails
            MemoryServiceError: If memories cannot be added
        """
        results = []
        errors = []
        
        for i, memory_data in enumerate(memories):
            try:
                memory = self.add_memory(**memory_data)
                results.append(memory)
            except (ValidationError, MemoryServiceError) as e:
                errors.append({"index": i, "error": str(e), "data": memory_data})
                logger.error("Error adding memory at index %d: %s", i, e)
        
        if errors:
            logger.warning("Batch add completed with %d errors", len(errors))
        
        return results

    def get_memory(self, memory_id: str) -> Memory | None:
        """
        Retrieve a memory by its ID.
        
        Args:
            memory_id: The unique identifier of the memory
            
        Returns:
            Memory or None: The memory object if found, None otherwise
        """
        try:
            memory = self.database.get(memory_id)
            if memory:
                logger.debug("Memory retrieved: %s", memory_id)
            return memory
        except Exception as e:
            logger.error("Error retrieving memory %s: %s", memory_id, e)
            return None

    def get_memories(self, memory_ids: list[str]) -> list[Memory]:
        """
        Retrieve multiple memories by their IDs.
        
        Args:
            memory_ids: List of memory IDs to retrieve
            
        Returns:
            list[Memory]: List of found memory objects
        """
        results = []
        for memory_id in memory_ids:
            memory = self.get_memory(memory_id)
            if memory:
                results.append(memory)
        return results

    def search_memory(
        self,
        *,
        query: str,
        project_id: str,
        limit: int = 10,
        memory_type: str | None = None,
    ) -> list[Memory]:
        """
        Search memories using full-text search.
        
        Args:
            query: Search query string
            project_id: Project scope filter
            limit: Maximum number of results (1-100)
            memory_type: Optional memory type filter
            
        Returns:
            list[Memory]: List of matching memories
            
        Raises:
            ValidationError: If input validation fails
        """
        try:
            project_id = validate_project_id(project_id)
            
            if limit < 1 or limit > 100:
                raise ValidationError("limit must be between 1 and 100")
            
            if memory_type is not None:
                memory_type = validate_memory_type(memory_type)
            
            fts_query = build_fts_query(query)
            if not fts_query:
                logger.debug("Empty FTS query, falling back to recent memories")
                return self.database.list_recent(project_id, limit)
            
            results = self.database.search(fts_query, project_id, limit, memory_type)
            logger.debug("Search completed: query='%s', project_id='%s', count=%d", 
                        query, project_id, len(results))
            return results
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error("Search error: %s", e)
            return []

    def retrieve_context(
        self,
        *,
        query: str,
        project_id: str,
        limit: int = 10,
        memory_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Retrieve memories and format them as context for LLM prompts.
        
        Args:
            query: Search query string
            project_id: Project scope filter
            limit: Maximum number of results (1-100)
            memory_type: Optional memory type filter
            
        Returns:
            dict: Context information including formatted text
            
        Raises:
            ValidationError: If input validation fails
        """
        memories = self.search_memory(
            query=query,
            project_id=project_id,
            limit=limit,
            memory_type=memory_type,
        )
        items = [memory.to_dict() for memory in memories]
        
        context = {
            "project_id": project_id,
            "query": query,
            "count": len(items),
            "memories": items,
            "context_text": render_context(items),
        }
        
        logger.debug("Context retrieved: project_id='%s', query='%s', count=%d", 
                     project_id, query, len(items))
        
        return context

    def update_memory(
        self,
        memory_id: str,
        *,
        content: str | None = None,
        summary: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        status: str | None = None,
    ) -> Memory | None:
        """
        Update an existing memory.
        
        Args:
            memory_id: The unique identifier of the memory to update
            content: New content (optional)
            summary: New summary (optional)
            tags: New tags list (optional)
            metadata: New metadata dictionary (optional)
            status: New status (optional)
            
        Returns:
            Memory or None: The updated memory object if found, None otherwise
            
        Raises:
            ValidationError: If input validation fails
        """
        try:
            # Get current memory for validation
            current = self.get_memory(memory_id)
            if current is None:
                logger.warning("Memory not found for update: %s", memory_id)
                return None
            
            values: dict[str, Any] = {"updated_at": _now()}
            
            if content is not None:
                values["content"] = validate_content(content)
            
            if summary is not None:
                summary = summary.strip()
                if summary and len(summary) > 10000:
                    raise ValidationError("summary must be 10000 characters or less")
                values["summary"] = summary or None
            
            if tags is not None:
                values["tags"] = validate_tags(tags)
            
            if metadata is not None:
                values["metadata"] = validate_metadata(metadata)
            
            if status is not None:
                values["status"] = validate_status(status)
            
            updated = self.database.update(memory_id, values)
            
            if updated:
                logger.info("Memory updated: %s", memory_id)
                
                # Trigger callback if status changed to archived
                if status == MemoryStatus.ARCHIVED.value and self._callbacks["archived"]:
                    try:
                        self._callbacks["archived"](updated)
                    except Exception as e:
                        logger.error("Error in on_memory_archived callback: %s", e)
                
                # Trigger update callback
                if self._callbacks["updated"]:
                    try:
                        self._callbacks["updated"](updated)
                    except Exception as e:
                        logger.error("Error in on_memory_updated callback: %s", e)
            
            return updated
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error("Error updating memory %s: %s", memory_id, e)
            return None

    def archive_memory(self, memory_id: str) -> Memory | None:
        """
        Archive a memory (mark as archived).
        
        Args:
            memory_id: The unique identifier of the memory to archive
            
        Returns:
            Memory or None: The archived memory object if found, None otherwise
        """
        return self.update_memory(memory_id, status=MemoryStatus.ARCHIVED.value)

    def supersede_memory(self, memory_id: str) -> Memory | None:
        """
        Mark a memory as superseded.
        
        Args:
            memory_id: The unique identifier of the memory to supersede
            
        Returns:
            Memory or None: The superseded memory object if found, None otherwise
        """
        return self.update_memory(memory_id, status=MemoryStatus.SUPERSEDED.value)

    def activate_memory(self, memory_id: str) -> Memory | None:
        """
        Activate a memory (mark as active).
        
        Args:
            memory_id: The unique identifier of the memory to activate
            
        Returns:
            Memory or None: The activated memory object if found, None otherwise
        """
        return self.update_memory(memory_id, status=MemoryStatus.ACTIVE.value)

    def delete_memory(self, memory_id: str) -> bool:
        """
        Permanently delete a memory from the database.
        
        Args:
            memory_id: The unique identifier of the memory to delete
            
        Returns:
            bool: True if memory was deleted, False otherwise
        """
        try:
            deleted = self.database.delete(memory_id)
            if deleted:
                logger.info("Memory deleted: %s", memory_id)
            return deleted
        except Exception as e:
            logger.error("Error deleting memory %s: %s", memory_id, e)
            return False

    def health(self) -> dict[str, Any]:
        """
        Check service health and return status information.
        
        Returns:
            dict: Health status information
        """
        try:
            health = self.database.health()
            health["service"] = "MemoryService"
            health["timestamp"] = _now()
            return health
        except Exception as e:
            logger.error("Health check failed: %s", e)
            return {
                "ok": False,
                "service": "MemoryService",
                "timestamp": _now(),
                "error": str(e),
            }

    def get_stats(self, project_id: str | None = None) -> dict[str, Any]:
        """
        Get statistics about memories.
        
        Args:
            project_id: Optional project filter
            
        Returns:
            dict: Statistics about memories
        """
        return self.database.get_stats(project_id)

    def list_projects(self) -> list[str]:
        """
        List all project IDs in the database.
        
        Returns:
            list[str]: List of project IDs
        """
        with self.database._lock:
            try:
                rows = self.database.connection.execute(
                    "SELECT DISTINCT project_id FROM memories ORDER BY project_id"
                ).fetchall()
                return [row["project_id"] for row in rows]
            except Exception as e:
                logger.error("Error listing projects: %s", e)
                return []

    def backup(self, backup_path: str | Path) -> bool:
        """
        Create a backup of the database.
        
        Args:
            backup_path: Path to save the backup
            
        Returns:
            bool: True if backup was successful
        """
        import shutil
        
        try:
            backup_path = Path(backup_path).expanduser().resolve()
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Ensure all writes are flushed
            self.database.connection.execute("PRAGMA wal_checkpoint(FULL)")
            
            # Copy the database file
            shutil.copy2(self.database.path, backup_path)
            
            # Also copy WAL and SHM files if they exist
            wal_file = self.database.path.with_suffix(self.database.path.suffix + "-wal")
            shm_file = self.database.path.with_suffix(self.database.path.suffix + "-shm")
            
            if wal_file.exists():
                shutil.copy2(wal_file, backup_path.with_suffix(".db-wal"))
            if shm_file.exists():
                shutil.copy2(shm_file, backup_path.with_suffix(".db-shm"))
            
            logger.info("Database backup created: %s", backup_path)
            return True
            
        except Exception as e:
            logger.error("Backup failed: %s", e)
            return False

    def restore(self, backup_path: str | Path) -> bool:
        """
        Restore the database from a backup.
        
        Args:
            backup_path: Path to the backup file
            
        Returns:
            bool: True if restore was successful
            
        Note:
            This will close the current database connection and replace
            the database file. All existing connections must be closed first.
        """
        import shutil
        
        try:
            backup_path = Path(backup_path).expanduser().resolve()
            
            if not backup_path.exists():
                raise FileNotFoundError(f"Backup file not found: {backup_path}")
            
            # Close current connection
            self.close()
            
            # Create parent directory if it doesn't exist
            self.database.path.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy backup to database location
            shutil.copy2(backup_path, self.database.path)
            
            # Also restore WAL and SHM files if they exist
            backup_wal = backup_path.with_suffix(".db-wal")
            backup_shm = backup_path.with_suffix(".db-shm")
            
            if backup_wal.exists():
                shutil.copy2(backup_wal, self.database.path.with_suffix(".db-wal"))
            if backup_shm.exists():
                shutil.copy2(backup_shm, self.database.path.with_suffix(".db-shm"))
            
            # Reopen the database
            self.database = SQLiteDatabase(self.database.path)
            self.database.initialize()
            
            logger.info("Database restored from: %s", backup_path)
            return True
            
        except Exception as e:
            logger.error("Restore failed: %s", e)
            # Try to reopen the original database
            try:
                self.database = SQLiteDatabase(self.database.path)
                self.database.initialize()
            except:
                pass
            return False
