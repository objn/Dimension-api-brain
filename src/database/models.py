"""
Auto-generated SQLAlchemy models from database schema.
Generated similar to TypeORM entity generation.
"""
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, Boolean, Float, JSON, ARRAY
from sqlalchemy.dialects.postgresql import UUID, BYTEA, INET, DOUBLE_PRECISION
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
    created_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))
    updated_at = Column(DateTime)
    updated_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))
    agent_profile_image = Column(UUID(as_uuid=True), ForeignKey('Files.file_id'))

    profile_image = relationship("Files", foreign_keys=[agent_profile_image])
    creator = relationship("Users", foreign_keys=[created_by])
    updater = relationship("Users", foreign_keys=[updated_by])


class Conversations(Base):
    """Model for Conversations table"""
    __tablename__ = "Conversations"

    conversation_id = Column(UUID(as_uuid=True), primary_key=True)
    conversation_topic = Column(String(255))
    created_at = Column(DateTime)
    created_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))
    updated_at = Column(DateTime)
    updated_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))

    creator = relationship("Users", foreign_keys=[created_by])
    updater = relationship("Users", foreign_keys=[updated_by])
    messages = relationship("Messages", back_populates="conversation", lazy="joined")


class Files(Base):
    """Model for Files table"""
    __tablename__ = "Files"

    file_id = Column(UUID(as_uuid=True), primary_key=True)
    file_name = Column(String(255))
    file_size = Column(Integer)
    mime_type = Column(String(255))
    created_at = Column(DateTime)
    created_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))

    creator = relationship("Users", foreign_keys=[created_by])


class Messages(Base):
    """Model for Messages table"""
    __tablename__ = "Messages"

    message_id = Column(UUID(as_uuid=True), primary_key=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey('Conversations.conversation_id'))
    message_content = Column(Text)
    sender_role = Column(String(16), ForeignKey('Roles.role_id'))
    created_at = Column(DateTime)
    created_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))
    updated_at = Column(DateTime)
    updated_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))

    conversation = relationship("Conversations", foreign_keys=[conversation_id], back_populates="messages")
    creator = relationship("Users", foreign_keys=[created_by])
    role = relationship("Roles", foreign_keys=[sender_role])
    updater = relationship("Users", foreign_keys=[updated_by])


class Metadatas(Base):
    """Model for Metadatas table"""
    __tablename__ = "Metadatas"

    metadata_id = Column(UUID(as_uuid=True), primary_key=True)
    metadata_of = Column(UUID(as_uuid=True))
    metadata_json = Column("metadata", JSON)  # Renamed to avoid SQLAlchemy reserved name
    content_to_summarize = Column(Text)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    # Note: metadata_of can reference multiple table types (polymorphic)
    # You may need to handle this relationship based on your use case


class Nodevector(Base):
    """Model for NodeVector table"""
    __tablename__ = "NodeVector"

    node_id = Column(UUID(as_uuid=True), ForeignKey('Nodes.node_id'), primary_key=True)
    document_vector_chuck = Column(Integer, primary_key=True)
    node_content_md_chuck = Column(Text)
    embedding = Column(Vector(1536))  # OpenAI embedding dimension
    created_at = Column(DateTime)
    created_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))
    updated_at = Column(DateTime)
    updated_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))

    creator = relationship("Users", foreign_keys=[created_by])
    node = relationship("Nodes", foreign_keys=[node_id])
    updater = relationship("Users", foreign_keys=[updated_by])


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
    created_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))
    updated_at = Column(DateTime)
    updated_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))

    creator = relationship("Users", foreign_keys=[created_by])
    updater = relationship("Users", foreign_keys=[updated_by])


class Relationpriority(Base):
    """Model for RelationPriority table"""
    __tablename__ = "RelationPriority"

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
    relation_type_id = Column(String(32), ForeignKey('RelationTypes.relation_type_id'), primary_key=True)
    relation_priority_id = Column(String(8), ForeignKey('RelationPriority.relation_priority_id'))
    created_at = Column(DateTime)
    created_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))
    updated_at = Column(DateTime)
    updated_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))

    # Note: parent_id and child_id can reference multiple table types
    # You may need to handle these relationships based on your use case
    creator = relationship("Users", foreign_keys=[created_by])
    relation_priority = relationship("Relationpriority", foreign_keys=[relation_priority_id])
    relation_type = relationship("Relationtypes", foreign_keys=[relation_type_id])
    updater = relationship("Users", foreign_keys=[updated_by])


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
    created_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))
    updated_at = Column(DateTime)
    updated_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))

    creator = relationship("Users", foreign_keys=[created_by])
    updater = relationship("Users", foreign_keys=[updated_by])

