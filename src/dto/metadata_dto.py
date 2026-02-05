"""
DTOs for Metadata operations.
Request and response models with validation.
"""
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
from uuid import UUID

from .base_dto import BaseResponseModel


class MetadataCreateRequest(BaseModel):
    """Request body for creating a metadata"""
    metadata_of: UUID = Field(..., description="UUID of the entity this metadata belongs to")
    metadata_json: Optional[dict] = Field(None, description="JSON metadata object")
    content_to_summarize: Optional[str] = Field(None, description="Content to be summarized")

    class Config:
        json_schema_extra = {
            "example": {
                "metadata_of": "123e4567-e89b-12d3-a456-426614174000",
                "metadata_json": {"key": "value", "tags": ["tag1", "tag2"]},
                "content_to_summarize": "This is the content that needs to be summarized..."
            }
        }


class MetadataUpdateRequest(BaseModel):
    """Request body for updating a metadata"""
    metadata_of: Optional[UUID] = Field(None, description="UUID of the entity this metadata belongs to")
    metadata_json: Optional[dict] = Field(None, description="JSON metadata object")
    content_to_summarize: Optional[str] = Field(None, description="Content to be summarized")

    class Config:
        json_schema_extra = {
            "example": {
                "metadata_json": {"key": "updated_value", "tags": ["tag1", "tag3"]},
                "content_to_summarize": "Updated content to summarize..."
            }
        }


class MetadataResponse(BaseResponseModel):
    """Response model for metadata data"""
    metadata_id: UUID
    metadata_of: Optional[UUID]
    metadata_json: Optional[dict]
    content_to_summarize: Optional[str]
    created_at: Optional[datetime]
    created_by: Optional[UUID]
    updated_at: Optional[datetime]
    updated_by: Optional[UUID]

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "metadata_id": "123e4567-e89b-12d3-a456-426614174000",
                "metadata_of": "123e4567-e89b-12d3-a456-426614174001",
                "metadata_json": {"key": "value"},
                "content_to_summarize": "Content text...",
                "created_at": "2026-01-31T12:00:00Z",
                "created_by": "123e4567-e89b-12d3-a456-426614174002",
                "updated_at": "2026-01-31T12:00:00Z",
                "updated_by": "123e4567-e89b-12d3-a456-426614174002"
            }
        }


class MetadataListResponse(BaseModel):
    """Response model for list of metadatas"""
    count: int
    metadatas: list[MetadataResponse]

    class Config:
        json_schema_extra = {
            "example": {
                "count": 2,
                "metadatas": [
                    {
                        "metadata_id": "123e4567-e89b-12d3-a456-426614174000",
                        "metadata_of": "123e4567-e89b-12d3-a456-426614174001",
                        "metadata_json": {"key": "value"},
                        "created_at": "2026-01-31T12:00:00Z"
                    }
                ]
            }
        }
