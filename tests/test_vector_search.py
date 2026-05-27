"""Tests for Vector Search implementation."""

import os
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "server"))

from embedding import (
    EmbeddingConfig,
    EmbeddingResult,
    EmbeddingGenerator,
    LocalEmbeddingSidecar,
    NullEmbeddingGenerator,
    EmbeddingManager,
    cosine_similarity,
    euclidean_distance,
    normalize_vector,
    vector_dimension,
    validate_embedding,
)
from search import (
    VectorSearch,
    TextSearch,
    HybridSearch,
    SearchManager,
    VectorSearchResult,
    TextSearchResult,
    HybridSearchResult,
    SearchResults,
    generate_query_embedding,
)
from ranking import HybridRRFRanker


class TestEmbeddingConfig(unittest.TestCase):
    """Test cases for EmbeddingConfig."""

    def test_default_config(self):
        """Test default embedding configuration."""
        config = EmbeddingConfig()
        
        self.assertEqual(config.model_name, "all-MiniLM-L6-v2")
        self.assertEqual(config.dimension, 768)
        self.assertEqual(config.batch_size, 32)
        self.assertEqual(config.device, "cpu")
        self.assertTrue(config.normalize)
        self.assertFalse(config.trust_remote_code)

    def test_custom_config(self):
        """Test custom embedding configuration."""
        config = EmbeddingConfig(
            model_name="custom-model",
            dimension=384,
            batch_size=64,
            device="cuda",
            normalize=False,
        )
        
        self.assertEqual(config.model_name, "custom-model")
        self.assertEqual(config.dimension, 384)
        self.assertEqual(config.batch_size, 64)
        self.assertEqual(config.device, "cuda")
        self.assertFalse(config.normalize)

    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = EmbeddingConfig()
        data = config.to_dict()
        
        self.assertIn("model_name", data)
        self.assertIn("dimension", data)
        self.assertIn("batch_size", data)
        self.assertIn("device", data)

    def test_from_dict(self):
        """Test creating config from dictionary."""
        data = {
            "model_name": "test-model",
            "dimension": 512,
            "batch_size": 16,
        }
        config = EmbeddingConfig.from_dict(data)
        
        self.assertEqual(config.model_name, "test-model")
        self.assertEqual(config.dimension, 512)
        self.assertEqual(config.batch_size, 16)


class TestEmbeddingResult(unittest.TestCase):
    """Test cases for EmbeddingResult."""

    def test_creation(self):
        """Test creating an embedding result."""
        result = EmbeddingResult(
            text="test text",
            embedding=[0.1, 0.2, 0.3],
            model_name="test-model",
            dimension=3,
            generated_at="2024-01-01T00:00:00",
            processing_time_ms=10.0,
        )
        
        self.assertEqual(result.text, "test text")
        self.assertEqual(result.embedding, [0.1, 0.2, 0.3])
        self.assertEqual(result.model_name, "test-model")
        self.assertEqual(result.dimension, 3)

    def test_to_dict(self):
        """Test converting embedding result to dictionary."""
        result = EmbeddingResult(
            text="test",
            embedding=[0.1, 0.2],
            model_name="model",
            dimension=2,
            generated_at="2024-01-01",
        )
        
        data = result.to_dict()
        
        self.assertEqual(data["text"], "test")
        self.assertEqual(data["embedding"], [0.1, 0.2])
        self.assertEqual(data["model_name"], "model")

    def test_to_cozo_format(self):
        """Test converting to CozoDB format."""
        result = EmbeddingResult(
            text="test",
            embedding=[0.1, 0.2, 0.3],
            model_name="model",
            dimension=3,
            generated_at="2024-01-01",
        )
        
        cozo_embedding = result.to_cozo_format()
        
        self.assertIsInstance(cozo_embedding, list)
        self.assertEqual(len(cozo_embedding), 3)
        self.assertAllClose(cozo_embedding, [0.1, 0.2, 0.3])

    def test_from_dict(self):
        """Test creating embedding result from dictionary."""
        data = {
            "text": "test",
            "embedding": [0.1, 0.2],
            "model_name": "model",
            "dimension": 2,
            "generated_at": "2024-01-01",
        }
        
        result = EmbeddingResult.from_dict(data)
        
        self.assertEqual(result.text, "test")
        self.assertEqual(result.embedding, [0.1, 0.2])

    def assertAllClose(self, a, b, rtol=1e-5, atol=1e-8):
        """Helper to check if lists are approximately equal."""
        self.assertEqual(len(a), len(b))
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, delta=atol)


