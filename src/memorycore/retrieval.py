"""
Memorycore retrieval utilities.

Provides full-text search query building and context rendering for LLM prompts.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Token pattern for FTS5 query building
_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)

# Phrase pattern for handling quoted phrases
_PHRASE_RE = re.compile(r'"([^"]+)"')


def build_fts_query(query: str) -> str:
    """
    Convert user text into a conservative FTS5 query.
    
    Handles:
    - Token-based AND queries
    - Quoted phrases (converted to AND of tokens)
    - Empty queries
    - Special character escaping
    
    Args:
        query: The user's search query
        
    Returns:
        str: FTS5 query string, or empty string if query is empty
        
    Example:
        >>> build_fts_query('SQLite OR "graph"')
        '"SQLite" AND "OR" AND "graph"'
        >>> build_fts_query("   ")
        ''
    """
    query = query.strip()
    if not query:
        return ""
    
    # Handle quoted phrases by extracting them and processing separately
    phrases = _PHRASE_RE.findall(query)
    
    # Remove phrases from query and process remaining tokens
    remaining_query = _PHRASE_RE.sub("", query)
    tokens = _TOKEN_RE.findall(remaining_query)
    
    # Combine phrase tokens and regular tokens
    all_tokens = []
    
    # Add phrase tokens
    for phrase in phrases:
        phrase_tokens = _TOKEN_RE.findall(phrase)
        all_tokens.extend(phrase_tokens)
    
    # Add regular tokens
    all_tokens.extend(tokens)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_tokens = []
    for token in all_tokens:
        if token not in seen:
            seen.add(token)
            unique_tokens.append(token)
    
    if not unique_tokens:
        return ""
    
    # Escape double quotes in tokens
    escaped_tokens = [
        token.replace(chr(34), chr(34) * 2) for token in unique_tokens
    ]
    
    # Build AND query
    if len(escaped_tokens) == 1:
        return f'"{escaped_tokens[0]}"'
    
    return " AND ".join(f'"{token}"' for token in escaped_tokens)


def render_context(
    memories: list[dict[str, Any]],
    *,
    include_metadata: bool = False,
    max_content_length: int | None = None,
    separator: str = "\n\n",
) -> str:
    """
    Render memories as context text for LLM prompts.
    
    Args:
        memories: List of memory dictionaries
        include_metadata: Whether to include metadata in output
        max_content_length: Maximum length for content (truncates if exceeded)
        separator: String to use between memory entries
        
    Returns:
        str: Formatted context text
        
    Example:
        >>> memories = [{"id": "m1", "memory_type": "fact",
        ...             "summary": "A summary", "content": "Full content"}]
        >>> render_context(memories)
        '[fact:m1] A summary\\nFull content'
    """
    if not memories:
        return ""
    
    blocks: list[str] = []
    
    for item in memories:
        # Get label (prefer summary, fall back to content)
        label = item.get("summary") or item.get("content", "")
        
        # Truncate label if too long
        if max_content_length and len(label) > max_content_length:
            label = label[:max_content_length] + "..."
        
        # Build the memory entry
        memory_type = item.get("memory_type", "unknown")
        memory_id = item.get("id", "unknown")
        content = item.get("content", "")
        
        # Truncate content if needed
        if max_content_length and len(content) > max_content_length:
            content = content[:max_content_length] + "..."
        
        # Build the block
        header = f"[{memory_type}:{memory_id}] {label}"
        
        metadata_str = ""
        if include_metadata and item.get("metadata"):
            metadata_str = f"\nMetadata: {item['metadata']}"
        
        block = f"{header}\n{content}{metadata_str}"
        blocks.append(block)
    
    return separator.join(blocks)


def build_advanced_fts_query(
    query: str,
    *,
    use_phrases: bool = False,
    use_prefix: bool = False,
) -> str:
    """
    Build an advanced FTS5 query with additional features.
    
    Args:
        query: The user's search query
        use_phrases: Whether to use phrase search for quoted text
        use_prefix: Whether to use prefix matching
        
    Returns:
        str: Advanced FTS5 query string
    """
    query = query.strip()
    if not query:
        return ""
    
    if use_phrases:
        # Handle quoted phrases as exact phrases
        parts = []
        remaining = query
        
        # Find all quoted phrases
        for match in _PHRASE_RE.finditer(query):
            phrase = match.group(1)
            if phrase:
                # Add remaining text before phrase
                before = remaining[:match.start()]
                if before.strip():
                    parts.append(f'({build_fts_query(before)})')
                
                # Add the phrase as exact match
                parts.append(f'"{phrase}"')
                
                # Update remaining text
                remaining = remaining[match.end():]
        
        # Add any remaining text
        if remaining.strip():
            parts.append(f'({build_fts_query(remaining)})')
        
        if parts:
            return " AND ".join(parts)
        return ""
    
    return build_fts_query(query)


def normalize_query(query: str) -> str:
    """
    Normalize a query string for consistent processing.
    
    Args:
        query: The query to normalize
        
    Returns:
        str: Normalized query string
    """
    # Convert to lowercase
    query = query.lower()
    
    # Remove extra whitespace
    query = re.sub(r'\s+', ' ', query)
    
    # Remove common punctuation that doesn't help search
    query = re.sub(r'[.,;:!?]', '', query)
    
    return query.strip()
