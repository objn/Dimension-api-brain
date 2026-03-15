"""
Job CRUD controller.
All operations use ORM - no raw SQL queries.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime, timedelta

from src.database import get_db
from src.repositories.job_repository import JobRepository
from src.repositories.base_repository import BaseRepository
from src.database.models import Job, Metadatas
from src.dto.job_dto import (
    JobCreateRequest,
    JobUpdateStatusRequest,
    JobInterruptRequest,
    JobHandleRequest,
    JobHandleAction,
    JobResponse,
    JobWithMetadataResponse,
    JobListResponse,
    JobWithMetadataListResponse
)
from src.dto.metadata_dto import MetadataResponse
from src.dto.response_dto import success_response, error_response
from src.utils.auth import get_current_user_id
from src.services.job_service import job_service, JobStatus

router = APIRouter(
    prefix="/jobs",
    tags=["Jobs"]
)


# ============================================================================
# GET Endpoints
# ============================================================================

@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Get jobs by owner with optional filters",
    description="Retrieve jobs created by the authenticated user. Use query parameters: metadata=true, actived=true, result=STATUS, limit=N"
)
async def get_all_jobs(
    limit: Optional[int] = None,
    metadata: bool = False,
    actived: Optional[bool] = None,
    result: Optional[str] = None,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    Get all jobs created by the authenticated user with optional filters.
    
    Query Parameters:
    - metadata: Include job metadata (default: false)  
    - actived: Filter by activated status (true/false, default: all)
    - result: Filter by job result status (PENDING, PROCESSING, SUCCESS, etc.)
    - limit: Maximum number of results to return
    """
    try:
        repo = JobRepository(db)
        
        # Start with base query - get jobs or jobs with metadata
        if metadata:
            results = repo.find_by_creator_with_metadata(user_id)
            # Apply filters on the results
            filtered_results = []
            for job, meta in results:
                # Filter by actived status if specified
                if actived is not None and job.job_actived != actived:
                    continue
                # Filter by result status if specified
                if result is not None and job.job_result != result:
                    continue
                filtered_results.append((job, meta))
            
            # Apply limit
            if limit:
                filtered_results = filtered_results[:limit]
            
            # Convert to response format
            jobs_with_metadata = []
            for job, metadata_obj in filtered_results:
                job_data = JobWithMetadataResponse(
                    job_id=job.job_id,
                    job_type=job.job_type,
                    job_start_time=job.job_start_time,
                    job_end_time=job.job_end_time,
                    job_actived=job.job_actived,
                    job_result=job.job_result,
                    job_error_log=getattr(job, "job_error_log", None),
                    created_at=job.created_at,
                    created_by=job.created_by,
                    updated_at=job.updated_at,
                    updated_by=job.updated_by,
                    metadata=MetadataResponse.model_validate(metadata_obj) if metadata_obj else None
                )
                jobs_with_metadata.append(job_data)
            
            result_response = JobWithMetadataListResponse(
                count=len(jobs_with_metadata),
                jobs=jobs_with_metadata
            )
            return success_response(result_response.model_dump())
        else:
            # Get jobs without metadata
            jobs = repo.find_by_creator(user_id)
            
            # Apply filters
            filtered_jobs = []
            for job in jobs:
                # Filter by actived status if specified
                if actived is not None and job.job_actived != actived:
                    continue
                # Filter by result status if specified  
                if result is not None and job.job_result != result:
                    continue
                filtered_jobs.append(job)
            
            # Apply limit
            if limit:
                filtered_jobs = filtered_jobs[:limit]
            
            result_response = JobListResponse(
                count=len(filtered_jobs),
                jobs=[JobResponse.model_validate(job) for job in filtered_jobs]
            )
            return success_response(result_response.model_dump())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching jobs: {str(e)}"
        )



# ============================================================================
# Daemon Control Endpoints (Debug)
# ============================================================================

@router.get(
    "/daemon/status",
    status_code=status.HTTP_200_OK,
    summary="Get daemon status",
    description="Get the current status of the job daemon (for debugging)"
)
async def get_daemon_status(
    user_id: UUID = Depends(get_current_user_id)
):
    """Get daemon status including running state, poll stats, etc."""
    from src.services.job_daemon import job_daemon
    
    return success_response(job_daemon.get_status())


