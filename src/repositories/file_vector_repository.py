"""
Repository for FileVector table (conversation-scoped file chunks).
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from src.database.models import Filevector


class FileVectorRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_one_by_composite_id(
        self, conversation_id: UUID, chunk_id: UUID
    ) -> Optional[Filevector]:
        """Single chunk row by (conversation_id, file_vector_chunk_id)."""
        return (
            self.db.query(Filevector)
            .filter(Filevector.conversation_id == conversation_id)
            .filter(Filevector.file_vector_chunk_id == chunk_id)
            .filter(Filevector.deleted_at.is_(None))
            .first()
        )

    def soft_delete_by_conversation_and_file(
        self,
        conversation_id: UUID,
        file_id: UUID,
        updated_by: UUID,
    ) -> int:
        """Set deleted_at on all active chunks for this conversation + file. Returns rowcount."""
        now = datetime.utcnow()
        q = (
            self.db.query(Filevector)
            .filter(Filevector.conversation_id == conversation_id)
            .filter(Filevector.file_id == file_id)
            .filter(Filevector.deleted_at.is_(None))
        )
        count = 0
        for row in q.all():
            row.deleted_at = now
            row.updated_at = now
            row.updated_by = updated_by
            count += 1
        if count:
            self.db.commit()
        return count

    def bulk_create(self, rows: List[Filevector]) -> None:
        for r in rows:
            self.db.add(r)
        self.db.commit()