class TestLocalEmbeddingSidecar(unittest.TestCase):
    """Test cases for LocalEmbeddingSidecar."""

    def test_initialization(self):
        """Test initializing the embedding sidecar."""
        sidecar = LocalEmbeddingSidecar()
        sidecar.initialize()
        
        self.assertTrue(sidecar.is_initialized())
        sidecar.close()

    def test_generate_single(self):
        """Test generating a single embedding."""
        sidecar = LocalEmbeddingSidecar()
        sidecar.initialize()
        
        result = sidecar.generate("test text")
        
        self.assertIsNotNone(result)
        self.assertEqual(result.text, "test text")
        self.assertEqual(len(result.embedding), 768)  # Default dimension
        self.assertEqual(result.dimension, 768)
        self.assertIsNotNone(result.generated_at)
        
        sidecar.close()

    def test_generate_batch(self):
        """Test generating batch embeddings."""
        sidecar = LocalEmbeddingSidecar()
        sidecar.initialize()
        
        texts = ["text 1", "text 2", "text 3"]
        results = sidecar.generate_batch(texts)
        
        self.assertEqual(len(results), 3)
        for i, result in enumerate(results):
            self.assertEqual(result.text, texts[i])
            self.assertEqual(len(result.embedding), 768)
        
        sidecar.close()

    def test_deterministic_embeddings(self):
        """Test that same text produces same embedding (for stub)."""
        sidecar = LocalEmbeddingSidecar()
        sidecar.initialize()
        
        result1 = sidecar.generate("test text")
        result2 = sidecar.generate("test text")
        
        # Same text should produce same embedding in stub
        self.assertEqual(result1.embedding, result2.embedding)
        
        sidecar.close()

    def test_different_texts_different_embeddings(self):
        """Test that different texts produce different embeddings."""
        sidecar = LocalEmbeddingSidecar()
        sidecar.initialize()
        
        result1 = sidecar.generate("text a")
        result2 = sidecar.generate("text b")
        
        # Different texts should produce different embeddings
        self.assertNotEqual(result1.embedding, result2.embedding)
        
        sidecar.close()

    def test_normalized_embeddings(self):
        """Test that embeddings are normalized."""
        sidecar = LocalEmbeddingSidecar()
        sidecar.initialize()
        
        result = sidecar.generate("test text")
        embedding = result.embedding
        
        # Check normalization: sum of squares should be ~1
        norm = (sum(x**2 for x in embedding) ** 0.5)
        self.assertAlmostEqual(norm, 1.0, delta=0.01)
        
        sidecar.close()


class TestNullEmbeddingGenerator(unittest.TestCase):
    """Test cases for NullEmbeddingGenerator."""

    def test_generate(self):
        """Test null generator returns zero vector."""
        generator = NullEmbeddingGenerator()
        generator.initialize()
        
        result = generator.generate("test")
        
        self.assertEqual(result.text, "test")
        self.assertEqual(result.embedding, [0.0] * 768)
        
        generator.close()


class TestEmbeddingManager(unittest.TestCase):
    """Test cases for EmbeddingManager."""

    def test_generate(self):
        """Test generating embedding through manager."""
        manager = EmbeddingManager()
        
        result = manager.generate("test text")
        
        self.assertIsNotNone(result)
        self.assertEqual(len(result.embedding), 768)
        
        manager.close()

    def test_generate_for_memory(self):
        """Test generating embedding for a memory record."""
        manager = EmbeddingManager()
        
        result = manager.generate_for_memory(
            content="This is the content",
            summary="This is the summary",
            tags=["tag1", "tag2"],
        )
        
        self.assertIsNotNone(result)
        self.assertEqual(len(result.embedding), 768)
        # The text should contain all parts
        self.assertIn("content", result.text.lower())
        
        manager.close()


