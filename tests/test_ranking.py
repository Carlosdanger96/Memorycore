"""Tests for RRF Ranking implementation."""

import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "server"))

from ranking import (
    RRFRanker,
    MemoryRanker,
    RankedResult,
    RRFResult,
    reciprocal_rank,
    rrf_score,
)


class TestRRFRanker(unittest.TestCase):
    """Test cases for RRFRanker."""

    def test_fuse_single_result_set(self):
        """Test fusing a single result set."""
        ranker = RRFRanker(k=60)
        
        result_sets = [
            ("source1", [
                ("mem1", 1.0),
                ("mem2", 0.9),
                ("mem3", 0.8),
            ]),
        ]
        
        result = ranker.fuse(result_sets, limit=10)
        
        self.assertEqual(len(result.results), 3)
        self.assertEqual(result.total, 3)
        self.assertEqual(result.k, 60)
        
        # Check order (should be same as input since only one source)
        self.assertEqual(result.results[0].memory_id, "mem1")
        self.assertEqual(result.results[1].memory_id, "mem2")
        self.assertEqual(result.results[2].memory_id, "mem3")

    def test_fuse_multiple_result_sets(self):
        """Test fusing multiple result sets."""
        ranker = RRFRanker(k=60)
        
        result_sets = [
            ("source1", [
                ("mem1", 1.0),
                ("mem2", 0.9),
                ("mem3", 0.8),
            ]),
            ("source2", [
                ("mem1", 1.0),  # mem1 appears in both
                ("mem4", 0.95),
                ("mem5", 0.85),
            ]),
        ]
        
        result = ranker.fuse(result_sets, limit=10)
        
        # mem1 should be first since it appears in both result sets
        self.assertEqual(result.results[0].memory_id, "mem1")
        self.assertIn("source1", result.results[0].source)
        self.assertIn("source2", result.results[0].source)

    def test_fuse_with_different_ranks(self):
        """Test that RRF properly weights by rank."""
        ranker = RRFRanker(k=60)
        
        # mem1 is rank 1 in source1, mem2 is rank 1 in source2
        # mem3 is rank 2 in both
        result_sets = [
            ("source1", [
                ("mem1", 1.0),
                ("mem3", 0.9),
            ]),
            ("source2", [
                ("mem2", 1.0),
                ("mem3", 0.9),
            ]),
        ]
        
        result = ranker.fuse(result_sets, limit=10)
        
        # mem1 and mem2 should be tied or very close (both rank 1 in one source)
        # mem3 should be lower (rank 2 in both)
        self.assertIn(result.results[0].memory_id, ["mem1", "mem2"])
        self.assertIn(result.results[1].memory_id, ["mem1", "mem2"])
        self.assertEqual(result.results[2].memory_id, "mem3")

    def test_fuse_with_weights(self):
        """Test fusing with custom weights."""
        ranker = RRFRanker(k=60)
        
        result_sets = [
            ("source1", [("mem1", 1.0), ("mem2", 0.9)], 2.0),  # Higher weight
            ("source2", [("mem1", 1.0), ("mem3", 0.8)], 1.0),  # Lower weight
        ]
        
        result = ranker.fuse_with_weights(result_sets, limit=10)
        
        # mem1 should be first (appears in both, with higher weight in source1)
        self.assertEqual(result.results[0].memory_id, "mem1")

    def test_empty_result_sets(self):
        """Test fusing empty result sets."""
        ranker = RRFRanker(k=60)
        
        result = ranker.fuse([], limit=10)
        
        self.assertEqual(len(result.results), 0)
        self.assertEqual(result.total, 0)

    def test_limit_results(self):
        """Test that limit is respected."""
        ranker = RRFRanker(k=60)
        
        result_sets = [
            ("source1", [(f"mem{i}", 1.0 - i * 0.01) for i in range(100)]),
        ]
        
        result = ranker.fuse(result_sets, limit=10)
        
        self.assertEqual(len(result.results), 10)
        self.assertEqual(result.total, 100)  # Total should still be 100

    def test_normalize_scores(self):
        """Test score normalization."""
        ranker = RRFRanker(k=60)
        
        result_sets = [
            ("source1", [("mem1", 10.0), ("mem2", 5.0), ("mem3", 1.0)]),
        ]
        
        normalized = ranker.normalize_scores(result_sets)
        
        # Check that scores are normalized to [0, 1]
        source, results = normalized[0]
        self.assertEqual(source, "source1")
        
        # First should be 1.0 (max), last should be 0.0 (min)
        self.assertAlmostEqual(results[0][1], 1.0)
        self.assertAlmostEqual(results[-1][1], 0.0)


