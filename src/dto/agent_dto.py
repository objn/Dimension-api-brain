"""
DTOs for Agent operations.
Request and response models with validation.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID

from .base_dto import BaseResponseModel


class AgentCreateRequest(BaseModel):
    """Request body for creating an agent"""
    agent_name: str = Field(..., min_length=1, max_length=255, description="Agent name")
    agent_desc: Optional[str] = Field(None, description="Agent description")
    agent_prompt: Optional[str] = Field(None, description="Agent system prompt")
    agent_profile_image: Optional[UUID] = Field(None, description="Profile image file ID")

    class Config:
        json_schema_extra = {
            "example": {
                "agent_name": "Research Assistant",
                "agent_desc": "AI assistant specialized in research and analysis",
                "agent_prompt": "You are a helpful research assistant...",
                "agent_profile_image": None
            }
        }


class AgentUpdateRequest(BaseModel):
    """Request body for updating an agent"""
    agent_name: Optional[str] = Field(None, min_length=1, max_length=255, description="Agent name")
    agent_desc: Optional[str] = Field(None, description="Agent description")
    agent_prompt: Optional[str] = Field(None, description="Agent system prompt")
    agent_profile_image: Optional[UUID] = Field(None, description="Profile image file ID")

    class Config:
        json_schema_extra = {
            "example": {
                "agent_name": "Updated Research Assistant",
                "agent_desc": "Updated description",
                "agent_prompt": "Updated system prompt"
            }
        }


class AgentResponse(BaseResponseModel):
    """Response model for agent data"""
    agent_id: UUID
    agent_name: Optional[str]
    agent_desc: Optional[str]
    agent_prompt: Optional[str]
    agent_profile_image: Optional[UUID]
    created_at: Optional[datetime]
    created_by: Optional[UUID]
    updated_at: Optional[datetime]
    updated_by: Optional[UUID]

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "agent_id": "123e4567-e89b-12d3-a456-426614174000",
                "agent_name": "Research Assistant",
                "agent_desc": "AI assistant for research",
                "agent_prompt": "You are a helpful assistant...",
                "agent_profile_image": None,
                "created_at": "2026-01-31T12:00:00Z",
                "created_by": "123e4567-e89b-12d3-a456-426614174001",
                "updated_at": "2026-01-31T12:00:00Z",
                "updated_by": "123e4567-e89b-12d3-a456-426614174001"
            }
        }


class AgentListResponse(BaseModel):
    """Response model for list of agents"""
    count: int
    agents: list[AgentResponse]

    class Config:
        json_schema_extra = {
            "example": {
                "count": 2,
                "agents": [
                    {
                        "agent_id": "123e4567-e89b-12d3-a456-426614174000",
                        "agent_name": "Research Assistant",
                        "agent_desc": "AI assistant for research",
                        "created_at": "2026-01-31T12:00:00Z"
                    }
                ]
            }
        }
