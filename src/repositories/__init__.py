"""
Repository pattern for database access (like TypeORM repositories).
Provides a clean abstraction layer over SQLAlchemy ORM.
"""
from .base_repository import BaseRepository
from .agent_repository import AgentRepository
from .metadata_repository import MetadataRepository

__all__ = ["BaseRepository", "AgentRepository", "MetadataRepository"]
