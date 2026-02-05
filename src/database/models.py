"""
Auto-generated SQLAlchemy models from database schema.
Generated similar to TypeORM entity generation.
"""
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, Boolean, Float, JSON, ARRAY
from sqlalchemy.dialects.postgresql import UUID, BYTEA, INET
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from datetime import datetime
import uuid

from .connection import Base


class Agents(Base):
    """Model for Agents table"""
    __tablename__ = "Agents"

    agent_id = Column(UUID(as_uuid=True), primary_key=True)
    agent_name = Column(String(255))
    agent_desc = Column(Text)
    agent_prompt = Column(Text)
    created_at = Column(DateTime)
    created_by = Column(UUID(as_uuid=True))
    updated_at = Column(DateTime)
    updated_by = Column(UUID(as_uuid=True))
    agent_profile_image = Column(UUID(as_uuid=True))

    Files = relationship("Files", foreign_keys=[agent_profile_image])
    Users = relationship("Users", foreign_keys=[created_by])
    Users = relationship("Users", foreign_keys=[updated_by])


class Conversations(Base):
    """Model for Conversations table"""
    __tablename__ = "Conversations"

    conversation_id = Column(UUID(as_uuid=True), primary_key=True)
    conversation_topic = Column(String(255))
    created_at = Column(DateTime)
    created_by = Column(UUID(as_uuid=True))
    updated_at = Column(DateTime)
    updated_by = Column(UUID(as_uuid=True))

    Users = relationship("Users", foreign_keys=[created_by])
    Users = relationship("Users", foreign_keys=[updated_by])


class Files(Base):
    """Model for Files table"""
    __tablename__ = "Files"

    file_id = Column(UUID(as_uuid=True), primary_key=True)
    file_name = Column(String(255))
    file_size = Column(Integer)
    mime_type = Column(String(255))
    created_at = Column(DateTime)
    created_by = Column(UUID(as_uuid=True))
    file_path = Column(String(255))

    Users = relationship("Users", foreign_keys=[created_by])


class Messages(Base):
    """Model for Messages table"""
    __tablename__ = "Messages"

    message_id = Column(UUID(as_uuid=True), primary_key=True)
    conversation_id = Column(UUID(as_uuid=True))
    message_content = Column(Text)
    sender_role = Column(String(16))
    created_at = Column(DateTime)
    created_by = Column(UUID(as_uuid=True))
    updated_at = Column(DateTime)
    updated_by = Column(UUID(as_uuid=True))

    conversation = relationship("Conversations", foreign_keys=[conversation_id])
    Users = relationship("Users", foreign_keys=[created_by])
    Roles = relationship("Roles", foreign_keys=[sender_role])
    Users = relationship("Users", foreign_keys=[updated_by])


class Metadatas(Base):
    """Model for Metadatas table"""
    __tablename__ = "Metadatas"

    metadata_id = Column(UUID(as_uuid=True), primary_key=True)
    metadata_of = Column(UUID(as_uuid=True))
    metadata = Column(JSON)
    content_to_summarize = Column(Text)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    Agents = relationship("Agents", foreign_keys=[metadata_of])
    Conversations = relationship("Conversations", foreign_keys=[metadata_of])
    Files = relationship("Files", foreign_keys=[metadata_of])
    Nodes = relationship("Nodes", foreign_keys=[metadata_of])
    Workspaces = relationship("Workspaces", foreign_keys=[metadata_of])


class Nodevector(Base):
    """Model for NodeVector table"""
    __tablename__ = "NodeVector"

    node_id = Column(UUID(as_uuid=True), primary_key=True)
    node_content_md_chuck = Column(Text)
    embedding = Column(Vector(1536))
    created_at = Column(DateTime)
    created_by = Column(UUID(as_uuid=True))
    updated_at = Column(DateTime)
    updated_by = Column(UUID(as_uuid=True))
    deleted_at = Column(DateTime)
    node_content_md_chuck_hash = Column(String(255))
    node_vector_chuck_id = Column(UUID(as_uuid=True), primary_key=True)
    node_vector_chuck_order = Column(Integer)

    Users = relationship("Users", foreign_keys=[created_by])
    node = relationship("Nodes", foreign_keys=[node_id])
    Users = relationship("Users", foreign_keys=[updated_by])


class Nodes(Base):
    """Model for Nodes table"""
    __tablename__ = "Nodes"

    node_id = Column(UUID(as_uuid=True), primary_key=True)
    node_name = Column(String(255))
    node_desc = Column(Text)
    node_content_md = Column(Text)
    node_location_x = Column(Float)
    node_location_y = Column(Float)
    node_location_z = Column(Float)
    created_at = Column(DateTime)
    created_by = Column(UUID(as_uuid=True))
    updated_at = Column(DateTime)
    updated_by = Column(UUID(as_uuid=True))

    Users = relationship("Users", foreign_keys=[created_by])
    Users = relationship("Users", foreign_keys=[updated_by])


class Relationpriorities(Base):
    """Model for RelationPriorities table"""
    __tablename__ = "RelationPriorities"

    relation_priority_id = Column(String(8), primary_key=True)



class Relationtypes(Base):
    """Model for RelationTypes table"""
    __tablename__ = "RelationTypes"

    relation_type_id = Column(String(32), primary_key=True)



class Relations(Base):
    """Model for Relations table"""
    __tablename__ = "Relations"

    parent_id = Column(UUID(as_uuid=True), primary_key=True)
    child_id = Column(UUID(as_uuid=True), primary_key=True)
    relation_type_id = Column(String(32), primary_key=True)
    relation_priority_id = Column(String(8))
    created_at = Column(DateTime)
    created_by = Column(UUID(as_uuid=True))
    updated_at = Column(DateTime)
    updated_by = Column(UUID(as_uuid=True))

    child = relationship("Agents", foreign_keys=[child_id])
    child = relationship("Conversations", foreign_keys=[child_id])
    child = relationship("Files", foreign_keys=[child_id])
    child = relationship("Nodes", foreign_keys=[child_id])
    child = relationship("Workspaces", foreign_keys=[child_id])
    Users = relationship("Users", foreign_keys=[created_by])
    parent = relationship("Workspaces", foreign_keys=[parent_id])
    parent = relationship("Nodes", foreign_keys=[parent_id])
    relation_priority = relationship("Relationpriorities", foreign_keys=[relation_priority_id])
    relation_type = relationship("Relationtypes", foreign_keys=[relation_type_id])
    Users = relationship("Users", foreign_keys=[updated_by])


class Roles(Base):
    """Model for Roles table"""
    __tablename__ = "Roles"

    role_id = Column(String(16), primary_key=True)



class Users(Base):
    """Model for Users table"""
    __tablename__ = "Users"

    user_id = Column(UUID(as_uuid=True), primary_key=True)
    user_display = Column(String(32))
    password = Column(String(255))
    first_name = Column(String(64))
    last_name = Column(String(64))
    email = Column(String(64))
    num_phone = Column(String(32))
    user_profile_file_id = Column(UUID(as_uuid=True))
    created_at = Column(DateTime)



class Workspaces(Base):
    """Model for Workspaces table"""
    __tablename__ = "Workspaces"

    workspace_id = Column(UUID(as_uuid=True), primary_key=True)
    workspace_name = Column(String(255))
    workspace_desc = Column(Text)
    created_at = Column(DateTime)
    created_by = Column(UUID(as_uuid=True))
    updated_at = Column(DateTime)
    updated_by = Column(UUID(as_uuid=True))

    Users = relationship("Users", foreign_keys=[created_by])
    Users = relationship("Users", foreign_keys=[updated_by])

