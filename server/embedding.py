"""Embedding Generation Interface for Memory Core.

Provides the embedding generation interface for vector search.
Supports sentence-transformers compatible 768-dim float32 vectors.

Architecture:
- Abstract base class for embedding generators
- Local embedding sidecar (stub implementation)
- Integration with memory operations
- Batch embedding support
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)


# Default embedding configuration
DEFAULT_EMBEDDING_DIM = 768
DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"  # 384-dim, but we'll use 768 for compatibility


@dataclass
class EmbeddingConfig:
    """Configuration for embedding generation."""
    model_name: str = DEFAULT_MODEL_NAME
    dimension: int = DEFAULT_EMBEDDING_DIM
    batch_size: int = 32
    device: str = "cpu"  # cpu, cuda, mps
    normalize: bool = True  # Normalize embeddings to unit length
    trust_remote_code: bool = False
    
    # For remote embedding services
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    api_timeout: float = 30.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "dimension": self.dimension,
            "batch_size": self.batch_size,
            "device": self.device,
            "normalize": self.normalize,
            "trust_remote_code": self.trust_remote_code,
            "api_url": self.api_url,
            "api_timeout": self.api_timeout,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmbeddingConfig":
        return cls(
            model_name=data.get("model_name", DEFAULT_MODEL_NAME),
            dimension=data.get("dimension", DEFAULT_EMBEDDING_DIM),
            batch_size=data.get("batch_size", 32),
            device=data.get("device", "cpu"),
            normalize=data.get("normalize", True),
            trust_remote_code=data.get("trust_remote_code", False),
            api_url=data.get("api_url"),
            api_key=data.get("api_key"),
            api_timeout=data.get("api_timeout", 30.0),
        )


@dataclass
class EmbeddingResult:
    """Result of embedding generation."""
    text: str
    embedding: List[float]
    model_name: str
    dimension: int
    generated_at: str
    processing_time_ms: float = 0.0
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "embedding": self.embedding,
            "model_name": self.model_name,
            "dimension": self.dimension,
            "generated_at": self.generated_at,
            "processing_time_ms": self.processing_time_ms,
            "error": self.error,
        }
    
    def to_cozo_format(self) -> List[float]:
        """Convert to CozoDB-compatible format (list of f32)."""
        return [float(x) for x in self.embedding]
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmbeddingResult":
        return cls(
            text=data.get("text", ""),
            embedding=data.get("embedding", []),
            model_name=data.get("model_name", ""),
            dimension=data.get("dimension", 0),
            generated_at=data.get("generated_at", ""),
            processing_time_ms=data.get("processing_time_ms", 0.0),
            error=data.get("error"),
        )


class EmbeddingError(Exception):
    """Base exception for embedding errors."""
    pass


class EmbeddingGenerationError(EmbeddingError):
    """Exception for embedding generation failures."""
    pass


class EmbeddingModelError(EmbeddingError):
    """Exception for model-related errors."""
    pass


class EmbeddingGenerator(ABC):
    """Abstract base class for embedding generators.
    
    All embedding generators must implement the generate and generate_batch methods.
    """
    
    def __init__(self, config: Optional[EmbeddingConfig] = None):
        """Initialize the embedding generator.
        
        Args:
            config: Embedding configuration
        """
        self.config = config or EmbeddingConfig()
        self._initialized = False
    
    @abstractmethod
    def initialize(self) -> None:
        """Initialize the embedding generator (load model, connect to API, etc.)."""
        pass
    
    @abstractmethod
    def generate(self, text: str) -> EmbeddingResult:
        """Generate embedding for a single text.
        
        Args:
            text: Input text to embed
            
        Returns:
            EmbeddingResult with the generated embedding
            
        Raises:
            EmbeddingGenerationError: If embedding generation fails
        """
        pass
    
    @abstractmethod
    def generate_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        """Generate embeddings for a batch of texts.
        
        Args:
            texts: List of input texts to embed
            
        Returns:
            List of EmbeddingResults (one per input text)
            
        Raises:
            EmbeddingGenerationError: If embedding generation fails
        """
        pass
    
    def __enter__(self):
        if not self._initialized:
            self.initialize()
            self._initialized = True
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def close(self) -> None:
        """Close the embedding generator and release resources."""
        self._initialized = False
    
    def is_initialized(self) -> bool:
        """Check if the generator is initialized."""
        return self._initialized
    
    def get_config(self) -> EmbeddingConfig:
        """Get the current configuration."""
        return self.config


class LocalEmbeddingSidecar(EmbeddingGenerator):
    """Local embedding sidecar for generating vector embeddings.
    
    This is a stub implementation that will be replaced with actual
    embedding model integration (sentence-transformers, etc.).
    
    For now, it generates random vectors of the correct dimension
    to allow the system to work end-to-end.
    
    Future implementation will use:
    - sentence-transformers (HuggingFace)
    - or other local embedding models
    """
    
    def __init__(self, config: Optional[EmbeddingConfig] = None):
        """Initialize the local embedding sidecar.
        
        Args:
            config: Embedding configuration
        """
        super().__init__(config)
        self._model = None
        self._tokenizer = None
    
    def initialize(self) -> None:
        """Initialize the embedding sidecar.
        
        For the stub implementation, this just logs a message.
        In the real implementation, this would load the model.
        """
        logger.info(f"Initializing LocalEmbeddingSidecar with model: {self.config.model_name}")
        logger.info(f"Embedding dimension: {self.config.dimension}")
        logger.info(f"Device: {self.config.device}")
        
        # In real implementation:
        # try:
        #     from sentence_transformers import SentenceTransformer
        #     self._model = SentenceTransformer(self.config.model_name, device=self.config.device)
        # except ImportError:
        #     raise EmbeddingModelError("sentence-transformers is required. Install with: pip install sentence-transformers")
        
        self._initialized = True
        logger.info("LocalEmbeddingSidecar initialized (stub mode)")
    
    def generate(self, text: str) -> EmbeddingResult:
        """Generate embedding for a single text.
        
        Stub implementation: generates a random vector.
        Real implementation: uses sentence-transformers.
        
        Args:
            text: Input text to embed
            
        Returns:
            EmbeddingResult with the generated embedding
        """
        import time
        import uuid
        from datetime import datetime
        
        start_time = time.time()
        
        # Generate a deterministic "hash" based on text for consistent stub embeddings
        # This allows tests to be reproducible
        import hashlib
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        seed = int(text_hash[:8], 16)
        
        # Create a reproducible random vector
        np.random.seed(seed)
        embedding = np.random.randn(self.config.dimension).tolist()
        
        # Normalize to unit length (for cosine similarity)
        if self.config.normalize:
            norm = (sum(x**2 for x in embedding) ** 0.5)
            if norm > 0:
                embedding = [x / norm for x in embedding]
        
        processing_time = (time.time() - start_time) * 1000
        
        return EmbeddingResult(
            text=text,
            embedding=embedding,
            model_name=self.config.model_name,
            dimension=self.config.dimension,
            generated_at=datetime.utcnow().isoformat(),
            processing_time_ms=processing_time,
        )
    
    def generate_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        """Generate embeddings for a batch of texts.
        
        Stub implementation: generates random vectors for each text.
        Real implementation: uses sentence-transformers batch processing.
        
        Args:
            texts: List of input texts to embed
            
        Returns:
            List of EmbeddingResults
        """
        import time
        from datetime import datetime
        
        start_time = time.time()
        results = []
        
        for text in texts:
            result = self.generate(text)
            results.append(result)
        
        logger.info(f"Generated batch of {len(texts)} embeddings in {(time.time() - start_time) * 1000:.2f}ms")
        return results
    
    def close(self) -> None:
        """Close the embedding sidecar."""
        # In real implementation:
        # if self._model:
        #     del self._model
        #     self._model = None
        logger.info("LocalEmbeddingSidecar closed")
        self._initialized = False


class RemoteEmbeddingService(EmbeddingGenerator):
    """Remote embedding service client.
    
    Connects to a remote embedding API (e.g., OpenAI, Cohere, etc.).
    This is a stub implementation for future use.
    """
    
    def __init__(self, config: Optional[EmbeddingConfig] = None):
        """Initialize the remote embedding service.
        
        Args:
            config: Embedding configuration with API settings
        """
        super().__init__(config)
        self._session = None
    
    def initialize(self) -> None:
        """Initialize the remote embedding service."""
        if not self.config.api_url:
            raise EmbeddingModelError("API URL is required for remote embedding service")
        
        logger.info(f"Initializing RemoteEmbeddingService: {self.config.api_url}")
        
        # In real implementation:
        # import httpx
        # self._session = httpx.AsyncClient(timeout=self.config.api_timeout)
        
        self._initialized = True
    
    def generate(self, text: str) -> EmbeddingResult:
        """Generate embedding via remote API.
        
        Stub implementation: returns a random vector.
        Real implementation: calls the API.
        """
        import time
        from datetime import datetime
        
        start_time = time.time()
        
        # Stub: generate random vector
        import hashlib
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        seed = int(text_hash[:8], 16)
        
        import numpy as np
        np.random.seed(seed)
        embedding = np.random.randn(self.config.dimension).tolist()
        
        if self.config.normalize:
            norm = (sum(x**2 for x in embedding) ** 0.5)
            if norm > 0:
                embedding = [x / norm for x in embedding]
        
        processing_time = (time.time() - start_time) * 1000
        
        return EmbeddingResult(
            text=text,
            embedding=embedding,
            model_name=self.config.model_name,
            dimension=self.config.dimension,
            generated_at=datetime.utcnow().isoformat(),
            processing_time_ms=processing_time,
        )
    
    def generate_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        """Generate embeddings for a batch of texts via remote API."""
        return [self.generate(text) for text in texts]
    
    def close(self) -> None:
        """Close the remote embedding service."""
        # In real implementation:
        # if self._session:
        #     self._session.close()
        #     self._session = None
        self._initialized = False


class NullEmbeddingGenerator(EmbeddingGenerator):
    """Null embedding generator that returns zero vectors.
    
    Useful for testing or when embeddings are not needed.
    """
    
    def initialize(self) -> None:
        self._initialized = True
    
    def generate(self, text: str) -> EmbeddingResult:
        from datetime import datetime
        
        return EmbeddingResult(
            text=text,
            embedding=[0.0] * self.config.dimension,
            model_name="null",
            dimension=self.config.dimension,
            generated_at=datetime.utcnow().isoformat(),
            processing_time_ms=0.0,
        )
    
    def generate_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        return [self.generate(text) for text in texts]


class EmbeddingManager:
    """Manager for embedding generation.
    
    Provides a unified interface for generating embeddings using
    the configured embedding generator.
    """
    
    def __init__(self, generator: Optional[EmbeddingGenerator] = None):
        """Initialize the embedding manager.
        
        Args:
            generator: Embedding generator to use (defaults to LocalEmbeddingSidecar)
        """
        self.generator = generator or LocalEmbeddingSidecar()
        self._initialized = False
    
    def initialize(self) -> None:
        """Initialize the embedding manager."""
        if not self._initialized:
            self.generator.initialize()
            self._initialized = True
    
    def generate(self, text: str) -> EmbeddingResult:
        """Generate embedding for a single text.
        
        Args:
            text: Input text to embed
            
        Returns:
            EmbeddingResult with the generated embedding
        """
        if not self._initialized:
            self.initialize()
        return self.generator.generate(text)
    
    def generate_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        """Generate embeddings for a batch of texts.
        
        Args:
            texts: List of input texts to embed
            
        Returns:
            List of EmbeddingResults
        """
        if not self._initialized:
            self.initialize()
        return self.generator.generate_batch(texts)
    
    def generate_for_memory(
        self,
        content: str,
        summary: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> EmbeddingResult:
        """Generate embedding for a memory record.
        
        Combines content, summary, and tags into a single text for embedding.
        
        Args:
            content: Memory content
            summary: Optional summary
            tags: Optional list of tags
            
        Returns:
            EmbeddingResult with the generated embedding
        """
        # Combine all text fields
        text_parts = [content]
        if summary:
            text_parts.append(summary)
        if tags:
            text_parts.append(" ".join(tags))
        
        combined_text = " \n ".join(text_parts)
        return self.generate(combined_text)
    
    def close(self) -> None:
        """Close the embedding manager."""
        self.generator.close()
        self._initialized = False
    
    def __enter__(self):
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Utility functions for embedding operations

def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Calculate cosine similarity between two vectors.
    
    Args:
        a: First vector
        b: Second vector
        
    Returns:
        Cosine similarity (0.0 to 1.0, higher is more similar)
    """
    if len(a) != len(b):
        raise ValueError(f"Vectors must have same dimension: {len(a)} vs {len(b)}")
    
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = (sum(x**2 for x in a) ** 0.5)
    norm_b = (sum(x**2 for x in b) ** 0.5)
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    return dot_product / (norm_a * norm_b)


def euclidean_distance(a: List[float], b: List[float]) -> float:
    """Calculate Euclidean distance between two vectors.
    
    Args:
        a: First vector
        b: Second vector
        
    Returns:
        Euclidean distance
    """
    if len(a) != len(b):
        raise ValueError(f"Vectors must have same dimension: {len(a)} vs {len(b)}")
    
    return (sum((x - y)**2 for x, y in zip(a, b)) ** 0.5)


def normalize_vector(v: List[float]) -> List[float]:
    """Normalize a vector to unit length.
    
    Args:
        v: Input vector
        
    Returns:
        Normalized vector
    """
    norm = (sum(x**2 for x in v) ** 0.5)
    if norm == 0:
        return v
    return [x / norm for x in v]


def vector_dimension(v: List[float]) -> int:
    """Get the dimension of a vector.
    
    Args:
        v: Input vector
        
    Returns:
        Dimension (length) of the vector
    """
    return len(v)


def validate_embedding(embedding: List[float], expected_dim: int = 768) -> bool:
    """Validate that an embedding has the expected dimension.
    
    Args:
        embedding: The embedding to validate
        expected_dim: Expected dimension (default 768)
        
    Returns:
        True if valid, False otherwise
    """
    return len(embedding) == expected_dim
