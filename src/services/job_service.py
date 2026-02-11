"""
Job Service for Background Processing Management.

Architecture v2 - Daemon-driven:
    - register_job() only creates DB record (PENDING)
    - JobDaemon polls DB for ready jobs and calls activate_job()
    - activate_job() atomically claims job (PENDING -> PROCESSING) and submits to thread pool
    - Race condition prevention via DB-level atomic update
    - Returns worker_break_off_time when pool is full

Status Flow:
    PENDING -> PROCESSING -> SUCCESS / FAILED / INTERRUPTED / CANCELLED
"""
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict, Any, Optional, Callable, Awaitable, List, Union
from uuid import UUID, uuid4
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
import traceback
import logging

from sqlalchemy.orm import Session
from sqlalchemy import update

from src.database.models import Job, Metadatas
from src.database import get_db
from src.config.settings import settings

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


class ActivateResult:
    """Result of activate_job() call"""
    
    def __init__(
        self,
        activated: bool,
        reason: str = "",
        worker_break_off_time: int = 0
    ):
        self.activated = activated
        self.reason = reason
        self.worker_break_off_time = worker_break_off_time
    
    def to_dict(self) -> Dict[str, Any]:
        result = {"activated": self.activated, "reason": self.reason}
        if self.worker_break_off_time > 0:
            result["worker_break_off_time"] = self.worker_break_off_time
        return result


