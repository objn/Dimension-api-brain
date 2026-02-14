"""
Chat Service - Implements AI Agent Operating Instructions.

This service handles the multi-role conversation flow:
- Messages are immutable (append-only)
- Proper role assignment (SYSTEM, USER, AGENT, TOOL)
- Agent persona management via agent_prompt
- Context management with recent message filtering
"""
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime
from sqlalchemy.orm import Session

from src.database.models import Messages, Conversations, Agents
from src.repositories.conversation_repository import ConversationRepository, MessageRepository
from src.repositories.agent_repository import AgentRepository
from src.dto.conversation_dto import (
    SenderRole,
    MessageResponse,
    ChatResponse,
    ChatHistoryResponse,
    LLMProviderType
)
import src.services.llm_router as LLM


class ChatService:
    """
    Chat service implementing AI Agent Operating Instructions.
    
    Conversation Model:
    - A Conversation is a container of context
    - A Message is an immutable event in the conversation timeline
    - Messages must never be edited or deleted, only appended
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.conversation_repo = ConversationRepository(db)
        self.message_repo = self.conversation_repo.get_message_repository()
        self.agent_repo = AgentRepository(db)
    
    def _check_conversation_ownership(
        self,
        conversation_id: UUID,
        user_id: UUID
    ) -> Conversations:
        """
        Check if the user owns the conversation.
        Raises ValueError if conversation not found or user doesn't own it.
        """
        conversation = self.conversation_repo.find_one_by_id(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        if conversation.created_by != user_id:
            raise PermissionError("You don't have permission to access this conversation")
        
        return conversation
    
    def create_message(
        self,
        conversation_id: UUID,
        content: str,
        sender_role: SenderRole,
        created_by: UUID
    ) -> Messages:
        """
        Create a new immutable message in the conversation.
        Messages are append-only - never edited or deleted.
        """
        new_message = Messages(
            message_id=uuid4(),
            conversation_id=conversation_id,
            message_content=content,
            sender_role=sender_role.value,
            created_by=created_by,
            created_at=datetime.utcnow(),
            updated_by=created_by,
            updated_at=datetime.utcnow()
        )
        return self.message_repo.create(new_message)
    
    def get_conversation_context(
        self,
        conversation_id: UUID,
        max_messages: int = 10,
        user_id: Optional[UUID] = None
    ) -> List[Dict[str, Any]]:
        """
        Get relevant recent messages for context.
        Filters and sorts by timestamp, returns most recent k messages.
        """
        # Check ownership if user_id provided
        if user_id:
            conversation = self._check_conversation_ownership(conversation_id, user_id)
        else:
            conversation = self.conversation_repo.find_one_by_id(conversation_id)
            if not conversation:
                return []
        
        # Get messages sorted by created_at
        messages = sorted(
            conversation.messages,
            key=lambda m: m.created_at or datetime.min
        )
        
        # Return most recent messages as context
        recent_messages = messages[-max_messages:] if len(messages) > max_messages else messages
        
        return [
            {
                "message_id": str(msg.message_id),
                "message_content": msg.message_content,
                "sender_role": msg.sender_role,
                "created_at": msg.created_at.isoformat() if msg.created_at else None
            }
            for msg in recent_messages
        ]
    
    def process_user_message(
        self,
        conversation_id: UUID,
        user_message: str,
        agent_id: UUID,
        user_id: UUID,
        llm_provider: LLMProviderType = "openai",
        max_history: int = 10
    ) -> ChatResponse:
        """
        Process a USER message and generate an AGENT response.
        
        Flow per AI Agent Operating Instructions:
        1. Read the latest conversation context
        2. Apply agent_prompt as system guidance
        3. Generate response that addresses user's intent
        4. Store response as AGENT message with agent_id
        """
        # Validate conversation exists and check ownership
        conversation = self._check_conversation_ownership(conversation_id, user_id)
        
        # Validate agent exists and get agent_prompt
        agent = self.agent_repo.find_one_by_id(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")
        
        # 1. Store USER message (immutable)
        user_msg = self.create_message(
            conversation_id=conversation_id,
            content=user_message,
            sender_role=SenderRole.USER,
            created_by=user_id
        )
        
        # 2. Get conversation context (recent messages)
        context = self.get_conversation_context(conversation_id, max_history)
        
        # 3. Generate AGENT response using agent_prompt as system guidance
        agent_response_content = LLM.chat_with_history(
            user_message=user_message,
            topic=conversation.conversation_topic,
            history=context,
            provider=llm_provider,
            system_prompt=agent.agent_prompt,
            k=max_history
        )
        
        # 4. Store AGENT response (immutable)
        # Note: created_by is the user who triggered the conversation,
        # the agent_id is tracked separately in the response
        agent_msg = self.create_message(
            conversation_id=conversation_id,
            content=agent_response_content,
            sender_role=SenderRole.AGENT,
            created_by=user_id  # User triggered this, agent_id tracked in response
        )
        
        # Update conversation timestamp
        self.conversation_repo.update_by_id(conversation_id, {
            "updated_at": datetime.utcnow(),
            "updated_by": user_id
        })
        
        return ChatResponse(
            conversation_id=conversation_id,
            user_message=MessageResponse.model_validate(user_msg),
            agent_response=MessageResponse.model_validate(agent_msg),
            agent_id=agent_id,
            agent_name=agent.agent_name,
            messages_in_context=len(context)
        )
    
    def record_tool_output(
        self,
        conversation_id: UUID,
        tool_name: str,
        tool_output: str,
        tool_input: Optional[str],
        user_id: UUID
    ) -> Messages:
        """
        Record a TOOL message in the conversation.
        
        Per AI Agent Operating Instructions:
        - Store tool input/output as TOOL role message
        - This can then be used to generate final AGENT response
        """
        # Check ownership
        self._check_conversation_ownership(conversation_id, user_id)
        
        # Format tool message content
        content = f"[TOOL: {tool_name}]"
        if tool_input:
            content += f"\nInput: {tool_input}"
        content += f"\nOutput: {tool_output}"
        
        return self.create_message(
            conversation_id=conversation_id,
            content=content,
            sender_role=SenderRole.TOOL,
            created_by=user_id
        )
    
    def record_system_message(
        self,
        conversation_id: UUID,
        content: str,
        user_id: UUID,
        is_error: bool = False
    ) -> Messages:
        """
        Record a SYSTEM message in the conversation.
        
        Per AI Agent Operating Instructions:
        - SYSTEM messages are for notices, errors, policies, or hidden context
        - Errors should be reported as SYSTEM messages
        """
        # Check ownership
        self._check_conversation_ownership(conversation_id, user_id)
        
        if is_error:
            content = f"[ERROR] {content}"
        
        return self.create_message(
            conversation_id=conversation_id,
            content=content,
            sender_role=SenderRole.SYSTEM,
            created_by=user_id
        )
    
    def get_chat_history(
        self,
        conversation_id: UUID,
        user_id: Optional[UUID] = None
    ) -> ChatHistoryResponse:
        """
        Get full chat history with role-based statistics.
        """
        # Check ownership if user_id provided
        if user_id:
            conversation = self._check_conversation_ownership(conversation_id, user_id)
        else:
            conversation = self.conversation_repo.find_one_by_id(conversation_id)
            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")
        
        messages = sorted(
            conversation.messages,
            key=lambda m: m.created_at or datetime.min
        )
        
        # Calculate role counts
        role_counts = {
            SenderRole.USER.value: 0,
            SenderRole.AGENT.value: 0,
            SenderRole.SYSTEM.value: 0,
            SenderRole.TOOL.value: 0
        }
        for msg in messages:
            if msg.sender_role in role_counts:
                role_counts[msg.sender_role] += 1
        
        return ChatHistoryResponse(
            conversation_id=conversation_id,
            conversation_topic=conversation.conversation_topic,
            total_messages=len(messages),
            messages=[MessageResponse.model_validate(msg) for msg in messages],
            role_counts=role_counts
        )
    
    def respond_after_tool(
        self,
        conversation_id: UUID,
        agent_id: UUID,
        user_id: UUID,
        llm_provider: LLMProviderType = "openai",
        max_history: int = 10
    ) -> Messages:
        """
        Generate an AGENT response after a TOOL call.
        
        Per AI Agent Operating Instructions:
        - After recording TOOL output, agent should respond again as AGENT
        """
        # Check ownership
        self._check_conversation_ownership(conversation_id, user_id)
        
        agent = self.agent_repo.find_one_by_id(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")
        
        context = self.get_conversation_context(conversation_id, max_history)
        
        # Generate response with tool output in context
        agent_response = LLM.chat_with_history(
            user_message="Based on the tool output above, please provide a response.",
            history=context,
            provider=llm_provider,
            system_prompt=agent.agent_prompt,
            k=max_history
        )
        
        # created_by is the user who triggered, agent_id tracked separately
        return self.create_message(
            conversation_id=conversation_id,
            content=agent_response,
            sender_role=SenderRole.AGENT,
            created_by=user_id
        )
