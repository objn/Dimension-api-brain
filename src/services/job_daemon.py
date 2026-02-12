"""
Job Daemon - READ-ONLY background poller for scheduled jobs.

Design Principles:
    - READ-ONLY: Only queries the database, never writes to it
    - Signals JobService to activate jobs (JobService does all DB writes)
    - Respects worker_break_off_time when pool is full
    - Runs in a daemon thread, polls at JOB_POLL_INTERVAL

Query Logic:
    SELECT * FROM Jobs
    WHERE job_result = 'PENDING'
      AND job_start_time <= NOW()
      AND job_end_time IS NULL
    ORDER BY created_at ASC

Flow:
    1. Poll DB for ready jobs (read-only)
    2. For each job, call job_service.activate_job(job_id)
    3. If response.worker_break_off_time > 0, sleep that duration and stop loop
    4. Otherwise continue to next job
    5. Sleep JOB_POLL_INTERVAL and repeat
"""
import threading
import time
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from src.database.models import Job
from src.database import get_silent_db
from src.config.settings import settings

logger = logging.getLogger(__name__)


class JobDaemon:
    """
    Background daemon that polls for ready jobs and signals JobService.
    
    READ-ONLY: This daemon never modifies the database.
    All status changes go through JobService.activate_job().
    """
    
    _instance = None
    
    def __new__(cls) -> 'JobDaemon':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._poll_interval = settings.job_poll_interval
        self._verbose = settings.job_daemon_verbose
        self._running = False
        self._thread: threading.Thread = None
        self._stop_event = threading.Event()
        self._started_at: datetime = None
        self._last_poll_at: datetime = None
        self._total_polls: int = 0
        self._total_jobs_activated: int = 0
        
        if self._verbose:
            logger.info(f"JobDaemon initialized: poll_interval={self._poll_interval}s")
    
    def start(self) -> None:
        """Start the daemon polling thread."""
        if self._running:
            logger.warning("JobDaemon is already running")
            return
        
        self._running = True
        self._stop_event.clear()
        self._started_at = datetime.utcnow()
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="job-daemon",
            daemon=True
        )
        self._thread.start()
        logger.info("JobDaemon started")
    
    def stop(self) -> None:
        """Stop the daemon gracefully."""
        if not self._running:
            return
        
        logger.info("Stopping JobDaemon...")
        self._running = False
        self._stop_event.set()
        self._started_at = None
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        
        logger.info("JobDaemon stopped")
    
    @property
    def is_running(self) -> bool:
        """Check if daemon is currently running."""
        return self._running and self._thread is not None and self._thread.is_alive()
    
    def get_status(self) -> dict:
        """Get daemon status information for debugging."""
        return {
            "running": self.is_running,
            "poll_interval_seconds": self._poll_interval,
            "verbose": self._verbose,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "last_poll_at": self._last_poll_at.isoformat() if self._last_poll_at else None,
            "total_polls": self._total_polls,
            "total_jobs_activated": self._total_jobs_activated,
            "thread_alive": self._thread.is_alive() if self._thread else False
        }
    
    def _poll_loop(self) -> None:
        """Main polling loop - runs in daemon thread."""
        if self._verbose:
            logger.info("JobDaemon poll loop started")
        
        while self._running and not self._stop_event.is_set():
            try:
                break_off = self._poll_once()
                
                if break_off > 0:
                    # Workers are full, wait break_off_time before next poll
                    if self._verbose:
                        logger.info(f"Workers full, sleeping {break_off}s (break_off_time)")
                    self._stop_event.wait(timeout=break_off)
                else:
                    # Normal interval
                    self._stop_event.wait(timeout=self._poll_interval)
                    
            except Exception as e:
                logger.error(f"JobDaemon poll error: {e}", exc_info=True)
                # Sleep before retrying to avoid tight error loops
                self._stop_event.wait(timeout=self._poll_interval)
    
    def _poll_once(self) -> int:
        """
        Single poll iteration: query ready jobs, signal JobService.
        
        READ-ONLY: Only reads from database.
        
        Returns:
            worker_break_off_time if workers are full, 0 otherwise
        """
        # Lazy import to avoid circular dependency
        from src.services.job_service import job_service
        
        self._last_poll_at = datetime.utcnow()
        self._total_polls += 1
        
        ready_jobs = self._find_ready_jobs()
        
        if not ready_jobs:
            return 0
        
        if self._verbose:
            logger.info(f"Found {len(ready_jobs)} ready job(s)")
        
        for job_id in ready_jobs:
            if not self._running:
                break
            
            result = job_service.activate_job(job_id)
            
            if result.worker_break_off_time > 0:
                # Pool is full - stop processing more jobs and return break_off_time
                return result.worker_break_off_time
            
            if result.activated:
                self._total_jobs_activated += 1
                logger.info(f"Job {job_id} activated")
            elif self._verbose:
                logger.debug(f"Job {job_id} not activated: {result.reason}")
        
        return 0
    
    def _find_ready_jobs(self) -> list:
        """
        Query DB for jobs ready to run (READ-ONLY).
        
        Criteria:
            - job_result = 'PENDING'
            - job_start_time <= current_time
            - job_end_time IS NULL
        
        Sorted by created_at ASC (oldest first / FIFO).
        
        Returns:
            List of job_id UUIDs
        """
        db_gen = get_silent_db()
        try:
            db = next(db_gen)
            now = datetime.utcnow()
            
            jobs = db.query(Job.job_id).filter(
                Job.job_result == "PENDING",
                Job.job_start_time <= now,
                Job.job_end_time.is_(None)
            ).order_by(
                Job.created_at.asc()
            ).all()
            
            return [row.job_id for row in jobs]
        except Exception as e:
            logger.error(f"Error querying ready jobs: {e}", exc_info=True)
            return []
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass


# Global singleton
job_daemon = JobDaemon()