@router.post(
    "/daemon/start",
    status_code=status.HTTP_200_OK,
    summary="Start daemon",
    description="Start the job daemon if not already running (for debugging)"
)
async def start_daemon(
    user_id: UUID = Depends(get_current_user_id)
):
    """Start the job daemon."""
    from src.services.job_daemon import job_daemon
    
    if job_daemon.is_running:
        return success_response({
            "message": "Daemon is already running",
            "started": False
        })
    
    job_daemon.start()
    return success_response({
        "message": "Daemon started",
        "started": True
    })


@router.post(
    "/daemon/stop",
    status_code=status.HTTP_200_OK,
    summary="Stop daemon",
    description="Stop the job daemon gracefully (for debugging)"
)
async def stop_daemon(
    user_id: UUID = Depends(get_current_user_id)
):
    """Stop the job daemon."""
    from src.services.job_daemon import job_daemon
    
    if not job_daemon.is_running:
        return success_response({
            "message": "Daemon is not running",
            "stopped": False
        })
    
    job_daemon.stop()
    return success_response({
        "message": "Daemon stopped",
        "stopped": True
    })


@router.get(
    "/{job_id}",
    status_code=status.HTTP_200_OK,
    summary="Get job by ID with metadata",
    description="Retrieve a single job by ID with its metadata (only if created by authenticated user)"
)
async def get_job_by_id(
    job_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Get job by ID with metadata - uses ORM, only returns if user owns the job"""
    try:
        repo = JobRepository(db)
        result = repo.find_one_by_id_with_metadata(job_id)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job with ID {job_id} not found"
            )

        job, metadata = result

        if job.created_by != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this job"
            )

        response = JobWithMetadataResponse(
            job_id=job.job_id,
            job_type=job.job_type,
            job_start_time=job.job_start_time,
            job_end_time=job.job_end_time,
            job_actived=job.job_actived,
            job_result=job.job_result,
            job_error_log=getattr(job, "job_error_log", None),
            created_at=job.created_at,
            created_by=job.created_by,
            updated_at=job.updated_at,
            updated_by=job.updated_by,
            metadata=MetadataResponse.model_validate(metadata) if metadata else None
        )
        return success_response(response.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching job: {str(e)}"
        )


# ============================================================================
# POST Endpoints
# ============================================================================

@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Register a new job with metadata",
    description="Create a new job and its associated metadata"
)
async def create_job(
    request: JobCreateRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Create a new job with optional metadata"""
    try:
        now = datetime.utcnow()
        job_id = uuid4()
        job_type_value = request.job_type.value if hasattr(request.job_type, 'value') else request.job_type
        job_start_time = request.job_start_time or (now + timedelta(minutes=1))

        # Create job with type and timing
        new_job = Job(
            job_id=job_id,
            job_type=job_type_value,
            job_start_time=job_start_time,
            job_end_time=None,
            job_actived=False,
            job_result=request.job_result or "PENDING",
            created_at=now,
            created_by=user_id,
            updated_at=now,
            updated_by=user_id
        )

        repo = JobRepository(db)
        created_job = repo.create(new_job)

        # Create metadata
        metadata_response = None
        metadata_json = request.metadata_json or {}
        metadata_json["job_type"] = job_type_value
        
        metadata_id = uuid4()
        new_metadata = Metadatas(
            metadata_id=metadata_id,
            metadata_of=job_id,
            metadata_json=metadata_json,
            content_to_summarize=request.content_to_summarize,
            created_at=now,
            created_by=user_id,
            updated_at=now,
            updated_by=user_id
        )
        db.add(new_metadata)
        db.commit()
        db.refresh(new_metadata)
        metadata_response = MetadataResponse.model_validate(new_metadata)

        response = JobWithMetadataResponse(
            job_id=created_job.job_id,
            job_type=created_job.job_type,
            job_start_time=created_job.job_start_time,
            job_end_time=created_job.job_end_time,
            job_actived=created_job.job_actived,
            job_result=created_job.job_result,
            created_at=created_job.created_at,
            created_by=created_job.created_by,
            updated_at=created_job.updated_at,
            updated_by=created_job.updated_by,
            metadata=metadata_response
        )
        return success_response(response.model_dump())
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating job: {str(e)}"
        )


# ============================================================================
# PUT Endpoints
# ============================================================================

