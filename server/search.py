"""Enhanced Search for Memory Core - Vector + FTS + Hybrid Search.

Provides advanced search capabilities including:
- Vector search using HNSW index
- Full-text search using FTS
- Hybrid search combining both
- Similarity scoring
- Result fusion
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VectorSearchResult:
    """Result of a vector search query."""
    memory_id: str
    project_id: str
    content: str
    summary: str
    tags: List[str]
    confidence: float
    trust_score: float
    status: str
    created_at: str
    score: float  # Cosine similarity (0.0 to 1.0)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "project_id": self.project_id,
            "content": self.content,
            "summary": self.summary,
            "tags": self.tags,
            "confidence": self.confidence,
            "trust_score": self.trust_score,
            "status": self.status,
            "created_at": self.created_at,
            "score": self.score,
        }


@dataclass
class TextSearchResult:
    """Result of a full-text search query."""
    memory_id: str
    project_id: str
    content: str
    summary: str
    tags: List[str]
    confidence: float
    trust_score: float
    status: str
    created_at: str
    score: float  # FTS score
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "project_id": self.project_id,
            "content": self.content,
            "summary": self.summary,
            "tags": self.tags,
            "confidence": self.confidence,
            "trust_score": self.trust_score,
            "status": self.status,
            "created_at": self.created_at,
            "score": self.score,
        }


@dataclass
class HybridSearchResult:
    """Result of a hybrid (vector + text) search query."""
    memory_id: str
    project_id: str
    content: str
    summary: str
    tags: List[str]
    confidence: float
    trust_score: float
    status: str
    created_at: str
    vector_score: Optional[float]  # Cosine similarity from vector search
    text_score: Optional[float]  # Score from FTS
    combined_score: float  # Weighted combination
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "project_id": self.project_id,
            "content": self.content,
            "summary": self.summary,
            "tags": self.tags,
            "confidence": self.confidence,
            "trust_score": self.trust_score,
            "status": self.status,
            "created_at": self.created_at,
            "vector_score": self.vector_score,
            "text_score": self.text_score,
            "combined_score": self.combined_score,
        }


@dataclass
class SearchResults:
    """Container for search results with pagination."""
    results: List[Any]  # Can be VectorSearchResult, TextSearchResult, or HybridSearchResult
    total: int
    limit: int
    offset: int
    query_time_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "results": [r.to_dict() for r in self.results],
            "total": self.total,
            "limit": self.limit,
            "offset": self.offset,
            "query_time_ms": self.query_time_ms,
        }


class VectorSearch:
    """Vector search using CozoDB HNSW index.
    
    Provides semantic search capabilities using vector embeddings.
    """
    
    def __init__(self, db: Any = None, db_path: str = "memorycore.cozo"):
        """Initialize vector search.
        
        Args:
            db: CozoDB database connection
            db_path: Path to CozoDB database
        """
        self.db = db
        self.db_path = db_path
        self._cozo = None
        
        if self.db is None:
            self._initialize_db()
    
    def _initialize_db(self) -> None:
        """Initialize CozoDB connection."""
        try:
            import cozo
            self._cozo = cozo
            self.db = self._cozo.Db(self.db_path)
        except ImportError:
            raise ImportError("CozoDB Python library is required. Install with: pip install cozo")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize CozoDB: {e}")
    
    def search(
        self,
        query_embedding: List[float],
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 100,
        ef_search: int = 100,
    ) -> SearchResults:
        """Perform vector search.
        
        Args:
            query_embedding: Query vector (768-dim float32)
            project_id: Optional filter by project ID
            status: Optional filter by status
            tags: Optional filter by tags (AND logic)
            limit: Maximum results
            ef_search: Search depth (higher = better quality, slower)
            
        Returns:
            SearchResults with vector search results
        """
        import time
        
        start_time = time.time()
        
        try:
            # Build query parameters
            params = {
                "query_embedding": query_embedding,
                "limit": limit,
                "ef_search": ef_search,
            }
            
            if project_id:
                params["project_id"] = project_id
            if status:
                params["status"] = status
            if tags:
                params["tags"] = tags
            
            # Execute vector search
            result = self.db.query(
                "vector_search_memories[query_embedding: $query_embedding, project_id: $project_id, "
                "status: $status, tags: $tags, limit: $limit, ef_search: $ef_search]",
                params
            )
            
            rows = list(result)
            
            # Convert to VectorSearchResult objects
            results = []
            for row in rows:
                results.append(VectorSearchResult(
                    memory_id=row.get("memory_id", ""),
                    project_id=row.get("project_id", ""),
                    content=row.get("content", ""),
                    summary=row.get("summary", ""),
                    tags=row.get("tags", []),
                    confidence=row.get("confidence", 0.0),
                    trust_score=row.get("trust_score", 0.0),
                    status=row.get("status", ""),
                    created_at=row.get("created_at", ""),
                    score=row.get("score", 0.0),
                ))
            
            query_time = (time.time() - start_time) * 1000
            
            return SearchResults(
                results=results,
                total=len(results),
                limit=limit,
                offset=0,
                query_time_ms=query_time,
            )
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            raise
    
    def nearest_neighbors(
        self,
        query_embedding: List[float],
        project_id: str,
        limit: int = 100,
        min_score: float = 0.0,
    ) -> SearchResults:
        """Find nearest neighbors within a project.
        
        Args:
            query_embedding: Query vector
            project_id: Project ID to search within
            limit: Maximum results
            min_score: Minimum similarity score (0.0 to 1.0)
            
        Returns:
            SearchResults with nearest neighbors
        """
        import time
        
        start_time = time.time()
        
        try:
            result = self.db.query(
                "nn_search_memories[query_embedding: $query_embedding, project_id: $project_id, "
                "limit: $limit, min_score: $min_score]",
                {
                    "query_embedding": query_embedding,
                    "project_id": project_id,
                    "limit": limit,
                    "min_score": min_score,
                }
            )
            
            rows = list(result)
            
            results = []
            for row in rows:
                results.append(VectorSearchResult(
                    memory_id=row.get("memory_id", ""),
                    project_id=row.get("project_id", ""),
                    content=row.get("content", ""),
                    summary=row.get("summary", ""),
                    tags=[],
                    confidence=0.0,
                    trust_score=0.0,
                    status="",
                    created_at="",
                    score=row.get("score", 0.0),
                ))
            
            query_time = (time.time() - start_time) * 1000
            
            return SearchResults(
                results=results,
                total=len(results),
                limit=limit,
                offset=0,
                query_time_ms=query_time,
            )
            
        except Exception as e:
            logger.error(f"Nearest neighbor search failed: {e}")
            raise


class TextSearch:
    """Full-text search using CozoDB FTS index.
    
    Provides keyword-based search capabilities.
    """
    
    def __init__(self, db: Any = None, db_path: str = "memorycore.cozo"):
        """Initialize text search.
        
        Args:
            db: CozoDB database connection
            db_path: Path to CozoDB database
        """
        self.db = db
        self.db_path = db_path
        self._cozo = None
        
        if self.db is None:
            self._initialize_db()
    
    def _initialize_db(self) -> None:
        """Initialize CozoDB connection."""
        try:
            import cozo
            self._cozo = cozo
            self.db = self._cozo.Db(self.db_path)
        except ImportError:
            raise ImportError("CozoDB Python library is required. Install with: pip install cozo")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize CozoDB: {e}")
    
    def search(
        self,
        query: str,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        tags: Optional[List[str]] = None,
        memory_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> SearchResults:
        """Perform full-text search.
        
        Args:
            query: Search query string
            project_id: Optional filter by project ID
            status: Optional filter by status
            tags: Optional filter by tags
            memory_type: Optional filter by memory type
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            SearchResults with text search results
        """
        import time
        
        start_time = time.time()
        
        try:
            # Build query parameters
            params = {
                "query": query,
                "limit": limit,
                "offset": offset,
            }
            
            if project_id:
                params["project_id"] = project_id
            if status:
                params["status"] = status
            if tags:
                params["tags"] = tags
            if memory_type:
                params["memory_type"] = memory_type
            
            # Execute FTS search
            result = self.db.query(
                "ft_search_memories[query: $query, project_id: $project_id, "
                "status: $status, tags: $tags, limit: $limit, offset: $offset]",
                params
            )
            
            rows = list(result)
            
            # Convert to TextSearchResult objects
            results = []
            for row in rows:
                results.append(TextSearchResult(
                    memory_id=row.get("memory_id", ""),
                    project_id=row.get("project_id", ""),
                    content=row.get("content", ""),
                    summary=row.get("summary", ""),
                    tags=row.get("tags", []),
                    confidence=row.get("confidence", 0.0),
                    trust_score=row.get("trust_score", 0.0),
                    status=row.get("status", ""),
                    created_at=row.get("created_at", ""),
                    score=row.get("score", 0.0),
                ))
            
            query_time = (time.time() - start_time) * 1000
            
            return SearchResults(
                results=results,
                total=len(results),
                limit=limit,
                offset=offset,
                query_time_ms=query_time,
            )
            
        except Exception as e:
            logger.error(f"Text search failed: {e}")
            raise


class HybridSearch:
    """Hybrid search combining vector and text search.
    
    Provides semantic + keyword search with weighted fusion.
    """
    
    def __init__(
        self,
        db: Any = None,
        db_path: str = "memorycore.cozo",
        vector_search: Optional[VectorSearch] = None,
        text_search: Optional[TextSearch] = None,
    ):
        """Initialize hybrid search.
        
        Args:
            db: CozoDB database connection
            db_path: Path to CozoDB database
            vector_search: Optional VectorSearch instance
            text_search: Optional TextSearch instance
        """
        self.db = db
        self.db_path = db_path
        self.vector_search = vector_search or VectorSearch(db, db_path)
        self.text_search = text_search or TextSearch(db, db_path)
    
    def search(
        self,
        query: Optional[str] = None,
        query_embedding: Optional[List[float]] = None,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        tags: Optional[List[str]] = None,
        memory_type: Optional[str] = None,
        limit: int = 100,
        vector_weight: float = 0.5,
        text_weight: float = 0.5,
        ef_search: int = 100,
    ) -> SearchResults:
        """Perform hybrid search (vector + text).
        
        Args:
            query: Optional text query for FTS
            query_embedding: Optional vector for semantic search
            project_id: Optional filter by project ID
            status: Optional filter by status
            tags: Optional filter by tags
            memory_type: Optional filter by memory type
            limit: Maximum results
            vector_weight: Weight for vector scores (0.0 to 1.0)
            text_weight: Weight for text scores (0.0 to 1.0)
            ef_search: Search depth for vector search
            
        Returns:
            SearchResults with hybrid search results
        """
        import time
        
        start_time = time.time()
        
        try:
            # Perform vector search if embedding provided
            vector_results = []
            if query_embedding is not None:
                vector_result = self.vector_search.search(
                    query_embedding=query_embedding,
                    project_id=project_id,
                    status=status,
                    tags=tags,
                    limit=limit,
                    ef_search=ef_search,
                )
                vector_results = vector_result.results
            
            # Perform text search if query provided
            text_results = []
            if query and query.strip():
                text_result = self.text_search.search(
                    query=query,
                    project_id=project_id,
                    status=status,
                    tags=tags,
                    memory_type=memory_type,
                    limit=limit,
                )
                text_results = text_result.results
            
            # Combine and deduplicate results
            combined: Dict[str, HybridSearchResult] = {}
            
            # Add vector results
            for vr in vector_results:
                if vr.memory_id not in combined:
                    combined[vr.memory_id] = HybridSearchResult(
                        memory_id=vr.memory_id,
                        project_id=vr.project_id,
                        content=vr.content,
                        summary=vr.summary,
                        tags=vr.tags,
                        confidence=vr.confidence,
                        trust_score=vr.trust_score,
                        status=vr.status,
                        created_at=vr.created_at,
                        vector_score=vr.score,
                        text_score=None,
                        combined_score=0.0,
                    )
                else:
                    combined[vr.memory_id].vector_score = vr.score
            
            # Add text results
            for tr in text_results:
                if tr.memory_id not in combined:
                    combined[tr.memory_id] = HybridSearchResult(
                        memory_id=tr.memory_id,
                        project_id=tr.project_id,
                        content=tr.content,
                        summary=tr.summary,
                        tags=tr.tags,
                        confidence=tr.confidence,
                        trust_score=tr.trust_score,
                        status=tr.status,
                        created_at=tr.created_at,
                        vector_score=None,
                        text_score=tr.score,
                        combined_score=0.0,
                    )
                else:
                    combined[tr.memory_id].text_score = tr.score
            
            # Calculate combined scores
            scored_results = []
            for mem_id, result in combined.items():
                v_score = result.vector_score if result.vector_score is not None else 0.0
                t_score = result.text_score if result.text_score is not None else 0.0
                
                # Normalize scores
                # Vector scores are already cosine similarity (0-1)
                # Text scores from FTS may need normalization
                v_norm = v_score
                t_norm = t_score / 100.0  # FTS scores can be higher
                
                # Apply weights
                combined_score = (v_norm * vector_weight) + (t_norm * text_weight)
                
                result.combined_score = combined_score
                scored_results.append(result)
            
            # Sort by combined score (descending)
            scored_results.sort(key=lambda r: r.combined_score, reverse=True)
            
            # Limit results
            final_results = scored_results[:limit]
            
            query_time = (time.time() - start_time) * 1000
            
            return SearchResults(
                results=final_results,
                total=len(combined),
                limit=limit,
                offset=0,
                query_time_ms=query_time,
            )
            
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            raise
    
    def search_with_rrf(
        self,
        query: Optional[str] = None,
        query_embedding: Optional[List[float]] = None,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 100,
        rrf_k: int = 60,
        ef_search: int = 100,
    ) -> SearchResults:
        """Perform hybrid search with RRF (Reciprocal Rank Fusion).
        
        Uses RRF to combine vector and text results without score normalization.
        
        Args:
            query: Optional text query for FTS
            query_embedding: Optional vector for semantic search
            project_id: Optional filter by project ID
            status: Optional filter by status
            tags: Optional filter by tags
            limit: Maximum results
            rrf_k: RRF constant parameter
            ef_search: Search depth for vector search
            
        Returns:
            SearchResults with RRF-fused hybrid search results
        """
        import time
        from server.ranking import RRFRanker
        
        start_time = time.time()
        
        try:
            ranker = RRFRanker(k=rrf_k)
            
            result_sets = []
            
            # Add vector results
            if query_embedding is not None:
                vector_result = self.vector_search.search(
                    query_embedding=query_embedding,
                    project_id=project_id,
                    status=status,
                    tags=tags,
                    limit=limit,
                    ef_search=ef_search,
                )
                vector_scores = [
                    (r.memory_id, r.score) for r in vector_result.results
                ]
                result_sets.append(("vector", vector_scores))
            
            # Add text results
            if query and query.strip():
                text_result = self.text_search.search(
                    query=query,
                    project_id=project_id,
                    status=status,
                    tags=tags,
                    limit=limit,
                )
                text_scores = [
                    (r.memory_id, r.score) for r in text_result.results
                ]
                result_sets.append(("text", text_scores))
            
            if not result_sets:
                return SearchResults(
                    results=[],
                    total=0,
                    limit=limit,
                    offset=0,
                    query_time_ms=0.0,
                )
            
            # Fuse with RRF
            rrf_result = ranker.fuse(result_sets, limit=limit)
            
            # Build final results
            memory_map: Dict[str, Dict[str, Any]] = {}
            
            # Collect all memory data
            if query_embedding is not None:
                for r in vector_result.results:
                    memory_map[r.memory_id] = {
                        "memory_id": r.memory_id,
                        "project_id": r.project_id,
                        "content": r.content,
                        "summary": r.summary,
                        "tags": r.tags,
                        "confidence": r.confidence,
                        "trust_score": r.trust_score,
                        "status": r.status,
                        "created_at": r.created_at,
                    }
            
            if query and query.strip():
                for r in text_result.results:
                    if r.memory_id not in memory_map:
                        memory_map[r.memory_id] = {
                            "memory_id": r.memory_id,
                            "project_id": r.project_id,
                            "content": r.content,
                            "summary": r.summary,
                            "tags": r.tags,
                            "confidence": r.confidence,
                            "trust_score": r.trust_score,
                            "status": r.status,
                            "created_at": r.created_at,
                        }
            
            # Create final results
            final_results = []
            for ranked in rrf_result.results:
                mem_data = memory_map.get(ranked.memory_id, {})
                final_results.append(HybridSearchResult(
                    memory_id=ranked.memory_id,
                    project_id=mem_data.get("project_id", ""),
                    content=mem_data.get("content", ""),
                    summary=mem_data.get("summary", ""),
                    tags=mem_data.get("tags", []),
                    confidence=mem_data.get("confidence", 0.0),
                    trust_score=mem_data.get("trust_score", 0.0),
                    status=mem_data.get("status", ""),
                    created_at=mem_data.get("created_at", ""),
                    vector_score=None,
                    text_score=None,
                    combined_score=ranked.score,
                ))
            
            query_time = (time.time() - start_time) * 1000
            
            return SearchResults(
                results=final_results,
                total=rrf_result.total,
                limit=limit,
                offset=0,
                query_time_ms=query_time,
            )
            
        except Exception as e:
            logger.error(f"Hybrid search with RRF failed: {e}")
            raise


class SearchManager:
    """Unified search manager for all search types.
    
    Provides a single interface for vector, text, and hybrid search.
    """
    
    def __init__(
        self,
        db: Any = None,
        db_path: str = "memorycore.cozo",
    ):
        """Initialize search manager.
        
        Args:
            db: CozoDB database connection
            db_path: Path to CozoDB database
        """
        self.db = db
        self.db_path = db_path
        self.vector_search = VectorSearch(db, db_path)
        self.text_search = TextSearch(db, db_path)
        self.hybrid_search = HybridSearch(db, db_path)
    
    def vector_search(
        self,
        query_embedding: List[float],
        **kwargs,
    ) -> SearchResults:
        """Perform vector search."""
        return self.vector_search.search(query_embedding, **kwargs)
    
    def text_search(
        self,
        query: str,
        **kwargs,
    ) -> SearchResults:
        """Perform text search."""
        return self.text_search.search(query, **kwargs)
    
    def hybrid_search(
        self,
        query: Optional[str] = None,
        query_embedding: Optional[List[float]] = None,
        **kwargs,
    ) -> SearchResults:
        """Perform hybrid search."""
        return self.hybrid_search.search(query, query_embedding, **kwargs)
    
    def hybrid_search_rrf(
        self,
        query: Optional[str] = None,
        query_embedding: Optional[List[float]] = None,
        **kwargs,
    ) -> SearchResults:
        """Perform hybrid search with RRF fusion."""
        return self.hybrid_search.search_with_rrf(query, query_embedding, **kwargs)


# Utility functions
def generate_query_embedding(
    query: str,
    embedding_generator: Any = None,
) -> Optional[List[float]]:
    """Generate embedding for a query string.
    
    Args:
        query: Query string
        embedding_generator: Optional embedding generator
        
    Returns:
        Query embedding or None if generation fails
    """
    if not query or not query.strip():
        return None
    
    if embedding_generator is None:
        from server.embedding import LocalEmbeddingSidecar
        embedding_generator = LocalEmbeddingSidecar()
        embedding_generator.initialize()
    
    try:
        result = embedding_generator.generate(query)
        return result.embedding
    except Exception as e:
        logger.warning(f"Failed to generate query embedding: {e}")
        return None
