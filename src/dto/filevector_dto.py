"""
DTOs for FileVector operations.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class FilevectorResponse(BaseModel):
    conversation_id: UUID
    file_id: UUID
    chunk_id: UUID = Field(alias="file_vector_chunk_id")
    chunk_order: Optional[int] = Field(default=None, alias="file_vector_chunk_order")
    file_content_text_chunk: Optional[str] = None
    created_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[UUID] = None

    class Config:
        from_attributes = True
        populate_by_name = True
