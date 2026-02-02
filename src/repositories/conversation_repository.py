"""
Agent repository with custom query methods.
Extends BaseRepository for agent-specific operations.
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from uuid import UUID

from .base_repository import BaseRepository
from src.database.models import Conversations, Messages


class ConversationRepository(BaseRepository[Conversations]):
    """
    Conversation repository with custom methods.
    Similar to TypeORM's custom repository.
    """

    def __init__(self, db: Session):
        super().__init__(Conversations, db)
    
    def find_by_topic(self, topic: str) -> Optional[Conversations]:
        """Find conversation by exact topic"""
        return self.db.query(Conversations).filter(
            Conversations.conversation_topic.ilike(f"{topic}")
        ).all()


    def find_by_creator(self, user_id: UUID) -> List[Conversations]:
        """Find all conversations created by a specific user"""
        return self.find_by(created_by=user_id)