"""
DTOs for Node operations.
Request and response models with validation.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID

from .base_dto import BaseResponseModel


class NodeCreateRequest(BaseModel):
    """Request body for creating a node"""
    node_name: str = Field(..., min_length=1, max_length=255, description="Node name")
    node_desc: Optional[str] = Field(None, description="Node description")
    node_content_md: Optional[str] = Field(None, description="Node content in Markdown format")
    node_location_x: Optional[float] = Field(None, description="X coordinate in 3D space")
    node_location_y: Optional[float] = Field(None, description="Y coordinate in 3D space")
    node_location_z: Optional[float] = Field(None, description="Z coordinate in 3D space")

    class Config:
        json_schema_extra = {
            "example": {
                "node_name": "Project Overview",
                "node_desc": "High-level overview of the project architecture",
                "node_content_md": "# Project Overview\n\nThis node contains...",
                "node_location_x": 0.0,
                "node_location_y": 0.0,
                "node_location_z": 0.0
            }
        }


class NodeUpdateRequest(BaseModel):
    """Request body for updating a node"""
    node_name: Optional[str] = Field(None, min_length=1, max_length=255, description="Node name")
    node_desc: Optional[str] = Field(None, description="Node description")
    node_content_md: Optional[str] = Field(None, description="Node content in Markdown format")
    node_location_x: Optional[float] = Field(None, description="X coordinate in 3D space")
    node_location_y: Optional[float] = Field(None, description="Y coordinate in 3D space")
    node_location_z: Optional[float] = Field(None, description="Z coordinate in 3D space")

    class Config:
        json_schema_extra = {
            "example": {
                "node_name": "Updated Project Overview",
                "node_desc": "Updated description",
                "node_content_md": "# Updated Overview\n\nThis node contains...",
                "node_location_x": 10.5,
                "node_location_y": 20.3,
                "node_location_z": 5.0
            }
        }


class NodeResponse(BaseResponseModel):
    """Response model for node data"""
    node_id: UUID
    node_name: Optional[str] = None
    node_desc: Optional[str] = None
    node_content_md: Optional[str] = None
    node_location_x: Optional[float] = None
    node_location_y: Optional[float] = None
    node_location_z: Optional[float] = None
    created_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[UUID] = None

    class Config:
        json_schema_extra = {
            "example": {
                "node_id": "123e4567-e89b-12d3-a456-426614174000",
                "node_name": "Project Overview",
                "node_desc": "High-level overview of the project architecture",
                "node_content_md": "# Project Overview\n\nThis node contains...",
                "node_location_x": 0.0,
                "node_location_y": 0.0,
                "node_location_z": 0.0,
                "created_at": "2026-02-05T12:00:00.000Z",
                "created_by": "123e4567-e89b-12d3-a456-426614174001",
                "updated_at": "2026-02-05T12:00:00.000Z",
                "updated_by": "123e4567-e89b-12d3-a456-426614174001"
            }
        }


class NodeListResponse(BaseResponseModel):
    """Response model for list of nodes"""
    nodes: List[NodeResponse]
    total: int

    class Config:
        json_schema_extra = {
            "example": {
                "nodes": [
                    {
                        "node_id": "123e4567-e89b-12d3-a456-426614174000",
                        "node_name": "Project Overview",
                        "node_desc": "High-level overview of the project architecture",
                        "node_content_md": "# Project Overview\n\nThis node contains...",
                        "node_location_x": 0.0,
                        "node_location_y": 0.0,
                        "node_location_z": 0.0,
                        "created_at": "2026-02-05T12:00:00.000Z",
                        "created_by": "123e4567-e89b-12d3-a456-426614174001",
                        "updated_at": "2026-02-05T12:00:00.000Z",
                        "updated_by": "123e4567-e89b-12d3-a456-426614174001"
                    }
                ],
                "total": 1
            }
        }