class TestMemoryRanker(unittest.TestCase):
    """Test cases for MemoryRanker."""

    def test_rank_with_keyword_only(self):
        """Test ranking with only keyword results."""
        ranker = MemoryRanker()
        
        keyword_results = [
            ("mem1", 1.0),
            ("mem2", 0.9),
            ("mem3", 0.8),
        ]
        
        result = ranker.rank_results(
            keyword_results=keyword_results,
            limit=10,
        )
        
        self.assertEqual(len(result.results), 3)
        self.assertEqual(result.results[0].memory_id, "mem1")

    def test_rank_with_multiple_sources(self):
        """Test ranking with multiple sources."""
        ranker = MemoryRanker()
        
        keyword_results = [
            ("mem1", 1.0),
            ("mem2", 0.9),
        ]
        
        vector_results = [
            ("mem1", 0.95),
            ("mem3", 0.85),
        ]
        
        result = ranker.rank_results(
            keyword_results=keyword_results,
            vector_results=vector_results,
            limit=10,
        )
        
        # mem1 should be first (appears in both)
        self.assertEqual(result.results[0].memory_id, "mem1")

    def test_rank_with_confidence_boost(self):
        """Test ranking with confidence boost."""
        ranker = MemoryRanker()
        
        keyword_results = [
            ("mem1", 0.8),
            ("mem2", 0.9),
        ]
        
        confidence_scores = {
            "mem1": 0.9,  # High confidence
            "mem2": 0.1,  # Low confidence
        }
        
        result = ranker.rank_results(
            keyword_results=keyword_results,
            confidence_scores=confidence_scores,
            limit=10,
        )
        
        # mem1 should be first due to confidence boost
        self.assertEqual(result.results[0].memory_id, "mem1")
        self.assertIn("confidence_boost", result.results[0].metadata)

    def test_rank_with_trust_boost(self):
        """Test ranking with trust boost."""
        ranker = MemoryRanker()
        
        keyword_results = [
            ("mem1", 0.8),
            ("mem2", 0.9),
        ]
        
        trust_scores = {
            "mem1": 0.9,  # High trust
            "mem2": 0.1,  # Low trust
        }
        
        result = ranker.rank_results(
            keyword_results=keyword_results,
            trust_scores=trust_scores,
            limit=10,
        )
        
        # mem1 should be first due to trust boost
        self.assertEqual(result.results[0].memory_id, "mem1")
        self.assertIn("trust_boost", result.results[0].metadata)

    def test_rank_with_weights(self):
        """Test ranking with custom weights."""
        ranker = MemoryRanker()
        
        keyword_results = [("mem1", 1.0), ("mem2", 0.9)]
        vector_results = [("mem1", 0.8), ("mem3", 0.95)]
        
        result = ranker.rank_with_weights(
            keyword_results=keyword_results,
            vector_results=vector_results,
            keyword_weight=2.0,
            vector_weight=1.0,
            limit=10,
        )
        
        # mem1 should be first (appears in both, with higher weight on keyword)
        self.assertEqual(result.results[0].memory_id, "mem1")

    def test_empty_results(self):
        """Test ranking with no results."""
        ranker = MemoryRanker()
        
        result = ranker.rank_results(limit=10)
        
        self.assertEqual(len(result.results), 0)
        self.assertEqual(result.total, 0)


class TestUtilityFunctions(unittest.TestCase):
    """Test cases for utility functions."""

    def test_reciprocal_rank(self):
        """Test reciprocal rank calculation."""
        # Rank 1 with k=60 should be 1/61
        self.assertAlmostEqual(reciprocal_rank(1, 60), 1.0 / 61.0)
        
        # Rank 10 with k=60 should be 1/70
        self.assertAlmostEqual(reciprocal_rank(10, 60), 1.0 / 70.0)
        
        # Higher k should give lower score for same rank
        self.assertLess(reciprocal_rank(1, 100), reciprocal_rank(1, 60))

    def test_rrf_score(self):
        """Test RRF score calculation."""
        # Single rank
        self.assertAlmostEqual(rrf_score([1], 60), 1.0 / 61.0)
        
        # Multiple ranks
        score = rrf_score([1, 2, 3], 60)
        expected = 1.0 / 61.0 + 1.0 / 62.0 + 1.0 / 63.0
        self.assertAlmostEqual(score, expected)


class TestRankedResult(unittest.TestCase):
    """Test cases for RankedResult dataclass."""

    def test_ranked_result_creation(self):
        """Test creating a RankedResult."""
        result = RankedResult(
            memory_id="mem1",
            score=0.95,
            rank=1,
            source="keyword",
            metadata={"key": "value"},
        )
        
        self.assertEqual(result.memory_id, "mem1")
        self.assertEqual(result.score, 0.95)
        self.assertEqual(result.rank, 1)
        self.assertEqual(result.source, "keyword")
        self.assertEqual(result.metadata, {"key": "value"})

    def test_rrf_result_to_dict(self):
        """Test RRFResult to_dict."""
        result = RRFResult(
            results=[
                RankedResult("mem1", 0.95, 1, "source1", {}),
                RankedResult("mem2", 0.90, 2, "source2", {}),
            ],
            total=2,
            k=60,
        )
        
        data = result.to_dict()
        
        self.assertEqual(len(data["results"]), 2)
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["k"], 60)


if __name__ == "__main__":
    unittest.main()
