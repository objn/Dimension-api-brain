"""
Agent repository with custom query methods.
Extends BaseRepository for agent-specific operations.
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from uuid import UUID

from .base_repository import BaseRepository
from src.database.models import Conversations, Messages


class MessageRepository(BaseRepository[Messages]):
    """
    Message repository with custom methods.
    """

    def __init__(self, db: Session):
        super().__init__(Messages, db)

    def find_by_conversation(self, conversation_id: UUID) -> List[Messages]:
        """Find all messages for a specific conversation"""
        return self.find_by(conversation_id=conversation_id)


class ConversationRepository(BaseRepository[Conversations]):
    """
    Conversation repository with custom methods.
    Similar to TypeORM's custom repository.
    """

    def __init__(self, db: Session):
        super().__init__(Conversations, db)

    def get_message_repository(self) -> MessageRepository:
        """Get the message repository for this conversation"""
        return MessageRepository(self.db)
    
    def find_all_sorted(self, sort_by: str = "updated_at", sort_order: str = "desc", limit: Optional[int] = None) -> List[Conversations]:
        """Find all conversations with sorting"""
        query = self.db.query(Conversations)
        
        # Get the column to sort by
        if hasattr(Conversations, sort_by):
            column = getattr(Conversations, sort_by)
            if sort_order.lower() == "asc":
                query = query.order_by(column.asc())
            else:
                query = query.order_by(column.desc())
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def find_by_topic(self, topic: str) -> Optional[Conversations]:
        """Find conversation by exact topic"""
        return self.db.query(Conversations).filter(
            Conversations.conversation_topic.ilike(f"{topic}")
        ).all()


    def find_by_creator(self, user_id: UUID) -> List[Conversations]:
        """Find all conversations created by a specific user"""
        return self.find_by(created_by=user_id)