@router.put(
    "/{job_id}",
    status_code=status.HTTP_200_OK,
    summary="Update job status and metadata",
    description="Update job status and its associated metadata"
)
async def update_job_status(
    job_id: UUID,
    request: JobUpdateStatusRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Update job status and metadata"""
    try:
        repo = JobRepository(db)
        job = repo.find_one_by_id(job_id)

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job with ID {job_id} not found"
            )

        if job.created_by != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this job"
            )

        now = datetime.utcnow()

        # Update job
        updated_job = repo.update_by_id(job_id, {
            "job_result": request.job_result,
            "updated_at": now,
            "updated_by": user_id
        })

        # Update or create metadata
        metadata_response = None
        existing_metadata = db.query(Metadatas).filter(
            Metadatas.metadata_of == job_id
        ).first()

        if existing_metadata:
            # Update existing metadata
            if request.metadata_json is not None:
                existing_metadata.metadata_json = request.metadata_json
            if request.content_to_summarize is not None:
                existing_metadata.content_to_summarize = request.content_to_summarize
            existing_metadata.updated_at = now
            existing_metadata.updated_by = user_id
            db.commit()
            db.refresh(existing_metadata)
            metadata_response = MetadataResponse.model_validate(existing_metadata)
        elif request.metadata_json is not None or request.content_to_summarize is not None:
            # Create new metadata
            metadata_id = uuid4()
            new_metadata = Metadatas(
                metadata_id=metadata_id,
                metadata_of=job_id,
                metadata_json=request.metadata_json,
                content_to_summarize=request.content_to_summarize,
                created_at=now,
                created_by=user_id,
                updated_at=now,
                updated_by=user_id
            )
            db.add(new_metadata)
            db.commit()
            db.refresh(new_metadata)
            metadata_response = MetadataResponse.model_validate(new_metadata)

        response = JobWithMetadataResponse(
            job_id=updated_job.job_id,
            job_type=updated_job.job_type,
            job_start_time=updated_job.job_start_time,
            job_end_time=updated_job.job_end_time,
            job_actived=updated_job.job_actived,
            job_result=updated_job.job_result,
            created_at=updated_job.created_at,
            created_by=updated_job.created_by,
            updated_at=updated_job.updated_at,
            updated_by=updated_job.updated_by,
            metadata=metadata_response
        )
        return success_response(response.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating job: {str(e)}"
        )


# ============================================================================
# PATCH Endpoints 
# ============================================================================

@router.patch(
    "/{job_id}/set-pending",
    status_code=status.HTTP_200_OK,
    summary="Set job status to PENDING",
    description="Set the job status to PENDING by job ID. No request body required. Only job owner can call."
)
async def set_job_pending(
    job_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Set job status to PENDING so it can be picked up by the daemon again."""
    try:
        repo = JobRepository(db)
        job = repo.find_one_by_id(job_id)

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job with ID {job_id} not found"
            )

        if job.created_by != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this job"
            )

        now = datetime.utcnow()
        updated_job = repo.update_by_id(job_id, {
            "job_result": "PENDING",
            "job_actived": False,
            "job_end_time": None,
            "updated_at": now,
            "updated_by": user_id
        })

        metadata_response = None
        existing_metadata = db.query(Metadatas).filter(
            Metadatas.metadata_of == job_id
        ).first()
        if existing_metadata:
            metadata_response = MetadataResponse.model_validate(existing_metadata)

        response = JobWithMetadataResponse(
            job_id=updated_job.job_id,
            job_type=updated_job.job_type,
            job_start_time=updated_job.job_start_time,
            job_end_time=updated_job.job_end_time,
            job_actived=updated_job.job_actived,
            job_result=updated_job.job_result,
            job_error_log=getattr(updated_job, "job_error_log", None),
            created_at=updated_job.created_at,
            created_by=updated_job.created_by,
            updated_at=updated_job.updated_at,
            updated_by=updated_job.updated_by,
            metadata=metadata_response
        )
        return success_response(response.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error setting job to PENDING: {str(e)}"
        )


