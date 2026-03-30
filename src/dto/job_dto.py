"""
DTOs for Job operations.
Request and response models with validation.
"""
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
from uuid import UUID
from enum import Enum

from .base_dto import BaseResponseModel
from .metadata_dto import MetadataResponse


class JobType(str, Enum):
    """Allowed job types (must match TaskRegistry registration in main.py)."""
    PROCESS_DOCUMENT = "process_document"
    NODE_CONTENT_EMBEDDING = "node_content_embedding"


class JobHandleAction(str, Enum):
    """Actions for handling jobs"""
    START = "start"
    RESTART = "restart" 
    STOP = "stop"


class JobHandleRequest(BaseModel):
    """Request body for handling jobs (start/restart/stop)"""
    handleJobTo: JobHandleAction = Field(..., description="Action to perform on the job")
    reason: Optional[str] = Field(None, description="Optional reason for the action")

    class Config:
        json_schema_extra = {
            "example": {
                "handleJobTo": "start",
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "reason": "User requested start"
            }
        }


class JobCreateRequest(BaseModel):
    """Request body for creating a job with metadata"""
    job_type: JobType = Field(..., description="Type of the job")
    job_start_time: Optional[datetime] = Field(
        None,
        description="When to allow the daemon to pick up this job. Defaults to now (immediate) if omitted.",
    )
    job_result: Optional[str] = Field(
        "PENDING",
        max_length=16,
        description="Ignored on create: new jobs are always registered as PENDING.",
    )
    metadata_json: Optional[dict] = Field(
        None,
        description=(
            "Task parameters in Metadatas.metadata_json. "
            "For process_document include file_id (UUID string); when create_node is true also workspace_id and authorization (full Bearer value). "
            "Optional: reformat_options, llm_provider, create_node, use_llm_extract, max_pages_per_call, translate_to. "
            "For node_content_embedding include node_id and optional force_reembed."
        ),
    )
    content_to_summarize: Optional[str] = Field(None, description="Optional Metadatas.content_to_summarize column")

    class Config:
        json_schema_extra = {
            "example": {
                "job_type": "process_document",
                "job_start_time": "2026-02-11T12:00:00Z",
                "metadata_json": {
                    "file_id": "660e8400-e29b-41d4-a716-446655440001",
                    "workspace_id": "770e8400-e29b-41d4-a716-446655440002",
                    "authorization": "Bearer <user_access_token>",
                    "reformat_options": [],
                    "llm_provider": "openai",
                    "create_node": True,
                    "use_llm_extract": False,
                    "max_pages_per_call": 5,
                    "translate_to": None,
                },
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
    job_type: Optional[str] = None
    job_start_time: Optional[datetime] = None
    job_end_time: Optional[datetime] = None
    job_actived: Optional[bool] = None
    job_result: Optional[str]
    job_error_log: Optional[str] = None
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
    job_type: Optional[str] = None
    job_start_time: Optional[datetime] = None
    job_end_time: Optional[datetime] = None
    job_actived: Optional[bool] = None
    job_result: Optional[str]
    job_error_log: Optional[str] = None
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
