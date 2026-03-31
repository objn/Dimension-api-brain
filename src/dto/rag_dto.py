"""
RAG Types and Constants.
Defines enums, dataclasses, and constants for RAG operations.
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RAGStage(str, Enum):
    """RAG Pipeline stages for job tracking"""
    INIT = "INIT"
    CHUNKING = "CHUNKING"
    COMPARING = "COMPARING"
    EMBEDDING = "EMBEDDING"
    STORING = "STORING"
    COMPLETED = "COMPLETED"


class ChunkType(str, Enum):
    """Type of chunk"""
    METADATA = "metadata"      # node_name + node_desc (order=0)
    CONTENT = "content"        # node_content_md chunks (order=1,2,3...)


@dataclass
class ChunkData:
    """
    Represents a single chunk of content.
    
    Attributes:
        order: Position in the sequence (0 = metadata, 1+ = content)
        content: The actual text content
        content_hash: MD5 hash for comparison
        chunk_type: METADATA or CONTENT
        section_header: Markdown header if applicable
        start_char: Start position in original content
        end_char: End position in original content
    """
    order: int
    content: str
    content_hash: str
    chunk_type: ChunkType
    section_header: Optional[str] = None
    start_char: Optional[int] = None
    end_char: Optional[int] = None


@dataclass
class ExistingChunk:
    """Represents an existing chunk from database"""
    chunk_id: UUID
    order: int
    content_hash: str
    content: Optional[str] = None


@dataclass
class ChunkDiff:
    """
    Represents difference between old and new chunks.
    Used to determine what to delete, create, or keep.
    """
    to_delete: List[UUID] = field(default_factory=list)      # chunk_ids to soft delete
    to_create: List[ChunkData] = field(default_factory=list)  # new chunks to create
    unchanged: List[UUID] = field(default_factory=list)       # chunk_ids unchanged


@dataclass
class EmbeddingResult:
    """Result of embedding a single chunk"""
    chunk_data: ChunkData
    embedding: List[float]


@dataclass
class NodeEmbeddingResult:
    """Final result of node embedding operation"""
    node_id: UUID
    chunks_created: int
    chunks_deleted: int
    chunks_unchanged: int
    total_chunks: int
    processing_time_seconds: float


@dataclass
class RAGSearchResult:
    """Single chunk result from semantic search (for RAG and citations)."""
    node_id: UUID
    chunk_id: UUID
    node_content_md_chunk: str
    similarity: float  # 1 - cosine_distance (higher = more similar)
    node_vector_chunk_order: Optional[int] = None


# ============================================================================
# Constants
# ============================================================================

# Chunking configuration
CHUNK_SIZE = 1000           # Target characters per chunk
CHUNK_OVERLAP = 200         # Overlap between chunks for context continuity
MIN_CHUNK_SIZE = 100        # Minimum chunk size (don't create tiny chunks)

# Embedding configuration
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
EMBEDDING_BATCH_SIZE = 50   # Number of texts per API call

# Search configuration
DEFAULT_SIMILARITY_THRESHOLD = 0.7
DEFAULT_SEARCH_LIMIT = 10

# Cross-lingual search (query translation so content in another language can be found)
RAG_CROSS_LINGUAL_ENABLED = True   # Set False to disable query translation
RAG_QUERY_TRANSLATE_LLM_PROVIDER = "openai"  # LLM used to translate query (en/th)
RAG_QUERY_TRANSLATE_MAX_CHARS = 2000  # Max query length sent for translation


# ============================================================================
# Pydantic models for RAG Search API
# ============================================================================

class RAGSearchRequest(BaseModel):
    """Request body for semantic search over node chunks."""
    query: str = Field(..., min_length=1, description="Natural language search query")
    limit: int = Field(default=DEFAULT_SEARCH_LIMIT, ge=1, le=50, description="Max chunks to return")
    min_similarity: Optional[float] = Field(default=DEFAULT_SIMILARITY_THRESHOLD, ge=0, le=1)
    scope_node_ids: Optional[List[UUID]] = Field(default=None, description="Restrict search to these node IDs")


class RAGSearchResultItem(BaseModel):
    """Single search result for API response."""
    node_id: UUID
    chunk_id: UUID
    node_content_md_chunk: str
    similarity: float
    node_vector_chunk_order: Optional[int] = None


class RAGSearchResponse(BaseModel):
    """Response for semantic search."""
    count: int
    results: List[RAGSearchResultItem]


class EmbeddingProcessRequest(BaseModel):
    """Request to register a node_content_embedding job (same metadata shape as POST /jobs)."""

    node_id: UUID = Field(..., description="Node ID to chunk and embed (must exist in brain DB)")
    force_reembed: bool = Field(
        default=False,
        description="If True, re-embed all chunks even when content hash unchanged",
    )
    job_start_time: Optional[datetime] = Field(
        default=None,
        description="When the job daemon may pick up this job. Omit for immediate (utcnow).",
    )
