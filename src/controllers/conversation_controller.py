"""
Conversation CRUD controller.
All operations use ORM - no raw SQL queries.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime

from src.database import get_db
from src.repositories.conversation_repository import ConversationRepository
from src.database.models import Conversations, Messages
from src.dto.conversation_dto import (
    ConversationCreateRequest,
    ConversationUpdateRequest,
    ConversationResponse,
    ConversationListResponse,
    MessageCreateRequest,
    MessageUpdateRequest,
    MessageResponse,
    MessageListResponse,
    ConversationWithMessagesResponse
)
from src.dto.response_dto import success_response, error_response
from src.utils.auth import get_current_user_id

import src.services.openai_api as LLM

router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"]
)


@router.get(
    "/",
    status_code=status.HTTP_200_OK,
    summary="Get all conversations",
    description="Retrieve all conversations using ORM"
)
async def get_all_conversations(
    limit: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get all conversations - uses ORM query"""
    try:
        repo = ConversationRepository(db)

        if limit:
            conversations = repo.find_recent(limit=limit)
        else:
            conversations = repo.find_all()

        result = ConversationListResponse(
            count=len(conversations),
            conversations=[ConversationResponse.model_validate(conversation) for conversation in conversations]
        )
        return success_response(result.model_dump())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching conversations: {str(e)}"
        )
    
@router.get(
    "/{conversation_id}",
    status_code=status.HTTP_200_OK,
    summary="Get conversation by ID",
    description="Retrieve a conversation by its ID using ORM"
)
async def get_conversation_by_id(
    conversation_id: UUID,
    db: Session = Depends(get_db)
):
    """Get conversation by ID - uses ORM query"""
    try:
        repo = ConversationRepository(db)
        conversation = repo.find_by_id(conversation_id)

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )

        result = ConversationWithMessagesResponse.model_validate(conversation)
        return success_response(result.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching conversation: {str(e)}"
        )
    
@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation",
    description="Create a new conversation using ORM"
)
async def create_conversation(
    request: ConversationCreateRequest,
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """Create a new conversation - uses ORM query"""
    try:
        resinput = LLM.OpenAIService().topic_by_firstmessage(request.message)
        # Ensure topic is properly encoded string
        topic = str(resinput) if resinput else "New Conversation"
        repo = ConversationRepository(db)
        new_conversation = Conversations(
            conversation_id=uuid4(),
            conversation_topic=topic,
            created_by=current_user_id,
            created_at=datetime.utcnow(),
            updated_by=current_user_id,
            updated_at=datetime.utcnow()
        )
        created_conversation = repo.create(new_conversation)

        result = ConversationResponse.model_validate(created_conversation)
        return success_response(result.model_dump())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating conversation: {str(e)}"
        )