"""
Auto-generated SQLAlchemy models from database schema.
Generated similar to TypeORM entity generation.
"""
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, Boolean, Float, JSON, ARRAY
from sqlalchemy.dialects.postgresql import UUID, BYTEA, INET
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from pgvector.sqlalchemy import Vector
from .connection import Base


class Agents(Base):
    """Model for Agents table"""
    __tablename__ = "Agents"

    agent_id = Column(UUID(as_uuid=True), primary_key=True)
    agent_name = Column(String(255))
    agent_desc = Column(Text)
    agent_prompt = Column(Text)
    # Add column in DB if missing: ALTER TABLE "Agents" ADD COLUMN default_llm_provider VARCHAR(32) NULL;
    default_llm_provider = Column(String(32), nullable=True)
    created_at = Column(DateTime)
    created_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))
    updated_at = Column(DateTime)
    updated_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))
    agent_profile_image = Column(UUID(as_uuid=True), ForeignKey('Files.file_id'))
    agent_default = Column(Boolean, default=False, nullable=False)

    Files = relationship("Files", foreign_keys=[agent_profile_image])
    Users = relationship("Users", foreign_keys=[created_by])
    Users_2 = relationship("Users", foreign_keys=[updated_by])


class Conversations(Base):
    """Model for Conversations table"""
    __tablename__ = "Conversations"

    conversation_id = Column(UUID(as_uuid=True), primary_key=True)
    conversation_topic = Column(String(255))
    created_at = Column(DateTime)
    created_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))
    updated_at = Column(DateTime)
    updated_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))

    Users = relationship("Users", foreign_keys=[created_by])
    Users_2 = relationship("Users", foreign_keys=[updated_by])
    messages = relationship("Messages", foreign_keys="Messages.conversation_id", back_populates="conversation")


class Files(Base):
    """Model for Files table"""
    __tablename__ = "Files"

    file_id = Column(UUID(as_uuid=True), primary_key=True)
    file_name = Column(String(255))
    file_size = Column(Integer)
    mime_type = Column(String(255))
    created_at = Column(DateTime)
    created_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))
    file_path = Column(String(255))

    Users = relationship("Users", foreign_keys=[created_by])


class JobResults(Base):
    """Model for JobResults table"""
    __tablename__ = "JobResults"

    job_result_id = Column(String(16), primary_key=True)



class Jobtypes(Base):
    """Model for JobTypes table"""
    __tablename__ = "JobTypes"

    Job_type_id = Column(String(255), primary_key=True)



class Job(Base):
    """Model for Jobs table"""
    __tablename__ = "Jobs"

    job_id = Column(UUID(as_uuid=True), primary_key=True)
    job_result = Column(String(16), ForeignKey('JobResults.job_result_id'))
    created_at = Column(DateTime)
    created_by = Column(UUID(as_uuid=True))
    updated_at = Column(DateTime)
    updated_by = Column(UUID(as_uuid=True))
    job_type = Column(String(255), ForeignKey('JobTypes.Job_type_id'))
    job_start_time = Column(DateTime)
    job_end_time = Column(DateTime)
    job_actived = Column(Boolean)
    job_error_log = Column(Text, nullable=True)

    JobResults = relationship("JobResults", foreign_keys=[job_result])
    JobTypes = relationship("Jobtypes", foreign_keys=[job_type])


class Messages(Base):
    """Model for Messages table"""
    __tablename__ = "Messages"

    message_id = Column(UUID(as_uuid=True), primary_key=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey('Conversations.conversation_id'))
    message_content = Column(Text)
    sender_role = Column(String(16), ForeignKey('Roles.role_id'))
    metadatas = Column("metadatas", JSON, nullable=True)
    created_at = Column(DateTime)
    created_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))
    updated_at = Column(DateTime)
    updated_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))

    conversation = relationship("Conversations", foreign_keys=[conversation_id], back_populates="messages")
    Users = relationship("Users", foreign_keys=[created_by])
    Roles = relationship("Roles", foreign_keys=[sender_role])
    Users_2 = relationship("Users", foreign_keys=[updated_by])


class Metadatas(Base):
    """Model for Metadatas table"""
    __tablename__ = "Metadatas"

    metadata_id = Column(UUID(as_uuid=True), primary_key=True)
    metadata_of = Column(UUID(as_uuid=True))
    metadata_json = Column("metadata", JSON)
    content_to_summarize = Column(Text)
    created_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))
    created_at = Column(DateTime)
    updated_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))
    updated_at = Column(DateTime)



class Nodevector(Base):
    """Model for NodeVector table"""
    __tablename__ = "NodeVector"

    node_id = Column(UUID(as_uuid=True), ForeignKey('Nodes.node_id'), primary_key=True)
    node_content_md_chunk = Column(Text)
    embedding = Column(Vector(1536))
    created_at = Column(DateTime)
    created_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))
    updated_at = Column(DateTime)
    updated_by = Column(UUID(as_uuid=True), ForeignKey('Users.user_id'))
    deleted_at = Column(DateTime)
    node_content_md_chunk_hash = Column(String(255))
    node_vector_chunk_id = Column(UUID(as_uuid=True), primary_key=True)
    node_vector_chunk_order = Column(Integer)

    Users = relationship("Users", foreign_keys=[created_by])
    node = relationship("Nodes", foreign_keys=[node_id])
    Users_2 = relationship("Users", foreign_keys=[updated_by])


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

    Users = relationship("Users", foreign_keys=[created_by])
    Users_2 = relationship("Users", foreign_keys=[updated_by])


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

    Users = relationship("Users", foreign_keys=[created_by])
    Users_2 = relationship("Users", foreign_keys=[updated_by])

