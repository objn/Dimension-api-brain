"""
DTOs for Conversation and Message operations.
Request and response models with validation.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID


class ConversationCreateRequest(BaseModel):
    """Request body for creating a conversation"""
    message: str = Field(..., min_length=1, max_length=255, description="Conversation topic")

    class Config:
        json_schema_extra = {
            "example": {
                "conversation_topic": "how are you today?"
            }
        }


class ConversationUpdateRequest(BaseModel):
    """Request body for updating a conversation"""
    conversation_topic: Optional[str] = Field(None, min_length=1, max_length=255, description="Conversation topic")

    class Config:
        json_schema_extra = {
            "example": {
                "conversation_topic": "Updated AI Research Discussion"
            }
        }


class ConversationResponse(BaseModel):
    """Response model for conversation data"""
    conversation_id: UUID
    conversation_topic: Optional[str]
    created_at: Optional[datetime]
    created_by: Optional[UUID]
    updated_at: Optional[datetime]
    updated_by: Optional[UUID]

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                "conversation_topic": "AI Research Discussion",
                "created_at": "2026-02-01T12:00:00Z",
                "created_by": "123e4567-e89b-12d3-a456-426614174001",
                "updated_at": "2026-02-01T12:00:00Z",
                "updated_by": "123e4567-e89b-12d3-a456-426614174001"
            }
        }


class ConversationListResponse(BaseModel):
    """Response model for list of conversations"""
    count: int
    conversations: list[ConversationResponse]

    class Config:
        json_schema_extra = {
            "example": {
                "count": 2,
                "conversations": [
                    {
                        "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                        "conversation_topic": "AI Research Discussion",
                        "created_at": "2026-02-01T12:00:00Z"
                    }
                ]
            }
        }


class MessageCreateRequest(BaseModel):
    """Request body for creating a message"""
    conversation_id: UUID = Field(..., description="ID of the conversation")
    message_content: str = Field(..., min_length=1, description="Message content")
    sender_role: str = Field(..., max_length=16, description="Role of the sender (user/assistant/system)")

    class Config:
        json_schema_extra = {
            "example": {
                "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                "message_content": "Hello, how can I help you today?",
                "sender_role": "assistant"
            }
        }


class MessageUpdateRequest(BaseModel):
    """Request body for updating a message"""
    message_content: Optional[str] = Field(None, min_length=1, description="Message content")

    class Config:
        json_schema_extra = {
            "example": {
                "message_content": "Updated message content"
            }
        }


class MessageResponse(BaseModel):
    """Response model for message data"""
    message_id: UUID
    conversation_id: Optional[UUID]
    message_content: Optional[str]
    sender_role: Optional[str]
    created_at: Optional[datetime]
    created_by: Optional[UUID]
    updated_at: Optional[datetime]
    updated_by: Optional[UUID]

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "message_id": "123e4567-e89b-12d3-a456-426614174002",
                "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                "message_content": "Hello, how can I help you today?",
                "sender_role": "assistant",
                "created_at": "2026-02-01T12:00:00Z",
                "created_by": "123e4567-e89b-12d3-a456-426614174001",
                "updated_at": "2026-02-01T12:00:00Z",
                "updated_by": "123e4567-e89b-12d3-a456-426614174001"
            }
        }


class MessageListResponse(BaseModel):
    """Response model for list of messages"""
    count: int
    messages: list[MessageResponse]

    class Config:
        json_schema_extra = {
            "example": {
                "count": 5,
                "messages": [
                    {
                        "message_id": "123e4567-e89b-12d3-a456-426614174002",
                        "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                        "message_content": "Hello!",
                        "sender_role": "user",
                        "created_at": "2026-02-01T12:00:00Z"
                    }
                ]
            }
        }


class ConversationWithMessagesResponse(BaseModel):
    """Response model for conversation with its messages"""
    conversation: ConversationResponse
    messages: list[MessageResponse]

    class Config:
        json_schema_extra = {
            "example": {
                "conversation": {
                    "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                    "conversation_topic": "AI Research Discussion",
                    "created_at": "2026-02-01T12:00:00Z"
                },
                "messages": [
                    {
                        "message_id": "123e4567-e89b-12d3-a456-426614174002",
                        "message_content": "Hello!",
                        "sender_role": "user",
                        "created_at": "2026-02-01T12:00:00Z"
                    }
                ]
            }
        }
