"""
Conversation CRUD controller with Chat System.
Implements AI Agent Operating Instructions for multi-role conversations.

Sender Roles:
- SYSTEM: System notices, errors, policies, or hidden context
- USER: Human user input  
- AGENT: AI agent natural language responses
- TOOL: Outputs from tools, APIs, or function calls

Key Principles:
- Messages are immutable (append-only, never edited/deleted)
- Proper role assignment for all messages
- Agent persona via agent_prompt
- Context management with recent messages
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime

from src.database import get_db
from src.repositories.conversation_repository import ConversationRepository
from src.repositories.agent_repository import AgentRepository
from src.config.settings import settings
from src.database.models import Conversations, Messages, Agents
from src.dto.conversation_dto import (
    ConversationCreateRequest,
    ConversationUpdateRequest,
    ConversationResponse,
    ConversationListResponse,
    MessageCreateRequest,
    MessageUpdateRequest,
    MessageResponse,
    MessageListResponse,
    ConversationWithMessagesResponse,
    # Chat DTOs
    AttachRequest,
    ChatRequest,
    ChatResponse,
    ChatPanelRequest,
    ChatPanelResponse,
    ToolCallRequest,
    SystemMessageRequest,
    SenderRole
)
from src.dto.response_dto import success_response, error_response
from src.utils.auth import get_current_user_id
from src.services.chat_service import ChatService

import src.services.llm_router as LLM

router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"]
)


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Get all conversations",
    description="Retrieve all conversations for the current user using ORM"
)
async def get_all_conversations(
    limit: Optional[int] = None,
    sort_by: Optional[str] = "updated_at",
    sort_order: Optional[str] = "desc",
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """Get all conversations for the current user - uses ORM query"""
    try:
        repo = ConversationRepository(db)

        conversations = repo.find_all_sorted(
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            user_id=current_user_id
        )

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
    description="Retrieve a conversation by its ID for the current user using ORM"
)
async def get_conversation_by_id(
    conversation_id: UUID,
    sort_by: Optional[str] = "created_at",
    sort_order: Optional[str] = "asc",
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """Get conversation by ID for the current user - uses ORM query"""
    try:
        repo = ConversationRepository(db)
        conversation = repo.find_one_by_id(conversation_id)

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
        
        # Check ownership
        if conversation.created_by != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this conversation"
            )

        # Sort messages
        messages = list(conversation.messages)
        if hasattr(Messages, sort_by):
            reverse = sort_order.lower() == "desc"
            messages.sort(key=lambda m: getattr(m, sort_by) or datetime.min, reverse=reverse)

        # Calculate role counts
        role_counts = {"USER": 0, "AGENT": 0, "SYSTEM": 0, "TOOL": 0}
        for msg in messages:
            role = msg.sender_role.upper() if isinstance(msg.sender_role, str) else msg.sender_role.value.upper()
            if role in role_counts:
                role_counts[role] += 1

        agent_repo = AgentRepository(db)
        agents_cache: dict[UUID, Agents | None] = {}

        def public_agent_profile_image_url(file_id: UUID) -> str:
            base = (settings.backend_server or "").rstrip("/")
            return f"{base}/files/public/{file_id}"

        message_responses: list[MessageResponse] = []
        for msg in messages:
            role = msg.sender_role.upper() if isinstance(msg.sender_role, str) else msg.sender_role.value.upper()
            msg_resp = MessageResponse.model_validate(msg)

            if role == "AGENT":
                metadatas = msg.metadatas or {}
                md = dict(metadatas) if isinstance(metadatas, dict) else {}
                agent_id_raw = md.get("agent_id")
                if agent_id_raw:
                    try:
                        agent_id = UUID(str(agent_id_raw))
                    except Exception:
                        agent_id = None

                    if agent_id:
                        md["agent_id"] = str(agent_id)
                        if agent_id not in agents_cache:
                            agents_cache[agent_id] = agent_repo.find_one_by_id(agent_id)
                        agent_entity = agents_cache.get(agent_id)

                        if agent_entity and agent_entity.agent_profile_image:
                            md["agent_profile_image"] = public_agent_profile_image_url(
                                agent_entity.agent_profile_image
                            )

                        msg_resp = msg_resp.model_copy(update={"metadatas": md})

            message_responses.append(msg_resp)

        result = ConversationWithMessagesResponse(
            conversation_id=conversation.conversation_id,
            conversation_topic=conversation.conversation_topic,
            created_at=conversation.created_at,
            created_by=conversation.created_by,
            updated_at=conversation.updated_at,
            updated_by=conversation.updated_by,
            total_messages=len(messages),
            messages=message_responses
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
    "",
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
        resinput = LLM.topic_by_firstmessage(request.message_content, request.llm_provider)
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
    description="Update a conversation by its ID using ORM (only owner can update)"
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
        
        # Check ownership
        if conversation.created_by != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this conversation"
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
    description="Delete a conversation by its ID using ORM (only owner can delete)"
)
async def delete_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id)
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
        
        # Check ownership
        if conversation.created_by != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this conversation"
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
    description="Add a new message to a conversation using ORM (only owner can add messages)"
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
        
        # Check ownership
        if conversation.created_by != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to add messages to this conversation"
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


# ============================================================================
# CHAT ENDPOINTS - AI Agent Operating Instructions Implementation
# ============================================================================

@router.post(
    "/chat",
    status_code=status.HTTP_200_OK,
    summary="Send a chat message to an agent",
    description="""
    Primary endpoint for user interaction with an AI agent.
    
    Flow:
    1. User sends a message
    2. Message is stored as USER role (immutable)
    3. Agent processes with conversation context
    4. Agent response is stored as AGENT role (immutable)
    5. Both messages are returned
    
    The agent uses its agent_prompt as system guidance for response generation.
    """
)
async def chat_with_agent(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """
    Send a user message and receive an agent response.
    Implements AI Agent Operating Instructions for message handling.
    """
    try:
        attach = request.attach or AttachRequest()
        chat_service = ChatService(db)
        
        response = chat_service.process_user_message(
            conversation_id=request.conversation_id,
            user_message=request.message_content,
            agent_id=request.agent_id,
            user_id=current_user_id,
            llm_provider=request.llm_provider,
            use_rag=request.use_rag or False,
            workspace_id=request.workspace_id,
            attach={
                "nodes": attach.nodes,
                "files": attach.files,
                "conversations": attach.conversations,
            },
            max_reasoning_loops=request.max_reasoning_loops or 1,
            rag_top_k=request.rag_top_k,
        )
        
        return success_response(response.model_dump())
    
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        # Record error as SYSTEM message
        try:
            chat_service = ChatService(db)
            chat_service.record_system_message(
                conversation_id=request.conversation_id,
                content=f"Failed to process message: {str(e)}",
                user_id=current_user_id,
                is_error=True
            )
        except:
            pass
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing chat: {str(e)}"
        )


@router.post(
    "/chat/panel",
    status_code=status.HTTP_200_OK,
    summary="Panel chat (multiple agents)",
    description="Send one user message and get a response from each of the specified agents.",
)
async def chat_panel(
    request: ChatPanelRequest,
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """One user message, multiple agents respond; returns list of agent responses."""
    try:
        chat_service = ChatService(db)
        response = chat_service.process_panel_message(
            conversation_id=request.conversation_id,
            user_message=request.message_content,
            agent_ids=request.agent_ids,
            user_id=current_user_id,
            llm_provider=request.llm_provider,
            max_history=request.max_history,
        )
        return success_response(response.model_dump())
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing panel chat: {str(e)}"
        )


@router.post(
    "/chat/tool",
    status_code=status.HTTP_201_CREATED,
    summary="Record a tool call result",
    description="""
    Record the output of a tool call in the conversation.
    
    Per AI Agent Operating Instructions:
    - Tool outputs are stored as TOOL role messages
    - This provides context for subsequent agent responses
    
    After recording, call /chat/tool/respond to get the agent's response.
    """
)
async def record_tool_call(
    request: ToolCallRequest,
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """Record a TOOL message in the conversation."""
    try:
        chat_service = ChatService(db)
        
        tool_message = chat_service.record_tool_output(
            conversation_id=request.conversation_id,
            tool_name=request.tool_name,
            tool_output=request.tool_output,
            tool_input=request.tool_input,
            user_id=current_user_id
        )
        
        result = MessageResponse.model_validate(tool_message)
        return success_response(result.model_dump())
    
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error recording tool call: {str(e)}"
        )


@router.post(
    "/chat/tool/respond",
    status_code=status.HTTP_200_OK,
    summary="Generate agent response after tool call",
    description="""
    Generate an AGENT response after a TOOL call has been recorded.
    
    Per AI Agent Operating Instructions:
    - After tool output is stored, use this to generate the final response
    - Agent will use tool output in context to formulate response
    """
)
async def respond_after_tool(
    conversation_id: UUID,
    agent_id: UUID,
    llm_provider: Optional[str] = "openai",
    max_history: Optional[int] = 10,
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """Generate AGENT response using TOOL output in context."""
    try:
        chat_service = ChatService(db)
        
        agent_message = chat_service.respond_after_tool(
            conversation_id=conversation_id,
            agent_id=agent_id,
            user_id=current_user_id,
            llm_provider=llm_provider,
            max_history=max_history
        )
        
        result = MessageResponse.model_validate(agent_message)
        return success_response(result.model_dump())
    
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating response: {str(e)}"
        )


@router.post(
    "/chat/system",
    status_code=status.HTTP_201_CREATED,
    summary="Create a system message",
    description="""
    Create a SYSTEM role message in the conversation.
    
    Per AI Agent Operating Instructions:
    - SYSTEM messages are for notices, errors, policies, or hidden context
    - Set is_error=true for error messages
    """
)
async def create_system_message(
    request: SystemMessageRequest,
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id)
):
    """Create a SYSTEM message in the conversation."""
    try:
        chat_service = ChatService(db)
        
        system_message = chat_service.record_system_message(
            conversation_id=request.conversation_id,
            content=request.message_content,
            user_id=current_user_id,
            is_error=request.is_error
        )
        
        result = MessageResponse.model_validate(system_message)
        return success_response(result.model_dump())
    
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating system message: {str(e)}"
        )



