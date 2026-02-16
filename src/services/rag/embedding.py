"""
OpenAI Embedding Service.
Uses text-embedding-3-small model for creating vector embeddings.
"""
import httpx
from typing import List, Optional
import logging

from openai import OpenAI

from src.config.settings import settings
from src.dto.rag_dto import EMBEDDING_MODEL, EMBEDDING_DIMENSIONS, EMBEDDING_BATCH_SIZE

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Service for creating embeddings using OpenAI API.
    
    Uses text-embedding-3-small model which produces 1536-dimensional vectors.
    """
    
    def __init__(self):
        """Initialize embedding service with OpenAI client."""
        self.client = self._create_client()
        self.model = EMBEDDING_MODEL
        self.dimensions = EMBEDDING_DIMENSIONS
        self.batch_size = EMBEDDING_BATCH_SIZE
    
    def _create_client(self) -> OpenAI:
        """Create OpenAI client with configured settings."""
        http_client = httpx.Client(
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=120.0  # Longer timeout for batch operations
        )
        return OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            http_client=http_client
        )
    
    def embed_single(self, text: str) -> List[float]:
        """
        Create embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector (1536 dimensions)
        """
        if not text or not text.strip():
            raise ValueError("Cannot embed empty text")
        
        # Truncate if too long (model limit is ~8191 tokens)
        text = text[:32000]  # Rough character limit
        
        response = self.client.embeddings.create(
            model=self.model,
            input=text,
            dimensions=self.dimensions
        )
        
        return response.data[0].embedding
    
    def embed_batch(
        self, 
        texts: List[str],
        on_progress: Optional[callable] = None
    ) -> List[List[float]]:
        """
        Create embeddings for multiple texts efficiently.
        
        Args:
            texts: List of texts to embed
            on_progress: Optional callback(processed, total) for progress updates
            
        Returns:
            List of embedding vectors in same order as input
        """
        if not texts:
            return []
        
        all_embeddings = []
        total = len(texts)
        
        # Process in batches
        for i in range(0, total, self.batch_size):
            batch = texts[i:i + self.batch_size]
            
            # Clean and truncate texts
            cleaned_batch = []
            for text in batch:
                if text and text.strip():
                    cleaned_batch.append(text[:32000])
                else:
                    cleaned_batch.append(" ")  # Placeholder for empty texts
            
            try:
                response = self.client.embeddings.create(
                    model=self.model,
                    input=cleaned_batch,
                    dimensions=self.dimensions
                )
                
                # Sort by index to maintain order
                sorted_data = sorted(response.data, key=lambda x: x.index)
                batch_embeddings = [item.embedding for item in sorted_data]
                all_embeddings.extend(batch_embeddings)
                
            except Exception as e:
                logger.error(f"Embedding batch failed at index {i}: {e}")
                raise
            
            # Progress callback
            if on_progress:
                processed = min(i + len(batch), total)
                on_progress(processed, total)
        
        return all_embeddings
    
    def embed_with_retry(
        self, 
        text: str, 
        max_retries: int = 3
    ) -> Optional[List[float]]:
        """
        Embed single text with retry logic.
        
        Args:
            text: Text to embed
            max_retries: Maximum retry attempts
            
        Returns:
            Embedding vector or None if all retries fail
        """
        import time
        
        for attempt in range(max_retries):
            try:
                return self.embed_single(text)
            except Exception as e:
                logger.warning(f"Embedding attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error(f"All {max_retries} embedding attempts failed")
                    return None
        
        return None


# Singleton instance
embedding_service = EmbeddingService()
