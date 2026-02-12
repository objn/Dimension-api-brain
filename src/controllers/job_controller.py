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
    summary="Get all jobs by owner",
    description="Retrieve all jobs created by the authenticated user"
)
async def get_all_jobs(
    limit: Optional[int] = None,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Get all jobs created by the authenticated user - uses ORM query"""
    try:
        repo = JobRepository(db)
        jobs = repo.find_by_creator(user_id)

        if limit:
            jobs = jobs[:limit]

        result = JobListResponse(
            count=len(jobs),
            jobs=[JobResponse.model_validate(job) for job in jobs]
        )
        return success_response(result.model_dump())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching jobs: {str(e)}"
        )


@router.get(
    "/metadata",
    status_code=status.HTTP_200_OK,
    summary="Get all jobs with metadata by owner",
    description="Retrieve all jobs with their metadata created by the authenticated user"
)
async def get_all_jobs_with_metadata(
    limit: Optional[int] = None,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Get all jobs with metadata created by the authenticated user"""
    try:
        repo = JobRepository(db)
        results = repo.find_by_creator_with_metadata(user_id)

        if limit:
            results = results[:limit]

        jobs_with_metadata = []
        for job, metadata in results:
            job_data = JobWithMetadataResponse(
                job_id=job.job_id,
                job_type=job.job_type,
                job_start_time=job.job_start_time,
                job_end_time=job.job_end_time,
                job_actived=job.job_actived,
                job_result=job.job_result,
                created_at=job.created_at,
                created_by=job.created_by,
                updated_at=job.updated_at,
                updated_by=job.updated_by,
                metadata=MetadataResponse.model_validate(metadata) if metadata else None
            )
            jobs_with_metadata.append(job_data)

        result = JobWithMetadataListResponse(
            count=len(jobs_with_metadata),
            jobs=jobs_with_metadata
        )
        return success_response(result.model_dump())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching jobs with metadata: {str(e)}"
        )

@router.get(
    "/active",
    status_code=status.HTTP_200_OK,
    summary="Get all active jobs",
    description="Retrieve all active (PENDING or PROCESSING) jobs for the authenticated user"
)
async def get_active_jobs(
    user_id: UUID = Depends(get_current_user_id)
):
    """Get all active jobs for the current user"""
    try:
        active_jobs = job_service.get_active_jobs(user_id)
        return success_response({
            "count": len(active_jobs),
            "jobs": active_jobs
        })
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching active jobs: {str(e)}"
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
    "/{job_id}/interrupt",
    status_code=status.HTTP_200_OK,
    summary="Interrupt a job",
    description="Interrupt a running job by setting its status to INTERRUPTED"
)
async def interrupt_job(
    job_id: UUID,
    request: Optional[JobInterruptRequest] = None,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Interrupt a job - sets status to INTERRUPTED"""
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
                detail="You don't have permission to interrupt this job"
            )

        # Check if job can be interrupted (only PENDING or PROCESSING/RUNNING jobs)
        interruptable_statuses = ["PENDING", "PROCESSING", "RUNNING"]
        if job.job_result not in interruptable_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot interrupt job with status '{job.job_result}'. Only PENDING or PROCESSING jobs can be interrupted."
            )

        now = datetime.utcnow()
        reason = request.reason if request else "User requested"

        # Signal the in-memory job context to stop (cooperative cancellation)
        service_interrupted = job_service.interrupt_job(job_id, reason=reason)
        if not service_interrupted:
            # Job not tracked in-memory (maybe old/restarted), update DB directly
            pass

        # Update job status to INTERRUPTED in DB
        updated_job = repo.update_by_id(job_id, {
            "job_result": "INTERRUPTED",
            "updated_at": now,
            "updated_by": user_id
        })

        # Update metadata with interrupt reason if provided
        metadata_response = None
        existing_metadata = db.query(Metadatas).filter(
            Metadatas.metadata_of == job_id
        ).first()

        if existing_metadata:
            if request and request.reason:
                # Add interrupt reason to metadata
                current_json = existing_metadata.metadata_json or {}
                current_json["interrupt_reason"] = request.reason
                current_json["interrupted_at"] = now.isoformat()
                existing_metadata.metadata_json = current_json
            existing_metadata.updated_at = now
            existing_metadata.updated_by = user_id
            db.commit()
            db.refresh(existing_metadata)
            metadata_response = MetadataResponse.model_validate(existing_metadata)
        elif request and request.reason:
            # Create new metadata with interrupt reason
            metadata_id = uuid4()
            new_metadata = Metadatas(
                metadata_id=metadata_id,
                metadata_of=job_id,
                metadata_json={
                    "interrupt_reason": request.reason,
                    "interrupted_at": now.isoformat()
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
            detail=f"Error interrupting job: {str(e)}"
        )


@router.patch(
    "/{job_id}/cancel",
    status_code=status.HTTP_200_OK,
    summary="Cancel a pending job",
    description="Cancel a job that has not yet started processing"
)
async def cancel_job(
    job_id: UUID,
    request: Optional[JobInterruptRequest] = None,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Cancel a pending job before it starts"""
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
                detail="You don't have permission to cancel this job"
            )

        if job.job_result != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel job with status '{job.job_result}'. Only PENDING jobs can be cancelled."
            )

        now = datetime.utcnow()
        reason = request.reason if request else "User cancelled"

        # Signal the in-memory job service to cancel
        job_service.cancel_job(job_id)

        # Update job status to CANCELLED in DB
        updated_job = repo.update_by_id(job_id, {
            "job_result": "CANCELLED",
            "updated_at": now,
            "updated_by": user_id
        })

        # Update metadata
        metadata_response = None
        existing_metadata = db.query(Metadatas).filter(
            Metadatas.metadata_of == job_id
        ).first()

        if existing_metadata:
            current_json = existing_metadata.metadata_json or {}
            current_json["cancel_reason"] = reason
            current_json["cancelled_at"] = now.isoformat()
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
                    "cancel_reason": reason,
                    "cancelled_at": now.isoformat()
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
            detail=f"Error cancelling job: {str(e)}"
        )