class TestUtilityFunctions(unittest.TestCase):
    """Test cases for utility functions."""

    def test_cosine_similarity(self):
        """Test cosine similarity calculation."""
        # Same vectors should have similarity 1.0
        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        self.assertAlmostEqual(cosine_similarity(a, b), 1.0)
        
        # Orthogonal vectors should have similarity 0.0
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        self.assertAlmostEqual(cosine_similarity(a, b), 0.0)
        
        # Opposite vectors should have similarity -1.0
        a = [1.0, 0.0, 0.0]
        b = [-1.0, 0.0, 0.0]
        self.assertAlmostEqual(cosine_similarity(a, b), -1.0)

    def test_cosine_similarity_normalized(self):
        """Test cosine similarity with normalized vectors."""
        a = normalize_vector([1.0, 1.0, 0.0])
        b = normalize_vector([1.0, 0.0, 0.0])
        
        # cos(theta) where theta is 45 degrees = sqrt(2)/2
        expected = (2**0.5) / 2
        self.assertAlmostEqual(cosine_similarity(a, b), expected, delta=0.001)

    def test_euclidean_distance(self):
        """Test Euclidean distance calculation."""
        # Distance between same points should be 0
        a = [1.0, 2.0, 3.0]
        b = [1.0, 2.0, 3.0]
        self.assertAlmostEqual(euclidean_distance(a, b), 0.0)
        
        # Distance between (0,0) and (1,0) should be 1
        a = [0.0, 0.0]
        b = [1.0, 0.0]
        self.assertAlmostEqual(euclidean_distance(a, b), 1.0)
        
        # Distance between (0,0) and (0,1) should be 1
        a = [0.0, 0.0]
        b = [0.0, 1.0]
        self.assertAlmostEqual(euclidean_distance(a, b), 1.0)

    def test_normalize_vector(self):
        """Test vector normalization."""
        v = [3.0, 4.0, 0.0]
        normalized = normalize_vector(v)
        
        # Norm should be 1
        norm = (sum(x**2 for x in normalized) ** 0.5)
        self.assertAlmostEqual(norm, 1.0)
        
        # Direction should be preserved
        self.assertAlmostEqual(normalized[0] / v[0], normalized[1] / v[1])

    def test_vector_dimension(self):
        """Test getting vector dimension."""
        v = [1.0, 2.0, 3.0, 4.0]
        self.assertEqual(vector_dimension(v), 4)

    def test_validate_embedding(self):
        """Test embedding validation."""
        # Valid embedding
        valid = [0.0] * 768
        self.assertTrue(validate_embedding(valid, 768))
        
        # Invalid dimension
        invalid = [0.0] * 384
        self.assertFalse(validate_embedding(invalid, 768))
        
        # Valid with different expected dimension
        self.assertTrue(validate_embedding(invalid, 384))


class TestHybridRRFRanker(unittest.TestCase):
    """Test cases for HybridRRFRanker."""

    def test_fuse_hybrid(self):
        """Test fusing hybrid results."""
        ranker = HybridRRFRanker(k=60)
        
        vector_results = [("mem1", 0.9), ("mem2", 0.8)]
        text_results = [("mem1", 100.0), ("mem3", 90.0)]
        
        result = ranker.fuse_hybrid(
            vector_results=vector_results,
            text_results=text_results,
            limit=10,
        )
        
        self.assertEqual(len(result.results), 3)
        # mem1 should be first (appears in both)
        self.assertEqual(result.results[0].memory_id, "mem1")

    def test_fuse_with_normalization(self):
        """Test fusing with score normalization."""
        ranker = HybridRRFRanker(k=60)
        
        # Text scores with different ranges
        text_results = [("mem1", 100.0), ("mem2", 50.0)]
        
        result = ranker.fuse_with_normalization(
            text_results=text_results,
            limit=10,
        )
        
        self.assertEqual(len(result.results), 2)

    def test_rank_with_vector_boost(self):
        """Test ranking with vector boost."""
        ranker = HybridRRFRanker(k=60)
        
        results = [("mem1", 10.0), ("mem2", 9.0)]
        vector_scores = {"mem1": 0.9, "mem2": 0.1}
        
        result = ranker.rank_with_vector_boost(
            results=results,
            vector_scores=vector_scores,
            vector_weight=0.5,
            limit=10,
        )
        
        # mem1 should be first due to higher vector score
        self.assertEqual(result.results[0].memory_id, "mem1")
        self.assertIn("vector_boost", result.results[0].metadata)


