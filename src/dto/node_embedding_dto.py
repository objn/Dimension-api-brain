"""
DTOs for Node Embedding and Search operations.
Request and response models with validation.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime

from .base_dto import BaseResponseModel


# ============================================================================
# Embedding DTOs
# ============================================================================

class EmbedNodeRequest(BaseModel):
    """Request to start embedding a node"""
    force_reembed: bool = Field(
        default=False,
        description="Force re-embedding even if content unchanged"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "force_reembed": False
            }
        }


class EmbedNodeResponse(BaseModel):
    """Response after starting embedding job"""
    job_id: UUID
    node_id: UUID
    status: str = "PENDING"
    message: str = "Embedding job started"
    
    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "123e4567-e89b-12d3-a456-426614174000",
                "node_id": "223e4567-e89b-12d3-a456-426614174001",
                "status": "PENDING",
                "message": "Embedding job started"
            }
        }


class EmbeddingStatusResponse(BaseModel):
    """Embedding job status response"""
    job_id: UUID
    node_id: UUID
    status: str
    stage: Optional[str] = None
    progress: int = 0
    message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "123e4567-e89b-12d3-a456-426614174000",
                "node_id": "223e4567-e89b-12d3-a456-426614174001",
                "status": "PROCESSING",
                "stage": "EMBEDDING",
                "progress": 65,
                "message": "Embedded 10/15 chunks"
            }
        }


# ============================================================================
# Chunk DTOs
# ============================================================================

class ChunkResponse(BaseModel):
    """Single chunk response"""
    chunk_id: UUID
    order: int
    content: str
    content_hash: str
    chunk_type: str  # "metadata" or "content"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    embedding: Optional[List[float]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "chunk_id": "123e4567-e89b-12d3-a456-426614174000",
                "order": 0,
                "content": "Title: My Node\nDescription: This is a sample node",
                "content_hash": "abc123def456",
                "chunk_type": "metadata",
                "created_at": "2026-02-05T12:00:00Z"
            }
        }


class NodeChunksResponse(BaseModel):
    """Response with all chunks for a node"""
    node_id: UUID
    node_name: Optional[str] = None
    total_chunks: int
    chunks: List[ChunkResponse]
    
    class Config:
        json_schema_extra = {
            "example": {
                "node_id": "123e4567-e89b-12d3-a456-426614174000",
                "node_name": "Python Basics",
                "total_chunks": 5,
                "chunks": []
            }
        }


# ============================================================================
# Search DTOs
# ============================================================================

class SearchRequest(BaseModel):
    """Search request body"""
    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum results")
    similarity_threshold: float = Field(
        default=0.7, 
        ge=0.0, 
        le=1.0,
        description="Minimum similarity score (0-1)"
    )
    include_content: bool = Field(
        default=True,
        description="Include chunk content in results"
    )
    include_metadata_chunks: bool = Field(
        default=True,
        description="Include metadata chunks (order=0)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "How to use Python variables",
                "limit": 10,
                "similarity_threshold": 0.7,
                "include_content": True,
                "include_metadata_chunks": True
            }
        }


class SearchResultItem(BaseModel):
    """Single search result"""
    node_id: UUID
    node_name: Optional[str] = None
    node_desc: Optional[str] = None
    chunk_id: UUID
    chunk_order: int
    chunk_type: str  # "metadata" or "content"
    similarity: float
    content: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "node_id": "123e4567-e89b-12d3-a456-426614174000",
                "node_name": "Python Basics",
                "chunk_id": "223e4567-e89b-12d3-a456-426614174001",
                "chunk_order": 1,
                "chunk_type": "content",
                "similarity": 0.89,
                "content": "Variables in Python are..."
            }
        }


class SearchResponse(BaseModel):
    """Search response"""
    query: str
    total_results: int
    results: List[SearchResultItem]
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "Python variables",
                "total_results": 5,
                "results": []
            }
        }


class SearchInNodeRequest(BaseModel):
    """Search within a specific node"""
    query: str = Field(..., min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=50)
    include_metadata: bool = Field(default=True)


class SearchInNodeResponse(BaseModel):
    """Search in node response"""
    node_id: UUID
    query: str
    total_results: int
    results: List[Dict[str, Any]]


# ============================================================================
# Related Nodes DTOs
# ============================================================================

class RelatedNodeItem(BaseModel):
    """Related node item"""
    node_id: UUID
    node_name: Optional[str] = None
    node_desc: Optional[str] = None
    similarity: float
    
    class Config:
        json_schema_extra = {
            "example": {
                "node_id": "123e4567-e89b-12d3-a456-426614174000",
                "node_name": "Python Data Types",
                "node_desc": "Overview of Python data types",
                "similarity": 0.85
            }
        }


class RelatedNodesResponse(BaseModel):
    """Related nodes response"""
    source_node_id: UUID
    total_results: int
    related_nodes: List[RelatedNodeItem]
    
    class Config:
        json_schema_extra = {
            "example": {
                "source_node_id": "123e4567-e89b-12d3-a456-426614174000",
                "total_results": 3,
                "related_nodes": []
            }
        }


# ============================================================================
# Hybrid Search DTOs
# ============================================================================

class HybridSearchRequest(BaseModel):
    """Hybrid search request (keyword + semantic)"""
    query: str = Field(..., min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=100)
    keyword_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    semantic_weight: float = Field(default=0.7, ge=0.0, le=1.0)
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "Python function definition",
                "limit": 10,
                "keyword_weight": 0.3,
                "semantic_weight": 0.7
            }
        }