@router.patch(
    "/{job_id}/stop",
    status_code=status.HTTP_200_OK,
    summary="Stop a job (cancel or interrupt)",
    description="Unified endpoint to stop a job. Cancels PENDING jobs, interrupts PROCESSING/RUNNING jobs."
)
async def stop_job(
    job_id: UUID,
    request: Optional[JobInterruptRequest] = None,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    Unified stop endpoint.
    - PENDING jobs -> CANCELLED
    - PROCESSING/RUNNING jobs -> INTERRUPTED (cooperative via context flag)
    """
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
                detail="You don't have permission to stop this job"
            )

        stoppable_statuses = ["PENDING", "PROCESSING", "RUNNING"]
        if job.job_result not in stoppable_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot stop job with status '{job.job_result}'. Only PENDING or PROCESSING jobs can be stopped."
            )

        now = datetime.utcnow()
        reason = request.reason if request else "User requested stop"

        if job.job_result == "PENDING":
            # Cancel pending job
            job_service.cancel_job(job_id)
            new_status = "CANCELLED"
            meta_key = "cancel_reason"
            meta_time_key = "cancelled_at"
        else:
            # Interrupt running job (sets context._interrupted = True)
            job_service.interrupt_job(job_id, reason=reason)
            new_status = "INTERRUPTED"
            meta_key = "interrupt_reason"
            meta_time_key = "interrupted_at"

        # Update DB
        updated_job = repo.update_by_id(job_id, {
            "job_result": new_status,
            "updated_at": now,
            "updated_by": user_id
        })

        # Update metadata
        metadata_response = None
        existing_metadata = db.query(Metadatas).filter(
            Metadatas.metadata_of == job_id
        ).first()

        if existing_metadata:
            current_json = existing_metadata.metadata_json or {}
            current_json[meta_key] = reason
            current_json[meta_time_key] = now.isoformat()
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
                    meta_key: reason,
                    meta_time_key: now.isoformat()
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
            detail=f"Error stopping job: {str(e)}"
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

@router.get(
    "/{job_id}/status",
    status_code=status.HTTP_200_OK,
    summary="Get job status",
    description="Get the current status of a job"
)
async def get_job_status_endpoint(
    job_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Get job status with progress information"""
    try:
        # Verify ownership
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
                detail="You don't have permission to access this job"
            )
        
        # Get full job info from service
        job_info = job_service.get_job_info(job_id)
        
        if job_info:
            return success_response(job_info)
        else:
            return success_response({
                "job_id": str(job_id),
                "status": job.job_result,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None
            })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching job status: {str(e)}"
        )


@router.get(
    "/{job_id}/history",
    status_code=status.HTTP_200_OK,
    summary="Get job status history",
    description="Get the status transition history of a job"
)
async def get_job_history(
    job_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Get job status history from metadata"""
    try:
        # Verify ownership
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
                detail="You don't have permission to access this job"
            )
        
        # Get metadata with history
        metadata = db.query(Metadatas).filter(
            Metadatas.metadata_of == job_id
        ).first()
        
        if metadata and metadata.metadata_json:
            history = metadata.metadata_json.get("status_history", [])
            return success_response({
                "job_id": str(job_id),
                "current_status": job.job_result,
                "history": history
            })
        else:
            return success_response({
                "job_id": str(job_id),
                "current_status": job.job_result,
                "history": []
            })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching job history: {str(e)}"
        )

