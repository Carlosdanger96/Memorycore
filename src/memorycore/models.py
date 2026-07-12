"""
Memorycore data models and validation.

This module defines the core data structures and validation logic for Memorycore.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class MemoryType(StrEnum):
    """Types of memories that can be stored."""
    FACT = "fact"
    DECISION = "decision"
    PREFERENCE = "preference"
    PROCEDURE = "procedure"
    CORRECTION = "correction"
    NOTE = "note"


class MemoryStatus(StrEnum):
    """Status of a memory."""
    ACTIVE = "active"
    ARCHIVED = "archived"
    SUPERSEDED = "superseded"


class MemorycoreError(Exception):
    """Base exception for Memorycore errors."""
    pass


class ValidationError(MemorycoreError):
    """Raised when input validation fails."""
    pass


# Validation patterns
PROJECT_ID_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,254}$')
MEMORY_ID_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,254}$')


def validate_project_id(project_id: str) -> str:
    """
    Validate a project ID.
    
    Args:
        project_id: The project ID to validate
        
    Returns:
        str: The validated project ID
        
    Raises:
        ValidationError: If the project ID is invalid
    """
    if not project_id or not project_id.strip():
        raise ValidationError("project_id is required and cannot be empty")
    
    project_id = project_id.strip()
    
    if len(project_id) > 255:
        raise ValidationError("project_id must be 255 characters or less")
    
    if not PROJECT_ID_PATTERN.match(project_id):
        raise ValidationError(
            "project_id must start with alphanumeric and contain only "
            "alphanumeric, underscore, or hyphen characters"
        )
    
    return project_id


def validate_memory_id(memory_id: str | None) -> str:
    """
    Validate a memory ID.
    
    Args:
        memory_id: The memory ID to validate (can be None to generate new)
        
    Returns:
        str: The validated memory ID
        
    Raises:
        ValidationError: If the memory ID is invalid
    """
    if memory_id is None:
        return str(uuid.uuid4())
    
    memory_id = memory_id.strip()
    
    if not memory_id:
        return str(uuid.uuid4())
    
    if len(memory_id) > 255:
        raise ValidationError("memory_id must be 255 characters or less")
    
    if not MEMORY_ID_PATTERN.match(memory_id):
        raise ValidationError(
            "memory_id must start with alphanumeric and contain only "
            "alphanumeric, underscore, or hyphen characters"
        )
    
    return memory_id


def validate_memory_type(value: str) -> str:
    """
    Validate a memory type.
    
    Args:
        value: The memory type to validate
        
    Returns:
        str: The validated memory type
        
    Raises:
        ValidationError: If the memory type is invalid
    """
    try:
        return MemoryType(value).value
    except ValueError as exc:
        allowed = ", ".join(item.value for item in MemoryType)
        raise ValidationError(f"memory_type must be one of: {allowed}") from exc


def validate_status(value: str) -> str:
    """
    Validate a memory status.
    
    Args:
        value: The status to validate
        
    Returns:
        str: The validated status
        
    Raises:
        ValidationError: If the status is invalid
    """
    try:
        return MemoryStatus(value).value
    except ValueError as exc:
        allowed = ", ".join(item.value for item in MemoryStatus)
        raise ValidationError(f"status must be one of: {allowed}") from exc


def validate_content(content: str) -> str:
    """
    Validate memory content.
    
    Args:
        content: The content to validate
        
    Returns:
        str: The validated content
        
    Raises:
        ValidationError: If the content is invalid
    """
    if not content or not content.strip():
        raise ValidationError("content is required and cannot be empty")
    
    content = content.strip()
    
    if len(content) > 1000000:  # 1MB limit
        raise ValidationError("content must be 1MB or less")
    
    return content


def validate_tags(tags: list[str] | None) -> list[str]:
    """
    Validate and normalize tags.
    
    Args:
        tags: List of tags to validate
        
    Returns:
        list[str]: Validated and normalized tags
    """
    if tags is None:
        return []
    
    validated_tags = []
    for tag in tags:
        tag = tag.strip()
        if tag:
            if len(tag) > 100:
                raise ValidationError(f"Tag '{tag}' exceeds 100 character limit")
            validated_tags.append(tag)
    
    # Remove duplicates and sort for consistent storage
    return sorted(set(validated_tags))


def validate_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """
    Validate metadata.
    
    Args:
        metadata: Metadata dictionary to validate
        
    Returns:
        dict[str, Any]: Validated metadata
        
    Raises:
        ValidationError: If metadata is invalid
    """
    if metadata is None:
        return {}
    
    if not isinstance(metadata, dict):
        raise ValidationError("metadata must be a dictionary")
    
    # Check for valid keys and reasonable size
    if len(metadata) > 100:
        raise ValidationError("metadata cannot have more than 100 keys")
    
    # Convert non-serializable values to strings
    validated = {}
    for key, value in metadata.items():
        if not isinstance(key, str):
            raise ValidationError(f"metadata key must be string, got {type(key)}")
        if len(key) > 100:
            raise ValidationError(f"metadata key '{key}' exceeds 100 character limit")
        
        # Ensure value is JSON-serializable
        try:
            import json
            json.dumps(value)
            validated[key] = value
        except (TypeError, ValueError):
            validated[key] = str(value)
    
    return validated


def validate_created_by(created_by: str | None) -> str | None:
    """
    Validate created_by field.
    
    Args:
        created_by: The creator identifier
        
    Returns:
        str or None: Validated creator identifier
    """
    if created_by is None:
        return None
    
    created_by = created_by.strip()
    
    if not created_by:
        return None
    
    if len(created_by) > 255:
        raise ValidationError("created_by must be 255 characters or less")
    
    return created_by


@dataclass(slots=True)
class Memory:
    """
    Represents a memory stored in Memorycore.
    
    Attributes:
        id: Unique identifier for the memory
        project_id: Project scope identifier
        memory_type: Type of memory (fact, decision, etc.)
        content: Main content of the memory
        summary: Optional summary of the content
        tags: List of tags for categorization
        status: Current status of the memory
        created_by: Identifier of the creator
        metadata: Additional metadata dictionary
        created_at: ISO format timestamp of creation
        updated_at: ISO format timestamp of last update
    """
    id: str
    project_id: str
    memory_type: str
    content: str
    summary: str | None
    tags: list[str]
    status: str
    created_by: str | None
    metadata: dict[str, Any]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the memory to a dictionary.
        
        Returns:
            dict: Dictionary representation of the memory
        """
        return asdict(self)

    def to_json(self) -> str:
        """
        Convert the memory to a JSON string.
        
        Returns:
            str: JSON representation of the memory
        """
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    def is_active(self) -> bool:
        """
        Check if the memory is active.
        
        Returns:
            bool: True if memory status is 'active'
        """
        return self.status == MemoryStatus.ACTIVE.value

    def is_archived(self) -> bool:
        """
        Check if the memory is archived.
        
        Returns:
            bool: True if memory status is 'archived'
        """
        return self.status == MemoryStatus.ARCHIVED.value

    def is_superseded(self) -> bool:
        """
        Check if the memory is superseded.
        
        Returns:
            bool: True if memory status is 'superseded'
        """
        return self.status == MemoryStatus.SUPERSEDED.value

    def age_seconds(self) -> float:
        """
        Calculate the age of the memory in seconds.
        
        Returns:
            float: Age in seconds
        """
        created = datetime.fromisoformat(self.created_at.replace('Z', '+00:00'))
        now = datetime.now(datetime.now().astimezone().tzinfo)
        return (now - created).total_seconds()

    def time_since_update_seconds(self) -> float:
        """
        Calculate time since last update in seconds.
        
        Returns:
            float: Time since update in seconds
        """
        updated = datetime.fromisoformat(self.updated_at.replace('Z', '+00:00'))
        now = datetime.now(datetime.now().astimezone().tzinfo)
        return (now - updated).total_seconds()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Memory":
        """
        Create a Memory from a dictionary.
        
        Args:
            data: Dictionary containing memory data
            
        Returns:
            Memory: Memory object created from dictionary
        """
        return cls(**data)
