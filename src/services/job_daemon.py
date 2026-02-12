"""
Job Daemon - Lightweight background poller that signals JobService.

Design Principles:
    - SIGNAL-ONLY: Only checks if PENDING jobs exist, never reads details or writes
    - Sends a signal to JobService when ready jobs are detected
    - JobService handles finding, deduplicating, and activating jobs
    - Respects worker_break_off_time when pool is full
    - Runs in a daemon thread, polls at JOB_POLL_INTERVAL

Flow:
    1. Poll DB: EXISTS any PENDING job where job_start_time <= NOW()?
    2. If yes, call job_service.process_ready_jobs()
    3. If response.worker_break_off_time > 0, sleep that duration
    4. Otherwise sleep JOB_POLL_INTERVAL and repeat
"""
import threading
import time
import logging
from datetime import datetime

from sqlalchemy import func

from src.database.models import Job
from src.database import get_silent_db
from src.config.settings import settings

logger = logging.getLogger(__name__)


class JobDaemon:
    """
    Background daemon that signals JobService when ready jobs exist.
    
    SIGNAL-ONLY: This daemon only checks for existence of ready jobs.
    All querying, deduplication, and activation go through JobService.
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
        self._total_signals_sent: int = 0
        
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
            "total_signals_sent": self._total_signals_sent,
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
        Single poll iteration: check if ready jobs exist, signal JobService.
        
        Only checks existence (COUNT/EXISTS), does NOT read job details.
        
        Returns:
            worker_break_off_time if workers are full, 0 otherwise
        """
        from src.services.job_service import job_service
        
        self._last_poll_at = datetime.utcnow()
        self._total_polls += 1
        
        has_ready = self._has_ready_jobs()
        
        if not has_ready:
            return 0
        
        if self._verbose:
            logger.info("Detected ready job(s), signaling JobService")
        
        self._total_signals_sent += 1
        
        # Signal JobService to handle everything: find, dedup, activate
        result = job_service.process_ready_jobs()
        
        return result.worker_break_off_time
    
    def _has_ready_jobs(self) -> bool:
        """
        Check if any PENDING jobs are ready to run (lightweight EXISTS query).
        
        Criteria:
            - job_result = 'PENDING'
            - job_start_time <= current_time
            - job_end_time IS NULL
        
        Returns:
            True if at least one ready job exists
        """
        db_gen = get_silent_db()
        try:
            db = next(db_gen)
            now = datetime.utcnow()
            
            count = db.query(func.count(Job.job_id)).filter(
                Job.job_result == "PENDING",
                Job.job_start_time <= now,
                Job.job_end_time.is_(None),
                Job.job_actived == False
            ).scalar()
            
            return count > 0
        except Exception as e:
            logger.error(f"Error checking ready jobs: {e}", exc_info=True)
            return False
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass


# Global singleton
job_daemon = JobDaemon()
