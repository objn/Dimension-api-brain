"""
Metadata repository with custom query methods.
Extends BaseRepository for metadata-specific operations.
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from uuid import UUID

from .base_repository import BaseRepository
from src.database.models import Metadatas


class MetadataRepository(BaseRepository[Metadatas]):
    """
    Metadata repository with custom methods.
    Similar to TypeORM's custom repository.
    """

    def __init__(self, db: Session):
        super().__init__(Metadatas, db)

    def find_by_creator(self, user_id: UUID) -> List[Metadatas]:
        """Find all metadatas created by a specific user"""
        return self.find_by(created_by=user_id)

    def find_by_metadata_of(self, metadata_of: UUID) -> List[Metadatas]:
        """Find all metadatas for a specific entity"""
        return self.find_by(metadata_of=metadata_of)

    def find_by_creator_and_metadata_of(self, user_id: UUID, metadata_of: UUID) -> List[Metadatas]:
        """Find all metadatas for a specific entity created by a user"""
        return self.db.query(Metadatas).filter(
            Metadatas.created_by == user_id,
            Metadatas.metadata_of == metadata_of
        ).all()

    def find_recent_by_creator(self, user_id: UUID, limit: int = 10) -> List[Metadatas]:
        """Find most recently created metadatas by a specific user"""
        return self.db.query(Metadatas).filter(
            Metadatas.created_by == user_id
        ).order_by(
            Metadatas.created_at.desc()
        ).limit(limit).all()
