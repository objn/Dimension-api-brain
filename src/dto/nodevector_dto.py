"""
DTOs for NodeVector operations.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class NodevectorResponse(BaseModel):
    node_id: UUID
    node_name: Optional[str] = None
    chunk_id: UUID = Field(alias="node_vector_chunk_id")
    chunk_order: Optional[int] = Field(default=None, alias="node_vector_chunk_order")
    node_content_md_chunk: Optional[str] = None
    created_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[UUID] = None

    class Config:
        from_attributes = True
        populate_by_name = True

