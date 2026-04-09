"""
NodeVector repository for NodeVector table.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from src.database.models import Nodevector


class NodevectorRepository:
    """Repository for NodeVector entity (composite primary key)."""

    def __init__(self, db: Session):
        self.db = db

    def find_one_by_composite_id(self, node_id: UUID, chunk_id: UUID) -> Optional[Nodevector]:
        return (
            self.db.query(Nodevector)
            .filter(Nodevector.node_id == node_id)
            .filter(Nodevector.node_vector_chunk_id == chunk_id)
            .filter(Nodevector.deleted_at.is_(None))
            .first()
        )

