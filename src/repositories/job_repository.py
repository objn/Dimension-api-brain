"""
Job repository with custom query methods.
Extends BaseRepository for job-specific operations.
"""
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from uuid import UUID

from .base_repository import BaseRepository
from src.database.models import Job, Metadatas


class JobRepository(BaseRepository[Job]):
    """
    Job repository with custom methods.
    Similar to TypeORM's custom repository.
    """

    def __init__(self, db: Session):
        super().__init__(Job, db)

    def find_by_creator(self, user_id: UUID) -> List[Job]:
        """Find all jobs created by a specific user"""
        return self.find_by(created_by=user_id)

    def find_by_creator_with_metadata(self, user_id: UUID) -> List[Tuple[Job, Optional[Metadatas]]]:
        """Find all jobs created by a specific user with their metadata"""
        return self.db.query(Job, Metadatas).outerjoin(
            Metadatas,
            Metadatas.metadata_of == Job.job_id
        ).filter(
            Job.created_by == user_id
        ).all()

    def find_one_by_id_with_metadata(self, job_id: UUID) -> Optional[Tuple[Job, Optional[Metadatas]]]:
        """Find one job by ID with its metadata"""
        result = self.db.query(Job, Metadatas).outerjoin(
            Metadatas,
            Metadatas.metadata_of == Job.job_id
        ).filter(
            Job.job_id == job_id
        ).first()
        return result

    def find_by_status(self, status: str, user_id: UUID) -> List[Job]:
        """Find all jobs with a specific status for a user"""
        return self.db.query(Job).filter(
            Job.job_result == status,
            Job.created_by == user_id
        ).all()

    def find_recent(self, user_id: UUID, limit: int = 10) -> List[Job]:
        """Find most recently created jobs for a user"""
        return self.db.query(Job).filter(
            Job.created_by == user_id
        ).order_by(
            Job.created_at.desc()
        ).limit(limit).all()

    def find_pending_jobs(self, user_id: UUID) -> List[Job]:
        """Find all pending jobs for a user"""
        return self.find_by_status("PENDING", user_id)

    def find_running_jobs(self, user_id: UUID) -> List[Job]:
        """Find all running/processing jobs for a user"""
        return self.db.query(Job).filter(
            Job.job_result.in_(["PROCESSING", "RUNNING"]),
            Job.created_by == user_id
        ).all()

    def find_stoppable_jobs(self, user_id: UUID) -> List[Job]:
        """Find all jobs that can be stopped (PENDING or PROCESSING)"""
        return self.db.query(Job).filter(
            Job.job_result.in_(["PENDING", "PROCESSING", "RUNNING"]),
            Job.created_by == user_id
        ).all()
