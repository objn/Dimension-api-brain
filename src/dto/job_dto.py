"""
DTOs for Job operations.
Request and response models with validation.
"""
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
from uuid import UUID

from .base_dto import BaseResponseModel
from .metadata_dto import MetadataResponse


class JobCreateRequest(BaseModel):
    """Request body for creating a job with metadata"""
    job_result: Optional[str] = Field("PENDING", max_length=16, description="Job result status")
    metadata_json: Optional[dict] = Field(None, description="JSON metadata for the job")
    content_to_summarize: Optional[str] = Field(None, description="Content to be summarized")

    class Config:
        json_schema_extra = {
            "example": {
                "job_result": "PENDING",
                "metadata_json": {"task_type": "data_processing", "priority": "high"},
                "content_to_summarize": "Job details to summarize..."
            }
        }


class JobUpdateStatusRequest(BaseModel):
    """Request body for updating job status and metadata"""
    job_result: str = Field(..., max_length=16, description="Job result status")
    metadata_json: Optional[dict] = Field(None, description="Updated JSON metadata")
    content_to_summarize: Optional[str] = Field(None, description="Updated content to summarize")

    class Config:
        json_schema_extra = {
            "example": {
                "job_result": "COMPLETED",
                "metadata_json": {"task_type": "data_processing", "result": "success"},
                "content_to_summarize": "Updated job summary..."
            }
        }


class JobInterruptRequest(BaseModel):
    """Request body for interrupting a job"""
    reason: Optional[str] = Field(None, description="Reason for interruption")

    class Config:
        json_schema_extra = {
            "example": {
                "reason": "User requested cancellation"
            }
        }


class JobResponse(BaseResponseModel):
    """Response model for job data"""
    job_id: UUID
    job_result: Optional[str]
    created_at: Optional[datetime]
    created_by: Optional[UUID]
    updated_at: Optional[datetime]
    updated_by: Optional[UUID]

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "job_id": "123e4567-e89b-12d3-a456-426614174000",
                "job_result": "PENDING",
                "created_at": "2026-01-31T12:00:00Z",
                "created_by": "123e4567-e89b-12d3-a456-426614174001",
                "updated_at": "2026-01-31T12:00:00Z",
                "updated_by": "123e4567-e89b-12d3-a456-426614174001"
            }
        }


class JobWithMetadataResponse(BaseResponseModel):
    """Response model for job data with metadata"""
    job_id: UUID
    job_result: Optional[str]
    created_at: Optional[datetime]
    created_by: Optional[UUID]
    updated_at: Optional[datetime]
    updated_by: Optional[UUID]
    metadata: Optional[MetadataResponse] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "job_id": "123e4567-e89b-12d3-a456-426614174000",
                "job_result": "COMPLETED",
                "created_at": "2026-01-31T12:00:00Z",
                "created_by": "123e4567-e89b-12d3-a456-426614174001",
                "updated_at": "2026-01-31T12:00:00Z",
                "updated_by": "123e4567-e89b-12d3-a456-426614174001",
                "metadata": {
                    "metadata_id": "223e4567-e89b-12d3-a456-426614174002",
                    "metadata_of": "123e4567-e89b-12d3-a456-426614174000",
                    "metadata_json": {"task_type": "data_processing"},
                    "content_to_summarize": "Job summary content"
                }
            }
        }


class JobListResponse(BaseModel):
    """Response model for list of jobs"""
    count: int
    jobs: list[JobResponse]

    class Config:
        json_schema_extra = {
            "example": {
                "count": 2,
                "jobs": [
                    {
                        "job_id": "123e4567-e89b-12d3-a456-426614174000",
                        "job_result": "PENDING",
                        "created_at": "2026-01-31T12:00:00Z"
                    }
                ]
            }
        }


class JobWithMetadataListResponse(BaseModel):
    """Response model for list of jobs with metadata"""
    count: int
    jobs: list[JobWithMetadataResponse]

    class Config:
        json_schema_extra = {
            "example": {
                "count": 2,
                "jobs": [
                    {
                        "job_id": "123e4567-e89b-12d3-a456-426614174000",
                        "job_result": "COMPLETED",
                        "created_at": "2026-01-31T12:00:00Z",
                        "metadata": {
                            "metadata_id": "223e4567-e89b-12d3-a456-426614174002",
                            "metadata_json": {"task_type": "data_processing"}
                        }
                    }
                ]
            }
        }
