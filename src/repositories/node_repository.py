"""
Node repository for Nodes table.
"""
from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from src.database.models import Nodes, Relations
from src.repositories.base_repository import BaseRepository


class NodeRepository(BaseRepository[Nodes]):
    """Repository for Nodes entity."""

    def __init__(self, db: Session):
        super().__init__(Nodes, db)

    def find_by_created_by(self, created_by: UUID) -> List[Nodes]:
        """Find all nodes created by a user."""
        return self.find_by(created_by=created_by)

    def find_by_ids(self, node_ids: List[UUID]) -> List[Nodes]:
        """Find all nodes whose node_id is in the given list. Used to join citation data."""
        if not node_ids:
            return []
        return self.db.query(Nodes).filter(Nodes.node_id.in_(node_ids)).all()

    def find_node_ids_by_workspace(self, workspace_id: UUID) -> List[UUID]:
        """Find all node IDs in a workspace (through Relations table)."""
        rows = (
            self.db.query(Relations.child_id)
            .filter(Relations.parent_id == workspace_id)
            .join(Nodes, Relations.child_id == Nodes.node_id)
            .distinct()
            .all()
        )
        return [r[0] for r in rows if r[0]]
