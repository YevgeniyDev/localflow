import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base
from ..domain.enums import DraftStatus, DraftType, ExecutionStatus

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(200), default="New chat")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")
    drafts: Mapped[list["Draft"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

class Draft(Base):
    __tablename__ = "drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    type: Mapped[str] = mapped_column(String(50), default=DraftType.email.value)
    title: Mapped[str] = mapped_column(String(200), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(50), default=DraftStatus.drafting.value)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="drafts")
    tool_plan: Mapped["ToolPlan | None"] = relationship(back_populates="draft", uselist=False, cascade="all, delete-orphan")
    approvals: Mapped[list["Approval"]] = relationship(back_populates="draft", cascade="all, delete-orphan")

class ToolPlan(Base):
    __tablename__ = "tool_plans"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    draft_id: Mapped[str] = mapped_column(ForeignKey("drafts.id"), unique=True, index=True)

    json_canonical: Mapped[str] = mapped_column(Text)     # canonical JSON string (sorted keys)
    content_hash: Mapped[str] = mapped_column(String(64)) # sha256(canonical JSON bytes)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    draft: Mapped["Draft"] = relationship(back_populates="tool_plan")

class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    draft_id: Mapped[str] = mapped_column(ForeignKey("drafts.id"), index=True)

    draft_hash: Mapped[str] = mapped_column(String(64))
    toolplan_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    draft: Mapped["Draft"] = relationship(back_populates="approvals")
    executions: Mapped[list["Execution"]] = relationship(back_populates="approval", cascade="all, delete-orphan")

class Execution(Base):
    __tablename__ = "executions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    approval_id: Mapped[str] = mapped_column(ForeignKey("approvals.id"), index=True)

    tool_name: Mapped[str] = mapped_column(String(100))
    request_json: Mapped[str] = mapped_column(Text)  # canonical JSON
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(30), default=ExecutionStatus.pending.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    approval: Mapped["Approval"] = relationship(back_populates="executions")