class JobService:
    """
    Service for managing background jobs with status tracking.
    
    v2 Architecture:
        - register_job() -> creates DB record only (PENDING)
        - activate_job() -> atomically claims + submits to thread pool
        - JobDaemon calls activate_job() when job is ready
        - Task functions come from TaskRegistry
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
    
    def __init__(self):
        """Initialize job service with settings from config."""
        if self._initialized:
            return
            
        self._initialized = True
        self._max_workers = settings.job_worker_num
        self._break_off_time = settings.job_worker_break_off_time
        self._executor = ThreadPoolExecutor(max_workers=self._max_workers)
        self._jobs: Dict[UUID, JobContext] = {}
        self._futures: Dict[UUID, Future] = {}
        self._callbacks: Dict[UUID, List[Callable]] = {}
        self._job_lock = threading.Lock()
        
        logger.info(
            f"JobService initialized: workers={self._max_workers}, "
            f"break_off_time={self._break_off_time}s"
        )
    
    # =========================================================================
    # Job Registration (DB only - no execution)
    # =========================================================================
    
    async def register_job(
        self,
        user_id: UUID,
        job_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        job_start_time: Optional[datetime] = None,
        db: Optional[Session] = None
    ) -> UUID:
        """
        Register a new job in the database with status PENDING.
        
        This ONLY creates the DB record. The JobDaemon will pick it up
        when job_start_time <= now and call activate_job().
        
        Args:
            user_id: User ID who owns the job
            job_type: Type of the job (must be registered in TaskRegistry)
            metadata: Job metadata (task parameters stored here)
            job_start_time: Scheduled start time (defaults to now + 1 min)
            db: Database session (optional, will create new if not provided)
            
        Returns:
            Job ID
        """
        job_id = uuid4()
        now = datetime.utcnow()
        
        # Default start time: now + 1 minute
        if job_start_time is None:
            job_start_time = now + timedelta(minutes=1)
        
        # Persist to database
        if db:
            self._persist_job(db, job_id, user_id, JobStatus.PENDING, metadata, now, job_type, job_start_time)
        else:
            db_gen = get_db()
            try:
                db_session = next(db_gen)
                self._persist_job(db_session, job_id, user_id, JobStatus.PENDING, metadata, now, job_type, job_start_time)
            finally:
                try:
                    next(db_gen)
                except StopIteration:
                    pass
        
        logger.info(f"Job {job_id} registered (type={job_type}, start_time={job_start_time})")
        return job_id
    
    # =========================================================================
    # Job Activation (called by Daemon)
    # =========================================================================
    
    def activate_job(self, job_id: UUID) -> ActivateResult:
        """
        Activate a pending job: atomically claim it and submit to thread pool.
        
        Called by JobDaemon when a job is ready to run.
        
        Race Condition Prevention:
            Uses DB-level WHERE job_result = 'PENDING' to atomically claim.
            Only one caller can successfully flip PENDING -> PROCESSING.
        
        Args:
            job_id: Job ID to activate
            
        Returns:
            ActivateResult with activated flag and optional break_off_time
        """
        # Check worker availability FIRST
        active_count = self._get_active_worker_count()
        if active_count >= self._max_workers:
            logger.info(
                f"Workers full ({active_count}/{self._max_workers}), "
                f"returning break_off_time={self._break_off_time}s"
            )
            return ActivateResult(
                activated=False,
                reason="workers_full",
                worker_break_off_time=self._break_off_time
            )
        
        # Atomic claim: UPDATE WHERE job_result = 'PENDING'
        db_gen = get_db()
        try:
            db = next(db_gen)
            now = datetime.utcnow()
            
            result = db.execute(
                update(Job)
                .where(Job.job_id == job_id, Job.job_result == JobStatus.PENDING.value)
                .values(
                    job_result=JobStatus.PROCESSING.value,
                    job_actived=True,
                    updated_at=now
                )
            )
            db.commit()
            
            if result.rowcount == 0:
                # Another process already claimed it or status changed
                logger.warning(f"Job {job_id} already claimed or not PENDING")
                return ActivateResult(activated=False, reason="already_claimed")
            
            # Load job data for context
            job = db.query(Job).filter(Job.job_id == job_id).first()
            if not job:
                return ActivateResult(activated=False, reason="job_not_found")
            
            # Load metadata for task parameters
            metadata_record = db.query(Metadatas).filter(
                Metadatas.metadata_of == job_id
            ).first()
            
            job_metadata = {}
            if metadata_record and metadata_record.metadata_json:
                job_metadata = dict(metadata_record.metadata_json)
            
            # Get task function from registry
            from src.services.task_registry import task_registry
            task_func = task_registry.get(job.job_type)
            if not task_func:
                # No registered handler - mark as failed
                logger.error(f"No task registered for job_type: {job.job_type}")
                self._update_status(job_id, JobStatus.FAILED, {
                    "error": f"No task handler registered for job_type: {job.job_type}"
                })
                return ActivateResult(activated=False, reason="no_task_handler")
            
            # Create in-memory context
            context = JobContext(
                job_id=job_id,
                user_id=job.created_by,
                metadata=job_metadata,
                _service=self
            )
            
            with self._job_lock:
                self._jobs[job_id] = context
            
            # Update metadata with activation info
            self._update_metadata_status(db, job_id, JobStatus.PROCESSING, {
                "activated_at": now.isoformat()
            })
            db.commit()
            
            # Submit to thread pool
            if asyncio.iscoroutinefunction(task_func):
                future = self._executor.submit(
                    self._run_async_task, job_id, task_func, context
                )
            else:
                future = self._executor.submit(
                    self._run_sync_task, job_id, task_func, context
                )
            
            with self._job_lock:
                self._futures[job_id] = future
            
            logger.info(f"Job {job_id} activated and submitted to pool")
            return ActivateResult(activated=True)
            
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass
    
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
        self._cleanup_future(job_id)
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
        self._cleanup_future(job_id)
        logger.error(f"Job {job_id} failed: {error}")
    
    def _on_job_interrupted(self, job_id: UUID, reason: str) -> None:
        """Handle job interruption"""
        metadata = {
            "interrupted_at": datetime.utcnow().isoformat(),
            "interrupt_reason": reason
        }
        self._update_status(job_id, JobStatus.INTERRUPTED, metadata)
        self._trigger_callbacks(job_id, JobStatus.INTERRUPTED, reason)
        self._cleanup_future(job_id)
        logger.warning(f"Job {job_id} interrupted: {reason}")
    
    def _cleanup_future(self, job_id: UUID) -> None:
        """Remove completed future from tracking"""
        with self._job_lock:
            self._futures.pop(job_id, None)
    
    # =========================================================================
    # Job Control
    # =========================================================================
    
    def interrupt_job(self, job_id: UUID, reason: str = "User requested") -> bool:
        """
        Interrupt a running job.
        Sets the interrupted flag so the task can check and stop gracefully.
        
        Args:
            job_id: Job ID to interrupt
            reason: Reason for interruption
            
        Returns:
            True if job was marked for interruption
        """
        context = self._get_context(job_id)
        if not context:
            return False
        
        context._interrupted = True
        
        self._update_status(job_id, JobStatus.INTERRUPTED, {
            "interrupt_reason": reason,
            "interrupted_at": datetime.utcnow().isoformat()
        })
        
        logger.info(f"Job {job_id} marked for interruption: {reason}")
        return True
    
    def cancel_job(self, job_id: UUID) -> bool:
        """
        Cancel a pending job (before it starts).
        Uses atomic DB update so only PENDING jobs can be cancelled.
        
        Args:
            job_id: Job ID to cancel
            
        Returns:
            True if job was cancelled
        """
        db_gen = get_db()
        try:
            db = next(db_gen)
            now = datetime.utcnow()
            
            result = db.execute(
                update(Job)
                .where(Job.job_id == job_id, Job.job_result == JobStatus.PENDING.value)
                .values(
                    job_result=JobStatus.CANCELLED.value,
                    job_end_time=now,
                    updated_at=now
                )
            )
            db.commit()
            
            if result.rowcount == 0:
                return False
            
            # Clean up in-memory state if exists
            with self._job_lock:
                self._jobs.pop(job_id, None)
                if job_id in self._futures:
                    self._futures[job_id].cancel()
                    del self._futures[job_id]
            
            logger.info(f"Job {job_id} cancelled")
            return True
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass
    
    # =========================================================================
    # Worker Pool Info
    # =========================================================================
    
    def _get_active_worker_count(self) -> int:
        """Count currently running (not done) futures"""
        with self._job_lock:
            return sum(1 for f in self._futures.values() if not f.done())
    
    def has_available_workers(self) -> bool:
        """Check if there are available worker slots"""
        return self._get_active_worker_count() < self._max_workers
    
    def get_pool_status(self) -> Dict[str, Any]:
        """Get thread pool status info"""
        active = self._get_active_worker_count()
        return {
            "max_workers": self._max_workers,
            "active_workers": active,
            "available_workers": self._max_workers - active,
            "break_off_time": self._break_off_time,
            "tracked_jobs": len(self._jobs),
            "tracked_futures": len(self._futures)
        }
    
    # =========================================================================
    # Status & Progress
    # =========================================================================
    
    def get_job_status(self, job_id: UUID) -> Optional[JobStatus]:
        """Get current job status from database."""
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
        """Get full job information including metadata and progress."""
        db_gen = get_db()
        try:
            db = next(db_gen)
            job = db.query(Job).filter(Job.job_id == job_id).first()
            if not job:
                return None
            
            metadata = db.query(Metadatas).filter(
                Metadatas.metadata_of == job_id
            ).first()
            
            context = self._get_context(job_id)
            
            return {
                "job_id": str(job.job_id),
                "job_type": job.job_type,
                "status": job.job_result,
                "job_start_time": job.job_start_time.isoformat() if job.job_start_time else None,
                "job_end_time": job.job_end_time.isoformat() if job.job_end_time else None,
                "job_actived": job.job_actived,
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
        """Get all active (PENDING or PROCESSING) jobs."""
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
                    "job_type": job.job_type,
                    "status": job.job_result,
                    "job_start_time": job.job_start_time.isoformat() if job.job_start_time else None,
                    "job_actived": job.job_actived,
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
        """Add a callback to be called when job completes."""
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
        timestamp: datetime,
        job_type: Optional[str] = None,
        job_start_time: Optional[datetime] = None
    ) -> None:
        """Persist job to database"""
        job = Job(
            job_id=job_id,
            job_type=job_type,
            job_start_time=job_start_time or (timestamp + timedelta(minutes=1)),
            job_end_time=None,
            job_actived=False,
            job_result=status.value,
            created_at=timestamp,
            created_by=user_id,
            updated_at=timestamp,
            updated_by=user_id
        )
        db.add(job)
        
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
            
            job = db.query(Job).filter(Job.job_id == job_id).first()
            if job:
                job.job_result = status.value
                job.updated_at = now
                
                if status == JobStatus.PROCESSING:
                    job.job_actived = True
                
                terminal_statuses = [
                    JobStatus.SUCCESS, JobStatus.FAILED,
                    JobStatus.INTERRUPTED, JobStatus.CANCELLED
                ]
                if status in terminal_statuses:
                    job.job_end_time = now
            
            # Update metadata
            self._update_metadata_status(db, job_id, status, metadata_update)
            
            db.commit()
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass
    
    def _update_metadata_status(
        self,
        db: Session,
        job_id: UUID,
        status: JobStatus,
        metadata_update: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update metadata record with status info (does NOT commit)"""
        now = datetime.utcnow()
        metadata = db.query(Metadatas).filter(
            Metadatas.metadata_of == job_id
        ).first()
        
        if metadata:
            current = metadata.metadata_json or {}
            
            if "status_history" not in current:
                current["status_history"] = []
            
            current["status_history"].append({
                "status": status.value,
                "timestamp": now.isoformat(),
                "data": metadata_update
            })
            
            if metadata_update:
                current.update(metadata_update)
            
            current["current_status"] = status.value
            current["last_updated"] = now.isoformat()
            
            metadata.metadata_json = current
            metadata.updated_at = now
        elif metadata_update:
            context = self._get_context(job_id)
            user_id = context.user_id if context else None
            
            if user_id is None:
                job = db.query(Job).filter(Job.job_id == job_id).first()
                user_id = job.created_by if job else None
            
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
    
    # =========================================================================
    # Orphan Recovery (on startup)
    # =========================================================================
    
    def recover_orphaned_jobs(self) -> int:
        """
        Reset PROCESSING jobs back to PENDING on startup.
        
        These are jobs that were running when the server crashed.
        The daemon will pick them up again.
        
        Returns:
            Number of recovered jobs
        """
        db_gen = get_db()
        try:
            db = next(db_gen)
            now = datetime.utcnow()
            
            result = db.execute(
                update(Job)
                .where(Job.job_result == JobStatus.PROCESSING.value)
                .values(
                    job_result=JobStatus.PENDING.value,
                    job_actived=False,
                    updated_at=now
                )
            )
            db.commit()
            
            count = result.rowcount
            if count > 0:
                logger.warning(f"Recovered {count} orphaned PROCESSING jobs back to PENDING")
            return count
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
        """Clean up completed job contexts from memory."""
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
                self._futures.pop(job_id, None)
                self._callbacks.pop(job_id, None)
                cleaned += 1
        
        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} completed jobs from memory")
        return cleaned
    
    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the job service."""
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
    job_type: str,
    metadata: Optional[Dict[str, Any]] = None,
    job_start_time: Optional[datetime] = None,
    db: Optional[Session] = None
) -> UUID:
    """
    Convenience function to register a background job.
    Job will be picked up by the daemon when ready.
    """
    return await job_service.register_job(
        user_id=user_id,
        job_type=job_type,
        metadata=metadata,
        job_start_time=job_start_time,
        db=db
    )


def get_job_status(job_id: UUID) -> Optional[JobStatus]:
    """Get job status by ID"""
    return job_service.get_job_status(job_id)


def interrupt_job(job_id: UUID, reason: str = "User requested") -> bool:
    """Interrupt a running job"""
    return job_service.interrupt_job(job_id, reason)
