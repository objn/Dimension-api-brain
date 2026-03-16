"""
DTOs for Conversation and Message operations.
Request and response models with validation.

Sender Roles (per AI Agent Operating Instructions):
- SYSTEM: System notices, errors, policies, or hidden context
- USER: Human user input
- AGENT: AI agent natural language responses
- TOOL: Outputs from tools, APIs, or function calls
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal, List
from datetime import datetime
from uuid import UUID
from enum import Enum

from .base_dto import BaseResponseModel


# Supported LLM providers
LLMProviderType = Literal["openai", "gemini", "anthropic"]


class SenderRole(str, Enum):
    """
    Message sender roles per AI Agent Operating Instructions.
    Messages must correctly assign sender_role.
    """
    SYSTEM = "SYSTEM"   # System notices, errors, policies, hidden context
    USER = "USER"       # Human user input
    AGENT = "AGENT"     # AI agent natural language responses  
    TOOL = "TOOL"       # Outputs from tools, APIs, or function calls


# Type alias for role literals
SenderRoleType = Literal["SYSTEM", "USER", "AGENT", "TOOL"]


class ConversationCreateRequest(BaseModel):
    """Request body for creating a conversation"""
    message_content: str = Field(..., min_length=1, max_length=255, description="Conversation topic")
    llm_provider: Optional[LLMProviderType] = Field(
        default="openai",
        description="LLM provider to use (openai, gemini, anthropic)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "how are you today?",
                "llm_provider": "openai"
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


class ConversationResponse(BaseResponseModel):
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
    """Request body for creating a message (internal use - messages are immutable)"""
    conversation_id: UUID = Field(..., description="ID of the conversation")
    message_content: str = Field(..., min_length=1, description="Message content")
    sender_role: SenderRoleType = Field(..., description="Role: SYSTEM, USER, AGENT, or TOOL")
    llm_provider: Optional[LLMProviderType] = Field(
        default="openai",
        description="LLM provider to use (openai, gemini, anthropic)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                "message_content": "Hello, how can I help you today?",
                "sender_role": "USER",
                "llm_provider": "openai"
            }
        }


class MessageUpdateRequest(BaseModel):
    """Request body for updating a message"""
    message_content: Optional[str] = Field(None, min_length=1, description="Message content")
    llm_provider: Optional[LLMProviderType] = Field(
        default=None,
        description="LLM provider to use (openai, gemini, anthropic)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "message_content": "Updated message content",
                "llm_provider": "openai"
            }
        }


class MessageResponse(BaseResponseModel):
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


class ConversationWithMessagesResponse(BaseResponseModel):
    """Response model for conversation with its messages and statistics"""
    conversation_id: UUID
    conversation_topic: Optional[str]
    created_at: Optional[datetime]
    created_by: Optional[UUID]
    updated_at: Optional[datetime]
    updated_by: Optional[UUID]
    total_messages: int = 0
    messages: list[MessageResponse]

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                "conversation_topic": "AI Research Discussion",
                "created_at": "2026-02-01T12:00:00Z",
                "created_by": "123e4567-e89b-12d3-a456-426614174001",
                "updated_at": "2026-02-01T12:00:00Z",
                "updated_by": "123e4567-e89b-12d3-a456-426614174001",
                "total_messages": 25,
                "role_counts": {"USER": 10, "AGENT": 10, "SYSTEM": 3, "TOOL": 2},
                "messages": [
                    {
                        "message_id": "123e4567-e89b-12d3-a456-426614174002",
                        "message_content": "Hello!",
                        "sender_role": "USER",
                        "created_at": "2026-02-01T12:00:00Z"
                    }
                ]
            }
        }


# ============================================================================
# CHAT DTOs - For AI Agent Operating Instructions
# ============================================================================

class AttachRequest(BaseModel):
    """Node, file, and conversation IDs to attach for retrieval/context in chat."""
    nodes: List[UUID] = Field(
        default_factory=list,
        description="Node IDs to attach for context"
    )
    files: List[UUID] = Field(
        default_factory=list,
        description="File IDs to attach (content parsed and injected)"
    )
    conversations: List[UUID] = Field(
        default_factory=list,
        description="Conversation IDs whose messages will be injected as additional context"
    )


class ChatRequest(BaseModel):
    """
    Request body for sending a chat message to an agent.
    This is the primary entry point for user interaction.
    """
    conversation_id: UUID = Field(..., description="ID of the conversation")
    message_content: str = Field(..., min_length=1, description="User message content")
    agent_id: UUID = Field(..., description="ID of the agent to respond")
    llm_provider: Optional[LLMProviderType] = Field(
        default="openai",
        description="LLM provider to use"
    )
    use_rag: Optional[bool] = Field(
        default=False,
        description="If true, retrieve relevant node chunks and inject into context; response includes citations"
    )
    workspace_id: Optional[UUID] = Field(
        default=None,
        description="When use_rag is true, scope search to this workspace (frontend sends current workspace)"
    )
    attach: Optional[AttachRequest] = Field(
        default_factory=AttachRequest,
        description="Explicit nodes and/or files to attach for context retrieval"
    )
    max_reasoning_loops: Optional[int] = Field(
        default=1,
        ge=1,
        le=10,
        description="Max reasoning steps before answering (1 = no extra reasoning loop; 2+ = model reasons step-by-step up to this many steps)"
    )
    rag_top_k: Optional[int] = Field(
        default=5,
        ge=1,
        le=20,
        description="When use_rag is true: number of top chunks by similarity to retrieve from node_vector (default 5)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                "message_content": "What is machine learning?",
                "agent_id": "123e4567-e89b-12d3-a456-426614174999",
                "llm_provider": "openai",
                "use_rag": False,
                "workspace_id": None,
                "attach": {
                    "nodes": [],
                    "files": [],
                    "conversations": []
                },
                "max_reasoning_loops": 1,
                "rag_top_k": 5
            }
        }


class ToolCallRequest(BaseModel):
    """
    Request body for recording a tool call result.
    Tool outputs are stored as TOOL role messages.
    """
    conversation_id: UUID = Field(..., description="ID of the conversation")
    tool_name: str = Field(..., description="Name of the tool that was called")
    tool_input: Optional[str] = Field(None, description="Input provided to the tool")
    tool_output: str = Field(..., description="Output returned by the tool")

    class Config:
        json_schema_extra = {
            "example": {
                "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                "tool_name": "calculator",
                "tool_input": "2 + 2",
                "tool_output": "4"
            }
        }


class SystemMessageRequest(BaseModel):
    """
    Request body for creating a system message.
    Used for system notices, errors, or policy messages.
    """
    conversation_id: UUID = Field(..., description="ID of the conversation")
    message_content: str = Field(..., description="System message content")
    is_error: Optional[bool] = Field(default=False, description="Whether this is an error message")

    class Config:
        json_schema_extra = {
            "example": {
                "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                "message_content": "Session timeout. Please re-authenticate.",
                "is_error": True
            }
        }


class ChatResponse(BaseModel):
    """
    Response model for chat interactions.
    Contains the agent's response and metadata.
    """
    conversation_id: UUID
    user_message: MessageResponse
    agent_response: MessageResponse
    agent_id: UUID
    agent_name: Optional[str]
    messages_in_context: int = Field(description="Number of messages used as context")
    citations: Optional[List[dict]] = Field(
        default_factory=list,
        description="When use_rag was true: sources (node_id, chunk_id, snippet) used for the response"
    )
    attachments: Optional[dict] = Field(
        default_factory=dict,
        description=(
            "Details about any attached entities used for context. "
            "Structure: {'nodes': [...], 'files': [...], 'conversations': [...]}"
        ),
    )

    class Config:
        json_schema_extra = {
            "example": {
                "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                "user_message": {
                    "message_id": "123e4567-e89b-12d3-a456-426614174002",
                    "message_content": "What is machine learning?",
                    "sender_role": "USER"
                },
                "agent_response": {
                    "message_id": "123e4567-e89b-12d3-a456-426614174003",
                    "message_content": "Machine learning is a subset of AI...",
                    "sender_role": "AGENT"
                },
                "agent_id": "123e4567-e89b-12d3-a456-426614174999",
                "agent_name": "Research Assistant",
                "messages_in_context": 5,
                "citations": [],
                "attachments": {
                    "nodes": [
                        {
                            "node_id": "123e4567-e89b-12d3-a456-426614174100",
                            "node_name": "ML Overview",
                            "node_desc": "High-level machine learning notes"
                        }
                    ],
                    "files": [
                        {
                            "file_id": "123e4567-e89b-12d3-a456-426614174200",
                            "file_name": "ml_notes.pdf",
                            "mime_type": "application/pdf",
                            "file_size": 102400
                        }
                    ],
                    "conversations": [
                        {
                            "conversation_id": "123e4567-e89b-12d3-a456-426614174300",
                            "conversation_topic": "Previous ML discussion"
                        }
                    ]
                }
            }
        }


class ChatPanelRequest(BaseModel):
    """Request for panel chat: one user message, multiple agents respond."""
    conversation_id: UUID = Field(..., description="ID of the conversation")
    message_content: str = Field(..., min_length=1, description="User message content")
    agent_ids: List[UUID] = Field(..., min_length=1, max_length=10, description="IDs of agents that will each respond")
    llm_provider: Optional[LLMProviderType] = Field(default="openai")
    max_history: Optional[int] = Field(default=10, ge=1, le=50)


class AgentPanelResponseItem(BaseModel):
    """Single agent response in panel chat."""
    agent_id: UUID
    agent_name: Optional[str]
    message: MessageResponse


class ChatPanelResponse(BaseModel):
    """Response for panel chat: one user message, multiple agent responses."""
    conversation_id: UUID
    user_message: MessageResponse
    agent_responses: List[AgentPanelResponseItem]


class ChatHistoryResponse(BaseModel):
    """
    Response model for chat history with role-based grouping.
    Provides structured view of conversation timeline.
    """
    conversation_id: UUID
    conversation_topic: Optional[str]
    total_messages: int
    messages: List[MessageResponse]
    role_counts: dict = Field(description="Count of messages by role")

    class Config:
        json_schema_extra = {
            "example": {
                "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                "conversation_topic": "Machine Learning Discussion",
                "total_messages": 10,
                "messages": [],
                "role_counts": {
                    "USER": 4,
                    "AGENT": 4,
                    "SYSTEM": 1,
                    "TOOL": 1
                }
            }
        }


class AgentSearchItem(BaseModel):
    """Minimal agent fields for global search results."""
    agent_id: UUID
    agent_name: Optional[str]
    agent_desc: Optional[str]
    default: Optional[bool] = None


class ChatHistorySearchItem(BaseModel):
    """Minimal conversation/chat history fields for global search results."""
    conversation_id: UUID
    conversation_topic: Optional[str]
    updated_at: Optional[datetime]
    last_message_preview: Optional[str] = None


class GlobalSearchResponse(BaseModel):
    """Combined exact-search results for agents and chat history."""
    query: str
    agents: List[AgentSearchItem]
    conversations: List[ChatHistorySearchItem]
