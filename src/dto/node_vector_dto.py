"""
DTOs for NodeVector operations.
Request and response models with validation.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID

from .base_dto import BaseResponseModel


class NodeVectorCreateRequest(BaseModel):
    """Request body for creating a node vector"""
    node_id: UUID = Field(..., description="ID of the associated node")
    node_vector_chuck_id: UUID = Field(..., description="Unique ID for the vector chunk")
    node_vector_chuck_order: Optional[int] = Field(None, description="Order of the vector chunk")
    node_content_md_chuck: Optional[str] = Field(None, description="Markdown content chunk")
    node_content_md_chuck_hash: Optional[str] = Field(None, max_length=255, description="Hash of the content chunk")
    embedding: Optional[List[float]] = Field(None, description="Embedding vector (1536 dimensions)")

    class Config:
        json_schema_extra = {
            "example": {
                "node_id": "123e4567-e89b-12d3-a456-426614174000",
                "node_vector_chuck_id": "123e4567-e89b-12d3-a456-426614174001",
                "node_vector_chuck_order": 0,
                "node_content_md_chuck": "This is the first chunk of content...",
                "node_content_md_chuck_hash": "5d41402abc4b2a76b9719d911017c592",
                "embedding": [0.1, 0.2, 0.3]
            }
        }


class NodeVectorUpdateRequest(BaseModel):
    """Request body for updating a node vector"""
    node_vector_chuck_order: Optional[int] = Field(None, description="Order of the vector chunk")
    node_content_md_chuck: Optional[str] = Field(None, description="Markdown content chunk")
    node_content_md_chuck_hash: Optional[str] = Field(None, max_length=255, description="Hash of the content chunk")
    embedding: Optional[List[float]] = Field(None, description="Embedding vector (1536 dimensions)")

    class Config:
        json_schema_extra = {
            "example": {
                "node_vector_chuck_order": 1,
                "node_content_md_chuck": "Updated content chunk...",
                "node_content_md_chuck_hash": "5d41402abc4b2a76b9719d911017c592",
                "embedding": [0.1, 0.2, 0.3]
            }
        }


class NodeVectorResponse(BaseResponseModel):
    """Response model for node vector data"""
    node_id: UUID
    node_vector_chuck_id: UUID
    node_vector_chuck_order: Optional[int] = None
    node_content_md_chuck: Optional[str] = None
    node_content_md_chuck_hash: Optional[str] = None
    embedding: Optional[List[float]] = None
    created_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[UUID] = None
    deleted_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "node_id": "123e4567-e89b-12d3-a456-426614174000",
                "node_vector_chuck_id": "123e4567-e89b-12d3-a456-426614174001",
                "node_vector_chuck_order": 0,
                "node_content_md_chuck": "This is the first chunk of content...",
                "node_content_md_chuck_hash": "5d41402abc4b2a76b9719d911017c592",
                "embedding": [0.1, 0.2, 0.3],
                "created_at": "2026-02-05T12:00:00.000Z",
                "created_by": "123e4567-e89b-12d3-a456-426614174001",
                "updated_at": "2026-02-05T12:00:00.000Z",
                "updated_by": "123e4567-e89b-12d3-a456-426614174001",
                "deleted_at": "null"
            }
        }

class NodeVectorListResponse(BaseResponseModel):
    """Response model for list of node vectors"""
    node_vectors: List[NodeVectorResponse]
    total: int

    class Config:
        json_schema_extra = {
            "example": {
                "node_vectors": [
                    {
                        "node_id": "123e4567-e89b-12d3-a456-426614174000",
                        "node_vector_chuck_id": "123e4567-e89b-12d3-a456-426614174001",
                        "node_vector_chuck_order": 0,
                        "node_content_md_chuck": "First chunk...",
                        "node_content_md_chuck_hash": "5d41402abc4b2a76b9719d911017c592",
                        "embedding": [0.1, 0.2, 0.3],
                        "created_at": "2026-02-05T12:00:00.000Z",
                        "created_by": "123e4567-e89b-12d3-a456-426614174001",
                        "updated_at": "2026-02-05T12:00:00.000Z",
                        "updated_by": "123e4567-e89b-12d3-a456-426614174001",
                        "deleted_at": "null"
                    }
                ],
                "total": 1
            }
        }
