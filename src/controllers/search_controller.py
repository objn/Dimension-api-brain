from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional, List
from uuid import UUID

from src.database import get_db
from src.database.models import Messages
from src.repositories.agent_repository import AgentRepository, PUBLIC_AGENT_UUID
from src.repositories.conversation_repository import ConversationRepository, MessageRepository
from src.dto.agent_dto import AgentResponse
from src.dto.conversation_dto import (
    GlobalSearchResponse,
    AgentSearchItem,
    ChatHistorySearchItem,
)
from src.dto.response_dto import success_response
from src.utils.auth import get_current_user_id


router = APIRouter(
    prefix="/search",
    tags=["Search"],
)


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Search across agents and chat history",
    description=(
        "Perform a non-semantic (case-insensitive) substring search over agent names and conversation "
        "topics / messages for the current user. Returns results in separate lists."
    ),
)
async def global_search(
    q: str,
    limit_agents: Optional[int] = 10,
    limit_conversations: Optional[int] = 10,
    db: Session = Depends(get_db),
    current_user_id: UUID = Depends(get_current_user_id),
):
    """
    Non-semantic substring search over:
    - Agents accessible by the user (own agents + public agents) by agent_name.
    - Conversations created by the user by topic and by message content.

    If q is empty/blank, returns recent conversations and accessible agents (limited).
    """
    try:
        agent_repo = AgentRepository(db)
        convo_repo = ConversationRepository(db)
        message_repo = MessageRepository(db)

        query = (q or "").strip()

        # If blank query, return recent items to populate the search UI
        if not query:
            agents = agent_repo.find_accessible_by_user(current_user_id)
            # prefer default/public agents first, then by created_at desc
            agents.sort(
                key=lambda a: (
                    0 if a.created_by == PUBLIC_AGENT_UUID else 1,
                    -(a.created_at.timestamp() if a.created_at else 0),
                )
            )
            conversations_list = convo_repo.find_all_sorted(
                sort_by="updated_at",
                sort_order="desc",
                limit=limit_conversations,
                user_id=current_user_id,
            )
        else:
            # Agents: substring, case-insensitive match on name
            agents = agent_repo.search_accessible_by_user(current_user_id, query)

            # Conversations: combine topic + message substring matches, unique by conversation_id
            conv_by_topic = {
                c.conversation_id: c
                for c in convo_repo.search_conversations_by_topic_contains(current_user_id, query)
            }
            conv_by_message = {
                c.conversation_id: c
                for c in convo_repo.search_conversations_by_message_contains(current_user_id, query)
            }

            combined_conversations = {**conv_by_topic, **conv_by_message}
            conversations_list = list(combined_conversations.values())

            # Sort by updated_at desc (most recent first)
            conversations_list.sort(
                key=lambda c: c.updated_at or c.created_at or None, reverse=True
            )

        if limit_agents is not None and limit_agents > 0:
            agents = agents[: limit_agents]
        if limit_conversations is not None and limit_conversations > 0:
            conversations_list = conversations_list[: limit_conversations]

        agent_items: List[AgentSearchItem] = [
            AgentSearchItem(
                agent_id=agent.agent_id,
                agent_name=agent.agent_name,
                agent_desc=agent.agent_desc,
                default=agent.created_by == PUBLIC_AGENT_UUID,
            )
            for agent in agents
        ]

        conversation_items: List[ChatHistorySearchItem] = []
        for convo in conversations_list:
            # Fetch last message preview for this conversation
            messages = (
                message_repo.db.query(Messages)
                .filter(Messages.conversation_id == convo.conversation_id)
                .order_by(Messages.created_at.desc())
                .limit(1)
                .all()
            )
            last_preview: Optional[str] = None
            if messages:
                content = messages[0].message_content or ""
                last_preview = content[:200] + "…" if len(content) > 200 else content

            conversation_items.append(
                ChatHistorySearchItem(
                    conversation_id=convo.conversation_id,
                    conversation_topic=convo.conversation_topic,
                    updated_at=convo.updated_at,
                    last_message_preview=last_preview,
                )
            )

        result = GlobalSearchResponse(
            query=query,
            agents=agent_items,
            conversations=conversation_items,
        )
        return success_response(result.model_dump())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error performing search: {str(e)}",
        )

