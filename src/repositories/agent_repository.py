"""
Agent repository with custom query methods.
Extends BaseRepository for agent-specific operations.
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from uuid import UUID

from .base_repository import BaseRepository
from src.database.models import Agents

# Public agent UUID - agents with this creator are visible to everyone
PUBLIC_AGENT_UUID = UUID('00000000-0000-0000-0000-000000000000')


class AgentRepository(BaseRepository[Agents]):
    """
    Agent repository with custom methods.
    Similar to TypeORM's custom repository.
    """

    def __init__(self, db: Session):
        super().__init__(Agents, db)

    def find_by_name(self, name: str) -> Optional[Agents]:
        """Find agent by exact name"""
        return self.find_one_by(agent_name=name)

    def search_by_name(self, name: str) -> List[Agents]:
        """Search agents by name (partial match, case-insensitive)"""
        return self.db.query(Agents).filter(
            Agents.agent_name.ilike(f"%{name}%")
        ).all()

    def find_by_creator(self, user_id: UUID) -> List[Agents]:
        """Find all agents created by a specific user"""
        return self.find_by(created_by=user_id)
    
    def find_accessible_by_user(self, user_id: UUID) -> List[Agents]:
        """Find all agents accessible by a user (own agents + public agents)"""
        return self.db.query(Agents).filter(
            (Agents.created_by == user_id) | (Agents.created_by == PUBLIC_AGENT_UUID)
        ).all()
    
    def search_accessible_by_user(self, user_id: UUID, name: str) -> List[Agents]:
        """Search agents by name among accessible agents (own + public)"""
        return self.db.query(Agents).filter(
            ((Agents.created_by == user_id) | (Agents.created_by == PUBLIC_AGENT_UUID)) &
            (Agents.agent_name.ilike(f"%{name}%"))
        ).all()

    def search_accessible_by_user_exact(self, user_id: UUID, name: str) -> List[Agents]:
        """Exact (case-insensitive) search by agent_name among accessible agents (own + public)."""
        return self.db.query(Agents).filter(
            ((Agents.created_by == user_id) | (Agents.created_by == PUBLIC_AGENT_UUID)) &
            (Agents.agent_name.ilike(f"{name}"))
        ).all()
    
    def is_accessible_by_user(self, agent_id: UUID, user_id: UUID) -> bool:
        """Check if an agent is accessible by a user"""
        agent = self.find_one_by_id(agent_id)
        if not agent:
            return False
        return agent.created_by == user_id or agent.created_by == PUBLIC_AGENT_UUID

    def find_recent(self, limit: int = 10) -> List[Agents]:
        """Find most recently created agents"""
        return self.db.query(Agents).order_by(
            Agents.created_at.desc()
        ).limit(limit).all()

    def find_by_workspace(self, workspace_id: UUID) -> List[Agents]:
        """Find all agents in a workspace (through Relations table)"""
        from src.database.models import Relations

        return self.db.query(Agents).join(
            Relations,
            Relations.child_id == Agents.agent_id
        ).filter(
            Relations.parent_id == workspace_id,
            Relations.relation_type_id.in_(["WORKSPACE_AGENT", "CONTAINS"])
        ).all()

    def is_agent_default(self, agent_id: UUID) -> bool:
        """Check if an agent is the default agent"""
        if agent_id == PUBLIC_AGENT_UUID:
            return True
        return False