class TestSearchResults(unittest.TestCase):
    """Test cases for search result classes."""

    def test_vector_search_result(self):
        """Test VectorSearchResult creation."""
        result = VectorSearchResult(
            memory_id="mem1",
            project_id="proj1",
            content="test content",
            summary="test summary",
            tags=["tag1"],
            confidence=0.9,
            trust_score=0.8,
            status="accepted",
            created_at="2024-01-01",
            score=0.95,
        )
        
        self.assertEqual(result.memory_id, "mem1")
        self.assertEqual(result.score, 0.95)
        
        data = result.to_dict()
        self.assertIn("memory_id", data)
        self.assertIn("score", data)

    def test_text_search_result(self):
        """Test TextSearchResult creation."""
        result = TextSearchResult(
            memory_id="mem1",
            project_id="proj1",
            content="test content",
            summary="test summary",
            tags=["tag1"],
            confidence=0.9,
            trust_score=0.8,
            status="accepted",
            created_at="2024-01-01",
            score=100.0,
        )
        
        self.assertEqual(result.memory_id, "mem1")
        self.assertEqual(result.score, 100.0)

    def test_hybrid_search_result(self):
        """Test HybridSearchResult creation."""
        result = HybridSearchResult(
            memory_id="mem1",
            project_id="proj1",
            content="test content",
            summary="test summary",
            tags=["tag1"],
            confidence=0.9,
            trust_score=0.8,
            status="accepted",
            created_at="2024-01-01",
            vector_score=0.95,
            text_score=100.0,
            combined_score=0.975,
        )
        
        self.assertEqual(result.memory_id, "mem1")
        self.assertEqual(result.vector_score, 0.95)
        self.assertEqual(result.text_score, 100.0)
        self.assertEqual(result.combined_score, 0.975)

    def test_search_results_container(self):
        """Test SearchResults container."""
        results = [
            VectorSearchResult(
                memory_id="mem1",
                project_id="proj1",
                content="content1",
                summary="",
                tags=[],
                confidence=0.0,
                trust_score=0.0,
                status="",
                created_at="",
                score=0.9,
            ),
            VectorSearchResult(
                memory_id="mem2",
                project_id="proj1",
                content="content2",
                summary="",
                tags=[],
                confidence=0.0,
                trust_score=0.0,
                status="",
                created_at="",
                score=0.8,
            ),
        ]
        
        search_results = SearchResults(
            results=results,
            total=2,
            limit=10,
            offset=0,
            query_time_ms=100.0,
        )
        
        self.assertEqual(len(search_results.results), 2)
        self.assertEqual(search_results.total, 2)
        
        data = search_results.to_dict()
        self.assertIn("results", data)
        self.assertIn("total", data)


class TestGenerateQueryEmbedding(unittest.TestCase):
    """Test cases for query embedding generation."""

    def test_generate_query_embedding(self):
        """Test generating embedding for a query."""
        embedding = generate_query_embedding("test query")
        
        self.assertIsNotNone(embedding)
        self.assertEqual(len(embedding), 768)

    def test_empty_query(self):
        """Test that empty query returns None."""
        embedding = generate_query_embedding("")
        self.assertIsNone(embedding)
        
        embedding = generate_query_embedding(None)
        self.assertIsNone(embedding)


if __name__ == "__main__":
    unittest.main()
