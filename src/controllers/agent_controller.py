"""
Agent CRUD controller.
All operations use ORM - no raw SQL queries.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID, uuid4
from datetime import datetime

from src.database import get_db
from src.repositories.agent_repository import AgentRepository
from src.database.models import Agents
from src.dto.agent_dto import (
    AgentCreateRequest,
    AgentUpdateRequest,
    AgentResponse,
    AgentListResponse
)
from src.dto.response_dto import success_response, error_response
from src.utils.auth import get_current_user_id

router = APIRouter(
    prefix="/agents",
    tags=["Agents"]
)


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Get all agents",
    description="Retrieve all agents created by the authenticated user"
)
async def get_all_agents(
    limit: Optional[int] = None,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Get all agents created by the authenticated user - uses ORM query"""
    try:
        repo = AgentRepository(db)
        agents = repo.find_by_creator(user_id)

        if limit:
            agents = agents[:limit]

        result = AgentListResponse(
            count=len(agents),
            agents=[AgentResponse.model_validate(agent) for agent in agents]
        )
        return success_response(result.model_dump())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching agents: {str(e)}"
        )


@router.get(
    "/{agent_id}",
    status_code=status.HTTP_200_OK,
    summary="Get agent by ID",
    description="Retrieve a single agent by ID (only if created by authenticated user)"
)
async def get_agent_by_id(
    agent_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Get agent by ID - uses ORM, only returns if user owns the agent"""
    try:
        repo = AgentRepository(db)
        agent = repo.find_one_by_id(agent_id)

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent with ID {agent_id} not found"
            )

        if agent.created_by != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this agent"
            )

        result = AgentResponse.model_validate(agent)
        return success_response(result.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching agent: {str(e)}"
        )


@router.get(
    "/search/{name}",
    status_code=status.HTTP_200_OK,
    summary="Search agents by name",
    description="Search agents by name (partial match) among user's own agents"
)
async def search_agents(
    name: str,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Search agents by name - uses ORM, filtered by user's own agents"""
    try:
        repo = AgentRepository(db)
        agents = repo.search_by_name(name)
        # Filter to only show agents created by the authenticated user
        agents = [agent for agent in agents if agent.created_by == user_id]

        result = AgentListResponse(
            count=len(agents),
            agents=[AgentResponse.model_validate(agent) for agent in agents]
        )
        return success_response(result.model_dump())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching agents: {str(e)}"
        )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create new agent",
    description="Create a new agent using ORM (requires authentication)"
)
async def create_agent(
    request: AgentCreateRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Create agent - uses ORM with authenticated user_id"""
    try:
        repo = AgentRepository(db)

        # Create new agent entity
        new_agent = Agents(
            agent_id=uuid4(),
            agent_name=request.agent_name,
            agent_desc=request.agent_desc,
            agent_prompt=request.agent_prompt,
            agent_profile_image=request.agent_profile_image,
            created_at=datetime.utcnow(),
            created_by=user_id,
            updated_at=datetime.utcnow(),
            updated_by=user_id
        )

        # Save to database
        created_agent = repo.create(new_agent)

        result = AgentResponse.model_validate(created_agent)
        return success_response(result.model_dump())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating agent: {str(e)}"
        )


@router.put(
    "/{agent_id}",
    status_code=status.HTTP_200_OK,
    summary="Update agent",
    description="Update an existing agent using ORM (requires authentication)"
)
async def update_agent(
    agent_id: UUID,
    request: AgentUpdateRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Update agent - uses ORM with authenticated user_id"""
    try:
        repo = AgentRepository(db)

        # Check if agent exists
        agent = repo.find_one_by_id(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent with ID {agent_id} not found"
            )

        # Check if user owns this agent
        if agent.created_by != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this agent"
            )

        # Prepare update data (only fields that were provided)
        update_data = request.model_dump(exclude_unset=True)
        update_data['updated_at'] = datetime.utcnow()
        update_data['updated_by'] = user_id

        # Update in database
        updated_agent = repo.update_by_id(agent_id, update_data)

        result = AgentResponse.model_validate(updated_agent)
        return success_response(result.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating agent: {str(e)}"
        )


@router.patch(
    "/{agent_id}",
    response_model=AgentResponse,
    status_code=status.HTTP_200_OK,
    summary="Partially update agent",
    description="Partially update an agent (same as PUT) using ORM (requires authentication)"
)
async def patch_agent(
    agent_id: UUID,
    request: AgentUpdateRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """Patch agent - uses ORM (alias for PUT) with authenticated user_id"""
    return await update_agent(agent_id, request, db, user_id)


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete agent",
    description="Delete an agent by ID using ORM"
)
async def delete_agent(agent_id: UUID, db: Session = Depends(get_db)):
    """Delete agent - uses ORM"""
    try:
        repo = AgentRepository(db)

        # Check if agent exists
        if not repo.exists_by_id(agent_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent with ID {agent_id} not found"
            )

        # Delete from database
        success = repo.delete_by_id(agent_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete agent"
            )

        return success_response({"message": "Agent deleted successfully", "agent_id": str(agent_id)})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting agent: {str(e)}"
        )


