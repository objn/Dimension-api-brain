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
        conversation = repo.find_one_by_id(conversation_id)

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )

        result = ConversationWithMessagesResponse(
            conversation_id=conversation.conversation_id,
            conversation_topic=conversation.conversation_topic,
            created_at=conversation.created_at,
            created_by=conversation.created_by,
            updated_at=conversation.updated_at,
            updated_by=conversation.updated_by,
            messages=[MessageResponse.model_validate(msg) for msg in conversation.messages]
        )
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

@router.patch(
    "/{conversation_id}",
    status_code=status.HTTP_200_OK,
    summary="Update a conversation",
    description="Update a conversation by its ID using ORM"
)
async def rename_conversation(
    conversation_id: UUID,
    request: ConversationUpdateRequest,
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """Rename a conversation - uses ORM query"""
    try:
        repo = ConversationRepository(db)
        conversation = repo.find_one_by_id(conversation_id)

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )

        conversation.conversation_topic = request.conversation_topic
        conversation.updated_by = current_user_id
        conversation.updated_at = datetime.utcnow()

        updated_conversation = repo.update_by_id(conversation_id, {
            "conversation_topic": conversation.conversation_topic,
            "updated_by": conversation.updated_by,
            "updated_at": conversation.updated_at
        })

        result = ConversationResponse.model_validate(updated_conversation)
        return success_response(result.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating conversation: {str(e)}"
        )

@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a conversation",
    description="Delete a conversation by its ID using ORM"
)
async def delete_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete a conversation - uses ORM query"""
    try:
        repo = ConversationRepository(db)
        conversation = repo.find_one_by_id(conversation_id)

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )

        repo.delete_by_id(conversation.conversation_id)
        return success_response({"message": "Conversation deleted successfully"})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting conversation: {str(e)}"
        )
    
@router.post(
    "/messages",
    status_code=status.HTTP_201_CREATED,
    summary="Add a message to a conversation",
    description="Add a new message to a conversation using ORM"
)
async def add_message_to_conversation(
    request: MessageCreateRequest,
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """Add a message to a conversation - uses ORM query"""
    try:
        convo_repo = ConversationRepository(db)
        conversation = convo_repo.find_one_by_id(request.conversation_id)

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )

        new_message = Messages(
            message_id=uuid4(), 
            conversation_id=request.conversation_id,
            message_content=request.message_content,
            sender_role=request.sender_role,
            created_by=current_user_id,
            created_at=datetime.utcnow(),
            updated_by=current_user_id,
            updated_at=datetime.utcnow()
        )

        message_repo = convo_repo.get_message_repository()
        created_message = message_repo.create(new_message)
        result = MessageResponse.model_validate(created_message)

        
        return success_response(result.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error adding message: {str(e)}"
        )