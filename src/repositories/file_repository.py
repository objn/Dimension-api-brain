"""
File repository for Files table.
"""
from typing import List
from uuid import UUID
from sqlalchemy.orm import Session

from src.database.models import Files
from src.repositories.base_repository import BaseRepository


class FileRepository(BaseRepository[Files]):
    """Repository for Files entity."""

    def __init__(self, db: Session):
        super().__init__(Files, db)

    def find_by_created_by(self, created_by: UUID) -> List[Files]:
        """Find all files created by a user."""
        return self.find_by(created_by=created_by)
