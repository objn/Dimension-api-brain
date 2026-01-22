from typing import Any, Optional
import datetime
import uuid

from pgvector import Vector
from pgvector.sqlalchemy.vector import VECTOR
from sqlalchemy import DateTime, ForeignKeyConstraint, Integer, PrimaryKeyConstraint, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass


class NodeVector(Base):
    __tablename__ = 'NodeVector'
    __table_args__ = (
        PrimaryKeyConstraint('node_id', 'document_vector_chuck', name='NodeVector_pkey'),
    )

    node_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    document_vector_chuck: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_content_md_chuck: Mapped[Optional[str]] = mapped_column(Text)
    embedding: Mapped[Optional[Vector]] = mapped_column(VECTOR(1536))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)


class Roles(Base):
    __tablename__ = 'Roles'
    __table_args__ = (
        PrimaryKeyConstraint('role_id', name='Roles_pkey'),
    )

    role_id: Mapped[str] = mapped_column(String(16), primary_key=True)


class Users(Base):
    __tablename__ = 'Users'
    __table_args__ = (
        PrimaryKeyConstraint('user_id', name='Users_pkey'),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_display: Mapped[Optional[str]] = mapped_column(String(32))
    password: Mapped[Optional[str]] = mapped_column(String(255))
    first_name: Mapped[Optional[str]] = mapped_column(String(64))
    last_name: Mapped[Optional[str]] = mapped_column(String(64))
    email: Mapped[Optional[str]] = mapped_column(String(64))
    num_phone: Mapped[Optional[str]] = mapped_column(String(32))
    user_profile_file_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)

    Conversations: Mapped[list['Conversations']] = relationship('Conversations', foreign_keys='[Conversations.created_by]', back_populates='Users_')
    Conversations_: Mapped[list['Conversations']] = relationship('Conversations', foreign_keys='[Conversations.updated_by]', back_populates='Users1')


class Conversations(Base):
    __tablename__ = 'Conversations'
    __table_args__ = (
        ForeignKeyConstraint(['created_by'], ['Users.user_id'], name='FK_Conversations_created_by'),
        ForeignKeyConstraint(['updated_by'], ['Users.user_id'], name='FK_Conversations_updated_by'),
        PrimaryKeyConstraint('conversation_id', 'created_at', name='Conversations_pkey'),
        UniqueConstraint('conversation_id', name='Conversations_conversation_id_key')
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, primary_key=True)
    conversation_topic: Mapped[Optional[str]] = mapped_column(String(255))
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    Users_: Mapped[Optional['Users']] = relationship('Users', foreign_keys=[created_by], back_populates='Conversations')
    Users1: Mapped[Optional['Users']] = relationship('Users', foreign_keys=[updated_by], back_populates='Conversations_')
    Messages: Mapped[list['Messages']] = relationship('Messages', back_populates='conversation')


class Messages(Base):
    __tablename__ = 'Messages'
    __table_args__ = (
        ForeignKeyConstraint(['conversation_id'], ['Conversations.conversation_id'], name='Messages_conversation_id_fkey'),
        PrimaryKeyConstraint('message_id', name='Messages_pkey')
    )

    message_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    conversation_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    message_content: Mapped[Optional[str]] = mapped_column(Text)
    sender_role: Mapped[Optional[str]] = mapped_column(String(16))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    conversation: Mapped[Optional['Conversations']] = relationship('Conversations', back_populates='Messages')
