import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, func, Boolean
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from app.infra.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(1024), nullable=False)
    role = Column(String(50), default="user", nullable=False)  # 'user' | 'admin'
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    memories = relationship("LongTermMemory", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="actor")
    widgets = relationship("Widget", back_populates="creator")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), nullable=False)  # 'system' | 'user' | 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")


class LongTermMemory(Base):
    __tablename__ = "long_term_memories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    memory_type = Column(String(100), nullable=False)  # 'episodic' | 'semantic' | 'procedural'
    content = Column(Text, nullable=False)
    embedding = Column(Vector(768), nullable=False)  # Fits standard embedding sizes like text-embedding-3-small or BGE-base
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="memories")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(100), nullable=False)  # e.g., 'memory_write', 'auth_login'
    target = Column(String(255), nullable=False)  # e.g., 'memory_id_xyz'
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    actor = relationship("User", back_populates="audit_logs")


class Widget(Base):
    __tablename__ = "widgets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    widget_id = Column(UUID(as_uuid=True), nullable=False, unique=True, default=uuid.uuid4)
    allowed_origins = Column(ARRAY(String), nullable=False)
    theme = Column(JSONB, nullable=False)  # e.g., {"primary_color": "#ff0000", ...}
    greeting = Column(String(255), nullable=True)
    enabled_tools = Column(ARRAY(String), nullable=False)  # e.g., ['classify_issue', ...]
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    creator = relationship("User", back_populates="widgets")
