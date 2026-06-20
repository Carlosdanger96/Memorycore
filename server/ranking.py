"""RRF (Reciprocal Rank Fusion) Ranking for Memory Core.

Implements RRF ranking algorithm to combine results from multiple search methods
(keyword, vector, graph-based) into a single ranked result set.

RRF is a simple, parameter-free ranking fusion method that works well for
combining heterogeneous result sets.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import math

import logging

logger = logging.getLogger(__name__)


@dataclass
class RankedResult:
    """A single ranked result with score and metadata."""
    memory_id: str
    score: float
    rank: int
    source: str  # Which search method produced this result
    metadata: Dict[str, Any]


@dataclass
class RRFResult:
    """Result of RRF ranking fusion."""
    results: List[RankedResult]
    total: int
    k: int  # RRF constant parameter

    def to_dict(self) -> Dict[str, Any]:
        return {
            "results": [
                {
                    "memory_id": r.memory_id,
                    "score": r.score,
                    "rank": r.rank,
                    "source": r.source,
                    "metadata": r.metadata,
                }
                for r in self.results
            ],
            "total": self.total,
            "k": self.k,
        }


class RRFRanker:
    """RRF (Reciprocal Rank Fusion) ranker.
    
    Combines multiple ranked result sets into a single fused ranking.
    The RRF algorithm assigns a score to each document based on its rank
    in each result set: score = 1 / (k + rank), where k is a constant.
    
    The final score for each document is the sum of its scores across all
    result sets where it appears.
    """

    def __init__(self, k: int = 60):
        """Initialize RRF ranker.
        
        Args:
            k: RRF constant parameter (default 60, higher values give more
               weight to top-ranked results)
        """
        self.k = k

    def fuse(
        self,
        result_sets: List[Tuple[str, List[Tuple[str, float]]]],
        limit: int = 100,
    ) -> RRFResult:
        """Fuse multiple result sets using RRF.
        
        Args:
            result_sets: List of (source_name, [(memory_id, score), ...])
                         tuples, where each inner list is a ranked result set
                         sorted by relevance (highest score first)
            limit: Maximum number of results to return
            
        Returns:
            RRFResult with fused ranking
        """
        # Collect all unique memory IDs
        all_memory_ids = set()
        for source, results in result_sets:
            for memory_id, _ in results:
                all_memory_ids.add(memory_id)
        
        # Calculate RRF scores for each memory
        scores: Dict[str, float] = {}
        metadata: Dict[str, Dict[str, Any]] = {}
        
        for source, results in result_sets:
            for rank, (memory_id, original_score) in enumerate(results, 1):
                # RRF score: 1 / (k + rank)
                rrf_score = 1.0 / (self.k + rank)
                
                if memory_id not in scores:
                    scores[memory_id] = 0.0
                    metadata[memory_id] = {}
                
                scores[memory_id] += rrf_score
                
                # Store metadata from first occurrence
                if "sources" not in metadata[memory_id]:
                    metadata[memory_id]["sources"] = []
                metadata[memory_id]["sources"].append(source)
                
                # Store original score from first source
                if "original_score" not in metadata[memory_id]:
                    metadata[memory_id]["original_score"] = original_score
        
        # Sort by RRF score (descending)
        sorted_results = sorted(
            [
                RankedResult(
                    memory_id=memory_id,
                    score=score,
                    rank=0,  # Will be set below
                    source=",".join(metadata[memory_id].get("sources", [])),
                    metadata=metadata[memory_id],
                )
                for memory_id, score in scores.items()
            ],
            key=lambda r: r.score,
            reverse=True,
        )
        
        # Set final ranks
        for i, result in enumerate(sorted_results, 1):
            result.rank = i
        
        # Limit results
        results = sorted_results[:limit]
        
        return RRFResult(
            results=results,
            total=len(scores),
            k=self.k,
        )

    def fuse_with_weights(
        self,
        result_sets: List[Tuple[str, List[Tuple[str, float]], float]],
        limit: int = 100,
    ) -> RRFResult:
        """Fuse multiple result sets using weighted RRF.
        
        Each result set can have a weight that scales its contribution
        to the final score.
        
        Args:
            result_sets: List of (source_name, [(memory_id, score), ...], weight)
            limit: Maximum number of results to return
            
        Returns:
            RRFResult with fused ranking
        """
        # Collect all unique memory IDs
        all_memory_ids = set()
        for source, results, _ in result_sets:
            for memory_id, _ in results:
                all_memory_ids.add(memory_id)
        
        # Calculate weighted RRF scores for each memory
        scores: Dict[str, float] = {}
        metadata: Dict[str, Dict[str, Any]] = {}
        
        for source, results, weight in result_sets:
            for rank, (memory_id, original_score) in enumerate(results, 1):
                # Weighted RRF score
                rrf_score = weight * (1.0 / (self.k + rank))
                
                if memory_id not in scores:
                    scores[memory_id] = 0.0
                    metadata[memory_id] = {}
                
                scores[memory_id] += rrf_score
                
                # Store metadata
                if "sources" not in metadata[memory_id]:
                    metadata[memory_id]["sources"] = []
                metadata[memory_id]["sources"].append(source)
                metadata[memory_id]["weights"] = metadata[memory_id].get("weights", {})
                metadata[memory_id]["weights"][source] = weight
                
                if "original_score" not in metadata[memory_id]:
                    metadata[memory_id]["original_score"] = original_score
        
        # Sort by weighted RRF score (descending)
        sorted_results = sorted(
            [
                RankedResult(
                    memory_id=memory_id,
                    score=score,
                    rank=0,
                    source=",".join(metadata[memory_id].get("sources", [])),
                    metadata=metadata[memory_id],
                )
                for memory_id, score in scores.items()
            ],
            key=lambda r: r.score,
            reverse=True,
        )
        
        # Set final ranks
        for i, result in enumerate(sorted_results, 1):
            result.rank = i
        
        # Limit results
        results = sorted_results[:limit]
        
        return RRFResult(
            results=results,
            total=len(scores),
            k=self.k,
        )

    def normalize_scores(
        self,
        result_sets: List[Tuple[str, List[Tuple[str, float]]]],
    ) -> List[Tuple[str, List[Tuple[str, float]]]]:
        """Normalize scores across result sets to [0, 1] range.
        
        Args:
            result_sets: List of (source_name, [(memory_id, score), ...])
            
        Returns:
            Normalized result sets
        """
        normalized = []
        
        for source, results in result_sets:
            if not results:
                normalized.append((source, []))
                continue
            
            # Get min and max scores
            scores = [score for _, score in results]
            min_score = min(scores)
            max_score = max(scores)
            
            # Avoid division by zero
            if max_score == min_score:
                normalized_scores = [(mid, 0.5) for mid, _ in results]
            else:
                normalized_scores = [
                    (mid, (score - min_score) / (max_score - min_score))
                    for mid, score in results
                ]
            
            normalized.append((source, normalized_scores))
        
        return normalized


class MemoryRanker:
    """Memory-specific ranker that combines multiple search strategies.
    
    Supports:
    - Keyword search (FTS)
    - Vector search (embeddings)
    - Graph-based ranking (link analysis)
    - Confidence/trust scoring
    """

    def __init__(self, rrf_k: int = 60):
        """Initialize memory ranker.
        
        Args:
            rrf_k: RRF constant parameter
        """
        self.rrf_ranker = RRFRanker(k=rrf_k)

    def rank_results(
        self,
        keyword_results: Optional[List[Tuple[str, float]]] = None,
        vector_results: Optional[List[Tuple[str, float]]] = None,
        graph_results: Optional[List[Tuple[str, float]]] = None,
        confidence_scores: Optional[Dict[str, float]] = None,
        trust_scores: Optional[Dict[str, float]] = None,
        limit: int = 100,
    ) -> RRFResult:
        """Rank memories using multiple signals.
        
        Args:
            keyword_results: Results from FTS search as (memory_id, score) tuples
            vector_results: Results from vector search as (memory_id, score) tuples
            graph_results: Results from graph analysis as (memory_id, score) tuples
            confidence_scores: Dictionary of memory_id -> confidence score
            trust_scores: Dictionary of memory_id -> trust score
            limit: Maximum number of results to return
            
        Returns:
            RRFResult with fused ranking
        """
        result_sets = []
        
        # Add keyword results
        if keyword_results:
            result_sets.append(("keyword", keyword_results))
        
        # Add vector results
        if vector_results:
            result_sets.append(("vector", vector_results))
        
        # Add graph results
        if graph_results:
            result_sets.append(("graph", graph_results))
        
        # If we have result sets, fuse them with RRF
        if result_sets:
            rrf_result = self.rrf_ranker.fuse(result_sets, limit=limit * 2)
        else:
            # No search results, return empty
            return RRFResult(results=[], total=0, k=self.rrf_ranker.k)
        
        # Apply confidence and trust boosts
        if confidence_scores or trust_scores:
            for result in rrf_result.results:
                memory_id = result.memory_id
                
                # Apply confidence boost
                if confidence_scores and memory_id in confidence_scores:
                    confidence_boost = confidence_scores[memory_id]
                    result.score *= (1.0 + confidence_boost * 0.5)  # 50% max boost
                    result.metadata["confidence_boost"] = confidence_boost
                
                # Apply trust boost
                if trust_scores and memory_id in trust_scores:
                    trust_boost = trust_scores[memory_id]
                    result.score *= (1.0 + trust_boost * 0.3)  # 30% max boost
                    result.metadata["trust_boost"] = trust_boost
        
        # Re-sort by final score
        rrf_result.results.sort(key=lambda r: r.score, reverse=True)
        
        # Re-set ranks
        for i, result in enumerate(rrf_result.results, 1):
            result.rank = i
        
        # Limit to requested size
        rrf_result.results = rrf_result.results[:limit]
        rrf_result.total = len(rrf_result.results)
        
        return rrf_result

    def rank_with_weights(
        self,
        keyword_results: Optional[List[Tuple[str, float]]] = None,
        vector_results: Optional[List[Tuple[str, float]]] = None,
        graph_results: Optional[List[Tuple[str, float]]] = None,
        keyword_weight: float = 1.0,
        vector_weight: float = 1.0,
        graph_weight: float = 1.0,
        limit: int = 100,
    ) -> RRFResult:
        """Rank memories with custom weights for each search method.
        
        Args:
            keyword_results: Results from FTS search
            vector_results: Results from vector search
            graph_results: Results from graph analysis
            keyword_weight: Weight for keyword search (default 1.0)
            vector_weight: Weight for vector search (default 1.0)
            graph_weight: Weight for graph search (default 1.0)
            limit: Maximum number of results to return
            
        Returns:
            RRFResult with fused ranking
        """
        result_sets = []
        
        if keyword_results:
            result_sets.append(("keyword", keyword_results, keyword_weight))
        
        if vector_results:
            result_sets.append(("vector", vector_results, vector_weight))
        
        if graph_results:
            result_sets.append(("graph", graph_results, graph_weight))
        
        if not result_sets:
            return RRFResult(results=[], total=0, k=self.rrf_ranker.k)
        
        return self.rrf_ranker.fuse_with_weights(result_sets, limit=limit)


class HybridRRFRanker:
    """Hybrid RRF ranker for combining vector, text, and graph results.
    
    Extends the basic RRF algorithm with:
    - Score normalization across different modalities
    - Custom weights for each search method
    - Confidence and trust boosting
    - Support for vector embeddings
    """

    def __init__(self, k: int = 60):
        """Initialize hybrid RRF ranker.
        
        Args:
            k: RRF constant parameter
        """
        self.k = k
        self.rrf_ranker = RRFRanker(k=k)

    def fuse_hybrid(
        self,
        vector_results: Optional[List[Tuple[str, float]]] = None,
        text_results: Optional[List[Tuple[str, float]]] = None,
        graph_results: Optional[List[Tuple[str, float]]] = None,
        vector_weight: float = 1.0,
        text_weight: float = 1.0,
        graph_weight: float = 1.0,
        limit: int = 100,
    ) -> RRFResult:
        """Fuse results from multiple modalities using RRF with weights.
        
        Args:
            vector_results: Results from vector search as (memory_id, score) tuples
            text_results: Results from text search as (memory_id, score) tuples
            graph_results: Results from graph analysis as (memory_id, score) tuples
            vector_weight: Weight for vector results (default 1.0)
            text_weight: Weight for text results (default 1.0)
            graph_weight: Weight for graph results (default 1.0)
            limit: Maximum number of results to return
            
        Returns:
            RRFResult with fused ranking
        """
        result_sets = []
        
        if vector_results:
            result_sets.append(("vector", vector_results, vector_weight))
        
        if text_results:
            result_sets.append(("text", text_results, text_weight))
        
        if graph_results:
            result_sets.append(("graph", graph_results, graph_weight))
        
        if not result_sets:
            return RRFResult(results=[], total=0, k=self.k)
        
        return self.rrf_ranker.fuse_with_weights(result_sets, limit=limit)

    def fuse_with_normalization(
        self,
        vector_results: Optional[List[Tuple[str, float]]] = None,
        text_results: Optional[List[Tuple[str, float]]] = None,
        graph_results: Optional[List[Tuple[str, float]]] = None,
        limit: int = 100,
    ) -> RRFResult:
        """Fuse results with automatic score normalization.
        
        Normalizes scores from each modality to [0, 1] range before fusion.
        
        Args:
            vector_results: Results from vector search
            text_results: Results from text search
            graph_results: Results from graph analysis
            limit: Maximum number of results to return
            
        Returns:
            RRFResult with fused ranking
        """
        result_sets = []
        
        if vector_results:
            # Vector scores are already cosine similarity (0-1)
            result_sets.append(("vector", vector_results))
        
        if text_results:
            # Normalize text scores
            scores = [score for _, score in text_results]
            if scores:
                min_score = min(scores)
                max_score = max(scores)
                if max_score > min_score:
                    normalized = [
                        (mid, (score - min_score) / (max_score - min_score))
                        for mid, score in text_results
                    ]
                else:
                    normalized = [(mid, 0.5) for mid, _ in text_results]
                result_sets.append(("text", normalized))
            else:
                result_sets.append(("text", []))
        
        if graph_results:
            # Normalize graph scores
            scores = [score for _, score in graph_results]
            if scores:
                min_score = min(scores)
                max_score = max(scores)
                if max_score > min_score:
                    normalized = [
                        (mid, (score - min_score) / (max_score - min_score))
                        for mid, score in graph_results
                    ]
                else:
                    normalized = [(mid, 0.5) for mid, _ in graph_results]
                result_sets.append(("graph", normalized))
            else:
                result_sets.append(("graph", []))
        
        if not result_sets:
            return RRFResult(results=[], total=0, k=self.k)
        
        return self.rrf_ranker.fuse(result_sets, limit=limit)

    def rank_with_vector_boost(
        self,
        results: List[Tuple[str, float]],
        vector_scores: Dict[str, float],
        vector_weight: float = 0.3,
        limit: int = 100,
    ) -> RRFResult:
        """Rank results with vector score boosting.
        
        Boosts results that have high vector similarity scores.
        
        Args:
            results: Base results as (memory_id, score) tuples
            vector_scores: Dictionary of memory_id -> vector similarity score
            vector_weight: Weight for vector boost (0.0 to 1.0)
            limit: Maximum number of results to return
            
        Returns:
            RRFResult with boosted ranking
        """
        # Apply vector boost to scores
        boosted_results = []
        for memory_id, score in results:
            vector_score = vector_scores.get(memory_id, 0.0)
            # Boost the score by vector similarity
            boosted_score = score * (1.0 + vector_score * vector_weight)
            boosted_results.append((memory_id, boosted_score))
        
        # Sort by boosted score
        boosted_results.sort(key=lambda x: x[1], reverse=True)
        
        # Convert to RankedResult format
        ranked_results = []
        for i, (memory_id, score) in enumerate(boosted_results[:limit], 1):
            ranked_results.append(RankedResult(
                memory_id=memory_id,
                score=score,
                rank=i,
                source="boosted",
                metadata={"vector_boost": vector_scores.get(memory_id, 0.0)},
            ))
        
        return RRFResult(
            results=ranked_results,
            total=len(boosted_results),
            k=self.k,
        )

    def rank_results(
        self,
        keyword_results: Optional[List[Tuple[str, float]]] = None,
        vector_results: Optional[List[Tuple[str, float]]] = None,
        graph_results: Optional[List[Tuple[str, float]]] = None,
        confidence_scores: Optional[Dict[str, float]] = None,
        trust_scores: Optional[Dict[str, float]] = None,
        limit: int = 100,
    ) -> RRFResult:
        """Rank memories using multiple signals.
        
        Args:
            keyword_results: Results from FTS search as (memory_id, score) tuples
            vector_results: Results from vector search as (memory_id, score) tuples
            graph_results: Results from graph analysis as (memory_id, score) tuples
            confidence_scores: Dictionary of memory_id -> confidence score
            trust_scores: Dictionary of memory_id -> trust score
            limit: Maximum number of results to return
            
        Returns:
            RRFResult with fused ranking
        """
        result_sets = []
        
        # Add keyword results
        if keyword_results:
            result_sets.append(("keyword", keyword_results))
        
        # Add vector results
        if vector_results:
            result_sets.append(("vector", vector_results))
        
        # Add graph results
        if graph_results:
            result_sets.append(("graph", graph_results))
        
        # If we have result sets, fuse them with RRF
        if result_sets:
            rrf_result = self.rrf_ranker.fuse(result_sets, limit=limit * 2)
        else:
            # No search results, return empty
            return RRFResult(results=[], total=0, k=self.rrf_ranker.k)
        
        # Apply confidence and trust boosts
        if confidence_scores or trust_scores:
            for result in rrf_result.results:
                memory_id = result.memory_id
                
                # Apply confidence boost
                if confidence_scores and memory_id in confidence_scores:
                    confidence_boost = confidence_scores[memory_id]
                    result.score *= (1.0 + confidence_boost * 0.5)  # 50% max boost
                    result.metadata["confidence_boost"] = confidence_boost
                
                # Apply trust boost
                if trust_scores and memory_id in trust_scores:
                    trust_boost = trust_scores[memory_id]
                    result.score *= (1.0 + trust_boost * 0.3)  # 30% max boost
                    result.metadata["trust_boost"] = trust_boost
        
        # Re-sort by final score
        rrf_result.results.sort(key=lambda r: r.score, reverse=True)
        
        # Re-set ranks
        for i, result in enumerate(rrf_result.results, 1):
            result.rank = i
        
        # Limit to requested size
        rrf_result.results = rrf_result.results[:limit]
        rrf_result.total = len(rrf_result.results)
        
        return rrf_result

    def rank_with_weights(
        self,
        keyword_results: Optional[List[Tuple[str, float]]] = None,
        vector_results: Optional[List[Tuple[str, float]]] = None,
        graph_results: Optional[List[Tuple[str, float]]] = None,
        keyword_weight: float = 1.0,
        vector_weight: float = 1.0,
        graph_weight: float = 1.0,
        limit: int = 100,
    ) -> RRFResult:
        """Rank memories with custom weights for each search method.
        
        Args:
            keyword_results: Results from FTS search
            vector_results: Results from vector search
            graph_results: Results from graph analysis
            keyword_weight: Weight for keyword search (default 1.0)
            vector_weight: Weight for vector search (default 1.0)
            graph_weight: Weight for graph search (default 1.0)
            limit: Maximum number of results to return
            
        Returns:
            RRFResult with fused ranking
        """
        result_sets = []
        
        if keyword_results:
            result_sets.append(("keyword", keyword_results, keyword_weight))
        
        if vector_results:
            result_sets.append(("vector", vector_results, vector_weight))
        
        if graph_results:
            result_sets.append(("graph", graph_results, graph_weight))
        
        if not result_sets:
            return RRFResult(results=[], total=0, k=self.rrf_ranker.k)
        
        return self.rrf_ranker.fuse_with_weights(result_sets, limit=limit)

    def hybrid_rank(
        self,
        keyword_results: Optional[List[Tuple[str, float]]] = None,
        vector_results: Optional[List[Tuple[str, float]]] = None,
        graph_results: Optional[List[Tuple[str, float]]] = None,
        confidence_scores: Optional[Dict[str, float]] = None,
        trust_scores: Optional[Dict[str, float]] = None,
        vector_weight: float = 1.0,
        text_weight: float = 1.0,
        graph_weight: float = 1.0,
        limit: int = 100,
    ) -> RRFResult:
        """Rank memories using hybrid RRF with vector support.
        
        Uses HybridRRFRanker for better handling of vector embeddings.
        
        Args:
            keyword_results: Results from FTS search
            vector_results: Results from vector search
            graph_results: Results from graph analysis
            confidence_scores: Dictionary of memory_id -> confidence score
            trust_scores: Dictionary of memory_id -> trust score
            vector_weight: Weight for vector results (default 1.0)
            text_weight: Weight for text results (default 1.0)
            graph_weight: Weight for graph results (default 1.0)
            limit: Maximum number of results to return
            
        Returns:
            RRFResult with fused ranking
        """
        hybrid_ranker = HybridRRFRanker(k=self.rrf_ranker.k)
        
        # Use weighted fusion
        rrf_result = hybrid_ranker.fuse_hybrid(
            vector_results=vector_results,
            text_results=keyword_results,
            graph_results=graph_results,
            vector_weight=vector_weight,
            text_weight=text_weight,
            graph_weight=graph_weight,
            limit=limit * 2,  # Get more results before applying boosts
        )
        
        # Apply confidence and trust boosts
        if confidence_scores or trust_scores:
            for result in rrf_result.results:
                memory_id = result.memory_id
                
                # Apply confidence boost
                if confidence_scores and memory_id in confidence_scores:
                    confidence_boost = confidence_scores[memory_id]
                    result.score *= (1.0 + confidence_boost * 0.5)
                    result.metadata["confidence_boost"] = confidence_boost
                
                # Apply trust boost
                if trust_scores and memory_id in trust_scores:
                    trust_boost = trust_scores[memory_id]
                    result.score *= (1.0 + trust_boost * 0.3)
                    result.metadata["trust_boost"] = trust_boost
        
        # Re-sort by final score
        rrf_result.results.sort(key=lambda r: r.score, reverse=True)
        
        # Re-set ranks
        for i, result in enumerate(rrf_result.results, 1):
            result.rank = i
        
        # Limit to requested size
        rrf_result.results = rrf_result.results[:limit]
        rrf_result.total = len(rrf_result.results)
        
        return rrf_result


def reciprocal_rank(rank: int, k: int = 60) -> float:
    """Calculate reciprocal rank score.
    
    Args:
        rank: The rank position (1-based)
        k: RRF constant
        
    Returns:
        Reciprocal rank score
    """
    return 1.0 / (k + rank)


def rrf_score(ranks: List[int], k: int = 60) -> float:
    """Calculate RRF score for a document across multiple result sets.
    
    Args:
        ranks: List of rank positions (1-based) in each result set
        k: RRF constant
        
    Returns:
        Total RRF score
    """
    return sum(1.0 / (k + rank) for rank in ranks)
