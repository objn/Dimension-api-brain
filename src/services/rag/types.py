"""
RAG Types and Constants.
Defines enums, dataclasses, and constants for RAG operations.
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional
from uuid import UUID


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
