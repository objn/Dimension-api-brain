"""
RAG Services Package.
Provides node embedding and semantic search capabilities.
"""
from .types import (
    RAGStage,
    ChunkType,
    ChunkData,
    ChunkDiff,
    ExistingChunk,
    EmbeddingResult,
    NodeEmbeddingResult,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    EMBEDDING_MODEL,
    EMBEDDING_DIMENSIONS,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_SEARCH_LIMIT
)
from .chunking import ChunkingService, chunking_service
from .embedding import EmbeddingService, embedding_service
from .node_embedding_service import NodeEmbeddingService, node_embedding_service
from .search_service import SearchService, search_service

__all__ = [
    # Types & Constants
    "RAGStage",
    "ChunkType",
    "ChunkData",
    "ChunkDiff",
    "ExistingChunk",
    "EmbeddingResult",
    "NodeEmbeddingResult",
    "CHUNK_SIZE",
    "CHUNK_OVERLAP",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS",
    "DEFAULT_SIMILARITY_THRESHOLD",
    "DEFAULT_SEARCH_LIMIT",
    
    # Services
    "ChunkingService",
    "chunking_service",
    "EmbeddingService",
    "embedding_service",
    "NodeEmbeddingService",
    "node_embedding_service",
    "SearchService",
    "search_service",
]