@router.patch(
    "/{job_id}",
    status_code=status.HTTP_200_OK,
    summary="Handle job actions (start/restart/stop)",
    description="Handle job actions: start (set to processing), restart (set to pending), stop (set to skip)"
)
async def handle_job(
    request: JobHandleRequest,
    job_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Handle job actions based on handleJobTo parameter"""
    try:
        repo = JobRepository(db)
        job = repo.find_one_by_id(job_id)

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job with ID {request.job_id} not found"
            )

        if job.created_by != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to handle this job"
            )

        now = datetime.utcnow()
        reason = request.reason or f"User requested {request.handleJobTo.value}"
        
        if request.handleJobTo == JobHandleAction.START:
            # Set job to processing and start it
            if job.job_result not in ["PENDING"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot start job with status '{job.job_result}'. Only PENDING jobs can be started."
                )
            
            updated_job = repo.update_by_id(job_id, {
                "job_result": "PROCESSING",
                "job_actived": True,
                "updated_at": now,
                "updated_by": user_id
            })
            action_key = "start_reason"
            action_time_key = "started_at"
            
        elif request.handleJobTo == JobHandleAction.RESTART:
            # Set job to pending, wait for daemon
            updated_job = repo.update_by_id(job_id, {
                "job_result": "PENDING",
                "job_actived": False,
                "updated_at": now,
                "updated_by": user_id
            })
            action_key = "restart_reason"
            action_time_key = "restarted_at"
            
        elif request.handleJobTo == JobHandleAction.STOP:
            # Set job to skip and stop it
            if job.job_result in ["SUCCESS", "FAILED", "SKIP", "CANCELLED", "INTERRUPTED"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot stop job with status '{job.job_result}'. Job already completed."
                )
            
            # Signal service to stop if running
            if job.job_result in ["PROCESSING", "RUNNING"]:
                job_service.interrupt_job(job_id, reason=reason)
            
            updated_job = repo.update_by_id(job_id, {
                "job_result": "SKIP",
                "updated_at": now,
                "updated_by": user_id
            })
            action_key = "stop_reason"
            action_time_key = "stopped_at"

        # Update metadata
        metadata_response = None
        existing_metadata = db.query(Metadatas).filter(
            Metadatas.metadata_of == job_id
        ).first()

        if existing_metadata:
            current_json = existing_metadata.metadata_json or {}
            current_json[action_key] = reason
            current_json[action_time_key] = now.isoformat()
            existing_metadata.metadata_json = current_json
            existing_metadata.updated_at = now
            existing_metadata.updated_by = user_id
            db.commit()
            db.refresh(existing_metadata)
            metadata_response = MetadataResponse.model_validate(existing_metadata)
        elif reason:
            metadata_id = uuid4()
            new_metadata = Metadatas(
                metadata_id=metadata_id,
                metadata_of=job_id,
                metadata_json={
                    action_key: reason,
                    action_time_key: now.isoformat()
                },
                created_at=now,
                created_by=user_id,
                updated_at=now,
                updated_by=user_id
            )
            db.add(new_metadata)
            db.commit()
            db.refresh(new_metadata)
            metadata_response = MetadataResponse.model_validate(new_metadata)

        response = JobWithMetadataResponse(
            job_id=updated_job.job_id,
            job_type=updated_job.job_type,
            job_start_time=updated_job.job_start_time,
            job_end_time=updated_job.job_end_time,
            job_actived=updated_job.job_actived,
            job_result=updated_job.job_result,
            created_at=updated_job.created_at,
            created_by=updated_job.created_by,
            updated_at=updated_job.updated_at,
            updated_by=updated_job.updated_by,
            metadata=metadata_response
        )
        return success_response(response.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error handling job: {str(e)}"
        )




# ============================================================================
# DELETE Endpoints
# ============================================================================

@router.delete(
    "/{job_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a job and its metadata",
    description="Delete a job and its associated metadata"
)
async def delete_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Delete a job and its metadata"""
    try:
        repo = JobRepository(db)
        job = repo.find_one_by_id(job_id)

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job with ID {job_id} not found"
            )

        if job.created_by != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this job"
            )

        # Delete associated metadata first
        db.query(Metadatas).filter(
            Metadatas.metadata_of == job_id
        ).delete()

        # Delete job
        deleted = repo.delete_by_id(job_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete job"
            )

        return success_response({
            "message": f"Job {job_id} and its metadata deleted successfully",
            "job_id": str(job_id)
        })
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting job: {str(e)}"
        )


# ============================================================================
# Service-based Job Management Endpoints
# ============================================================================

