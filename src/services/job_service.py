"""
Job Service for Background Processing Management.

Provides job lifecycle management with status tracking:
PENDING -> PROCESSING -> SUCCESS/FAILED/INTERRUPTED

Features:
- Job registration and tracking
- Status transitions with metadata at each step
- Background task execution with callbacks
- Job cancellation/interruption support
- Thread-safe job state management
"""
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict, Any, Optional, Callable, Awaitable, List, Union
from uuid import UUID, uuid4
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
import traceback
import logging

from sqlalchemy.orm import Session

from src.database.models import Job, Metadatas
from src.database import get_db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Job status enumeration"""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    CANCELLED = "CANCELLED"


@dataclass
class JobContext:
    """
    Context object passed to job functions.
    Allows job to check for interruption and update progress.
    """
    job_id: UUID
    user_id: UUID
    metadata: Dict[str, Any] = field(default_factory=dict)
    _interrupted: bool = False
    _progress: float = 0.0
    _progress_message: str = ""
    _service: 'JobService' = None
    
    @property
    def is_interrupted(self) -> bool:
        """Check if job has been interrupted"""
        return self._interrupted
    
    def check_interrupted(self) -> None:
        """Raise exception if job has been interrupted"""
        if self._interrupted:
            raise JobInterruptedException(f"Job {self.job_id} was interrupted")
    
    def update_progress(self, progress: float, message: str = "") -> None:
        """
        Update job progress (0.0 to 1.0).
        
        Args:
            progress: Progress value between 0.0 and 1.0
            message: Optional progress message
        """
        self._progress = min(max(progress, 0.0), 1.0)
        self._progress_message = message
        
        if self._service:
            self._service._update_job_progress(
                self.job_id,
                self._progress,
                self._progress_message
            )


class JobInterruptedException(Exception):
    """Exception raised when a job is interrupted"""
    pass


class JobService:
    """
    Service for managing background jobs with status tracking.
    
    Usage:
        job_service = JobService()
        
        # Register and run a job
        job_id = await job_service.register_job(
            user_id=user_id,
            task_func=my_async_function,
            metadata={"task_type": "data_processing"}
        )
        
        # Check job status
        status = job_service.get_job_status(job_id)
        
        # Interrupt a job
        job_service.interrupt_job(job_id, reason="User cancelled")
    """
    
    # Singleton instance
    _instance: Optional['JobService'] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> 'JobService':
        """Singleton pattern for job service"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, max_workers: int = 10):
        """
        Initialize job service.
        
        Args:
            max_workers: Maximum number of concurrent workers
        """
        if self._initialized:
            return
            
        self._initialized = True
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: Dict[UUID, JobContext] = {}
        self._futures: Dict[UUID, Future] = {}
        self._callbacks: Dict[UUID, List[Callable]] = {}
        self._job_lock = threading.Lock()
        
        logger.info(f"JobService initialized with {max_workers} workers")
    
    # =========================================================================
    # Job Registration
    # =========================================================================
    
    async def register_job(
        self,
        user_id: UUID,
        task_func: Union[Callable[[JobContext], Any], Callable[[JobContext], Awaitable[Any]]],
        metadata: Optional[Dict[str, Any]] = None,
        auto_start: bool = True,
        db: Optional[Session] = None
    ) -> UUID:
        """
        Register a new job and optionally start it.
        
        Args:
            user_id: User ID who owns the job
            task_func: Function to execute (sync or async)
            metadata: Initial metadata for the job
            auto_start: Whether to start the job immediately
            db: Database session (optional, will create new if not provided)
            
        Returns:
            Job ID
        """
        job_id = uuid4()
        now = datetime.utcnow()
        
        # Create job context
        context = JobContext(
            job_id=job_id,
            user_id=user_id,
            metadata=metadata or {},
            _service=self
        )
        
        # Store in memory
        with self._job_lock:
            self._jobs[job_id] = context
        
        # Persist to database
        if db:
            self._persist_job(db, job_id, user_id, JobStatus.PENDING, metadata, now)
        else:
            # Create new session
            db_gen = get_db()
            try:
                db_session = next(db_gen)
                self._persist_job(db_session, job_id, user_id, JobStatus.PENDING, metadata, now)
            finally:
                try:
                    next(db_gen)
                except StopIteration:
                    pass
        
        logger.info(f"Job {job_id} registered with status PENDING")
        
        # Start job if auto_start
        if auto_start:
            await self.start_job(job_id, task_func)
        
        return job_id
    
    async def start_job(
        self,
        job_id: UUID,
        task_func: Union[Callable[[JobContext], Any], Callable[[JobContext], Awaitable[Any]]]
    ) -> None:
        """
        Start a pending job.
        
        Args:
            job_id: Job ID to start
            task_func: Function to execute
        """
        context = self._get_context(job_id)
        if not context:
            raise ValueError(f"Job {job_id} not found")
        
        # Update status to PROCESSING
        self._update_status(job_id, JobStatus.PROCESSING, {
            "started_at": datetime.utcnow().isoformat()
        })
        
        # Submit to executor
        if asyncio.iscoroutinefunction(task_func):
            # Async function - run in event loop
            future = self._executor.submit(
                self._run_async_task,
                job_id,
                task_func,
                context
            )
        else:
            # Sync function - run directly in thread
            future = self._executor.submit(
                self._run_sync_task,
                job_id,
                task_func,
                context
            )
        
        with self._job_lock:
            self._futures[job_id] = future
        
        logger.info(f"Job {job_id} started processing")
    
    # =========================================================================
    # Job Execution
    # =========================================================================
    
    def _run_sync_task(
        self,
        job_id: UUID,
        task_func: Callable[[JobContext], Any],
        context: JobContext
    ) -> Any:
        """Run synchronous task in thread"""
        try:
            result = task_func(context)
            self._on_job_success(job_id, result)
            return result
        except JobInterruptedException:
            self._on_job_interrupted(job_id, "Job was interrupted")
            raise
        except Exception as e:
            self._on_job_failed(job_id, e)
            raise
    
    def _run_async_task(
        self,
        job_id: UUID,
        task_func: Callable[[JobContext], Awaitable[Any]],
        context: JobContext
    ) -> Any:
        """Run async task in new event loop within thread"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(task_func(context))
            self._on_job_success(job_id, result)
            return result
        except JobInterruptedException:
            self._on_job_interrupted(job_id, "Job was interrupted")
            raise
        except Exception as e:
            self._on_job_failed(job_id, e)
            raise
        finally:
            loop.close()
    
    def _on_job_success(self, job_id: UUID, result: Any) -> None:
        """Handle successful job completion"""
        metadata = {
            "completed_at": datetime.utcnow().isoformat(),
            "result_summary": str(result)[:500] if result else None
        }
        self._update_status(job_id, JobStatus.SUCCESS, metadata)
        self._trigger_callbacks(job_id, JobStatus.SUCCESS, result)
        logger.info(f"Job {job_id} completed successfully")
    
    def _on_job_failed(self, job_id: UUID, error: Exception) -> None:
        """Handle job failure"""
        metadata = {
            "failed_at": datetime.utcnow().isoformat(),
            "error": str(error),
            "traceback": traceback.format_exc()
        }
        self._update_status(job_id, JobStatus.FAILED, metadata)
        self._trigger_callbacks(job_id, JobStatus.FAILED, error)
        logger.error(f"Job {job_id} failed: {error}")
    
    def _on_job_interrupted(self, job_id: UUID, reason: str) -> None:
        """Handle job interruption"""
        metadata = {
            "interrupted_at": datetime.utcnow().isoformat(),
            "interrupt_reason": reason
        }
        self._update_status(job_id, JobStatus.INTERRUPTED, metadata)
        self._trigger_callbacks(job_id, JobStatus.INTERRUPTED, reason)
        logger.warning(f"Job {job_id} interrupted: {reason}")
    
    # =========================================================================
    # Job Control
    # =========================================================================
    
    def interrupt_job(self, job_id: UUID, reason: str = "User requested") -> bool:
        """
        Interrupt a running job.
        
        Args:
            job_id: Job ID to interrupt
            reason: Reason for interruption
            
        Returns:
            True if job was marked for interruption
        """
        context = self._get_context(job_id)
        if not context:
            return False
        
        # Mark as interrupted (job should check this flag)
        context._interrupted = True
        
        # Update metadata
        self._update_status(job_id, JobStatus.INTERRUPTED, {
            "interrupt_reason": reason,
            "interrupted_at": datetime.utcnow().isoformat()
        })
        
        logger.info(f"Job {job_id} marked for interruption: {reason}")
        return True
    
    def cancel_job(self, job_id: UUID) -> bool:
        """
        Cancel a pending job (before it starts).
        
        Args:
            job_id: Job ID to cancel
            
        Returns:
            True if job was cancelled
        """
        context = self._get_context(job_id)
        if not context:
            return False
        
        # Can only cancel pending jobs
        status = self.get_job_status(job_id)
        if status != JobStatus.PENDING:
            return False
        
        # Cancel future if exists
        with self._job_lock:
            if job_id in self._futures:
                self._futures[job_id].cancel()
                del self._futures[job_id]
        
        # Update status
        self._update_status(job_id, JobStatus.CANCELLED, {
            "cancelled_at": datetime.utcnow().isoformat()
        })
        
        logger.info(f"Job {job_id} cancelled")
        return True
    
    # =========================================================================
    # Status & Progress
    # =========================================================================
    
    def get_job_status(self, job_id: UUID) -> Optional[JobStatus]:
        """
        Get current job status.
        
        Args:
            job_id: Job ID
            
        Returns:
            JobStatus or None if job not found
        """
        # Try to get from database
        db_gen = get_db()
        try:
            db = next(db_gen)
            job = db.query(Job).filter(Job.job_id == job_id).first()
            if job:
                return JobStatus(job.job_result) if job.job_result else None
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass
        
        return None
    
    def get_job_info(self, job_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get full job information including metadata.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job info dict or None if not found
        """
        db_gen = get_db()
        try:
            db = next(db_gen)
            job = db.query(Job).filter(Job.job_id == job_id).first()
            if not job:
                return None
            
            # Get metadata
            metadata = db.query(Metadatas).filter(
                Metadatas.metadata_of == job_id
            ).first()
            
            # Get in-memory context for progress
            context = self._get_context(job_id)
            
            return {
                "job_id": str(job.job_id),
                "status": job.job_result,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "created_by": str(job.created_by) if job.created_by else None,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None,
                "metadata": metadata.metadata_json if metadata else {},
                "progress": context._progress if context else None,
                "progress_message": context._progress_message if context else None
            }
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass
    
    def get_active_jobs(self, user_id: Optional[UUID] = None) -> List[Dict[str, Any]]:
        """
        Get all active (PENDING or PROCESSING) jobs.
        
        Args:
            user_id: Filter by user ID (optional)
            
        Returns:
            List of active job info dicts
        """
        db_gen = get_db()
        try:
            db = next(db_gen)
            query = db.query(Job).filter(
                Job.job_result.in_([JobStatus.PENDING.value, JobStatus.PROCESSING.value])
            )
            
            if user_id:
                query = query.filter(Job.created_by == user_id)
            
            jobs = query.all()
            
            return [
                {
                    "job_id": str(job.job_id),
                    "status": job.job_result,
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                    "created_by": str(job.created_by) if job.created_by else None
                }
                for job in jobs
            ]
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass
    
    def _update_job_progress(
        self,
        job_id: UUID,
        progress: float,
        message: str
    ) -> None:
        """Update job progress in metadata"""
        db_gen = get_db()
        try:
            db = next(db_gen)
            metadata = db.query(Metadatas).filter(
                Metadatas.metadata_of == job_id
            ).first()
            
            if metadata:
                current = metadata.metadata_json or {}
                current["progress"] = progress
                current["progress_message"] = message
                current["progress_updated_at"] = datetime.utcnow().isoformat()
                metadata.metadata_json = current
                metadata.updated_at = datetime.utcnow()
                db.commit()
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass
    
    # =========================================================================
    # Callbacks
    # =========================================================================
    
    def add_callback(
        self,
        job_id: UUID,
        callback: Callable[[UUID, JobStatus, Any], None]
    ) -> None:
        """
        Add a callback to be called when job completes.
        
        Args:
            job_id: Job ID
            callback: Callback function(job_id, status, result)
        """
        with self._job_lock:
            if job_id not in self._callbacks:
                self._callbacks[job_id] = []
            self._callbacks[job_id].append(callback)
    
    def _trigger_callbacks(
        self,
        job_id: UUID,
        status: JobStatus,
        result: Any
    ) -> None:
        """Trigger all callbacks for a job"""
        callbacks = self._callbacks.get(job_id, [])
        for callback in callbacks:
            try:
                callback(job_id, status, result)
            except Exception as e:
                logger.error(f"Callback error for job {job_id}: {e}")
    
    # =========================================================================
    # Database Operations
    # =========================================================================
    
    def _persist_job(
        self,
        db: Session,
        job_id: UUID,
        user_id: UUID,
        status: JobStatus,
        metadata: Optional[Dict[str, Any]],
        timestamp: datetime
    ) -> None:
        """Persist job to database"""
        # Create job record
        job = Job(
            job_id=job_id,
            job_result=status.value,
            created_at=timestamp,
            created_by=user_id,
            updated_at=timestamp,
            updated_by=user_id
        )
        db.add(job)
        
        # Create metadata record
        if metadata:
            metadata_record = Metadatas(
                metadata_id=uuid4(),
                metadata_of=job_id,
                metadata_json={
                    "status_history": [{
                        "status": status.value,
                        "timestamp": timestamp.isoformat(),
                        "data": metadata
                    }],
                    **metadata
                },
                created_at=timestamp,
                created_by=user_id,
                updated_at=timestamp,
                updated_by=user_id
            )
            db.add(metadata_record)
        
        db.commit()
    
    def _update_status(
        self,
        job_id: UUID,
        status: JobStatus,
        metadata_update: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update job status in database"""
        db_gen = get_db()
        try:
            db = next(db_gen)
            now = datetime.utcnow()
            
            # Update job
            job = db.query(Job).filter(Job.job_id == job_id).first()
            if job:
                job.job_result = status.value
                job.updated_at = now
            
            # Update metadata
            metadata = db.query(Metadatas).filter(
                Metadatas.metadata_of == job_id
            ).first()
            
            if metadata:
                current = metadata.metadata_json or {}
                
                # Add to status history
                if "status_history" not in current:
                    current["status_history"] = []
                
                current["status_history"].append({
                    "status": status.value,
                    "timestamp": now.isoformat(),
                    "data": metadata_update
                })
                
                # Merge metadata update
                if metadata_update:
                    current.update(metadata_update)
                
                current["current_status"] = status.value
                current["last_updated"] = now.isoformat()
                
                metadata.metadata_json = current
                metadata.updated_at = now
            elif metadata_update:
                # Create new metadata if none exists
                context = self._get_context(job_id)
                user_id = context.user_id if context else job.created_by
                
                metadata_record = Metadatas(
                    metadata_id=uuid4(),
                    metadata_of=job_id,
                    metadata_json={
                        "status_history": [{
                            "status": status.value,
                            "timestamp": now.isoformat(),
                            "data": metadata_update
                        }],
                        "current_status": status.value,
                        **metadata_update
                    },
                    created_at=now,
                    created_by=user_id,
                    updated_at=now,
                    updated_by=user_id
                )
                db.add(metadata_record)
            
            db.commit()
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass
    
    # =========================================================================
    # Internal Helpers
    # =========================================================================
    
    def _get_context(self, job_id: UUID) -> Optional[JobContext]:
        """Get job context from memory"""
        with self._job_lock:
            return self._jobs.get(job_id)
    
    def cleanup_completed_jobs(self, older_than_hours: int = 24) -> int:
        """
        Clean up completed job contexts from memory.
        
        Args:
            older_than_hours: Remove jobs older than this many hours
            
        Returns:
            Number of jobs cleaned up
        """
        cleaned = 0
        completed_statuses = [
            JobStatus.SUCCESS, JobStatus.FAILED,
            JobStatus.INTERRUPTED, JobStatus.CANCELLED
        ]
        
        with self._job_lock:
            to_remove = []
            for job_id in list(self._jobs.keys()):
                status = self.get_job_status(job_id)
                if status in completed_statuses:
                    to_remove.append(job_id)
            
            for job_id in to_remove:
                del self._jobs[job_id]
                if job_id in self._futures:
                    del self._futures[job_id]
                if job_id in self._callbacks:
                    del self._callbacks[job_id]
                cleaned += 1
        
        logger.info(f"Cleaned up {cleaned} completed jobs from memory")
        return cleaned
    
    def shutdown(self, wait: bool = True) -> None:
        """
        Shutdown the job service.
        
        Args:
            wait: Wait for running jobs to complete
        """
        logger.info("Shutting down JobService...")
        self._executor.shutdown(wait=wait)
        logger.info("JobService shutdown complete")


# Global instance
job_service = JobService()


# =========================================================================
# Convenience Functions
# =========================================================================

async def register_background_job(
    user_id: UUID,
    task_func: Union[Callable[[JobContext], Any], Callable[[JobContext], Awaitable[Any]]],
    metadata: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None
) -> UUID:
    """
    Convenience function to register and start a background job.
    
    Args:
        user_id: User ID
        task_func: Task function to execute
        metadata: Initial metadata
        db: Database session
        
    Returns:
        Job ID
    """
    return await job_service.register_job(
        user_id=user_id,
        task_func=task_func,
        metadata=metadata,
        auto_start=True,
        db=db
    )


def get_job_status(job_id: UUID) -> Optional[JobStatus]:
    """Get job status by ID"""
    return job_service.get_job_status(job_id)


def interrupt_job(job_id: UUID, reason: str = "User requested") -> bool:
    """Interrupt a running job"""
    return job_service.interrupt_job(job_id, reason)
