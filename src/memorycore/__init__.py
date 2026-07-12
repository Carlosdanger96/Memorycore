"""
Memorycore v0.1 public package.

Memorycore is a local-first SQLite memory service for LLMs and agents.
It provides durable storage, full-text search, and project-scoped memory management.

Example:
    >>> from memorycore import MemoryService
    >>> service = MemoryService("data/memorycore.db")
    >>> memory = service.add_memory(
    ...     project_id="example",
    ...     memory_type="decision",
    ...     content="SQLite is the canonical v0.1 store.",
    ...     tags=["storage"],
    ... )
    >>> context = service.retrieve_context(
    ...     query="canonical store",
    ...     project_id="example",
    ... )
    >>> print(context["context_text"])
    >>> service.close()
"""

from .memory_service import MemoryService, MemoryServiceError
from .models import (
    Memory,
    MemoryStatus,
    MemoryType,
    MemorycoreError,
    ValidationError,
)
from .database import (
    SQLiteDatabase,
    DatabaseError,
    MemoryNotFoundError,
)
from .retrieval import build_fts_query, render_context

__all__ = [
    # Main service
    "MemoryService",
    "MemoryServiceError",
    
    # Models
    "Memory",
    "MemoryStatus",
    "MemoryType",
    
    # Exceptions
    "MemorycoreError",
    "ValidationError",
    "DatabaseError",
    "MemoryNotFoundError",
    
    # Database
    "SQLiteDatabase",
    
    # Retrieval utilities
    "build_fts_query",
    "render_context",
]

__version__ = "0.1.0.dev0"
