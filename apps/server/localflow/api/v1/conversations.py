from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func

from localflow.api.deps import get_db
from localflow.storage.models import Conversation, Message, Draft

router = APIRouter(tags=["conversations"])


class ConversationListItem(BaseModel):
    id: str
    created_at: datetime
    # Derived: last activity time (latest message time, else created_at)
    last_activity_at: datetime
    title: str = Field(..., description="Derived title for display")
    last_message_preview: str
    message_count: int
    latest_draft_id: Optional[str] = None


class ConversationListOut(BaseModel):
    items: List[ConversationListItem]
    total: int
    limit: int
    offset: int


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime


class DraftOut(BaseModel):
    id: str
    type: str
    title: str
    content: str
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class ConversationDetailOut(BaseModel):
    id: str
    created_at: datetime
    messages: List[MessageOut]
    latest_draft: Optional[DraftOut] = None


def _preview(text: str, n: int = 90) -> str:
    s = (text or "").strip().replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


def _derive_title(messages: List[Message]) -> str:
    for m in messages:
        if (m.role or "").lower() == "user" and (m.content or "").strip():
            s = m.content.strip().replace("\n", " ")
            return s if len(s) <= 60 else s[:60] + "…"
    return "Conversation"


@router.get("/conversations", response_model=ConversationListOut)
def list_conversations(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
) -> ConversationListOut:
    total = db.query(Conversation).count()

    # Compute last activity per conversation as max(Message.created_at)
    last_activity_subq = (
        db.query(
            Message.conversation_id.label("cid"),
            func.max(Message.created_at).label("last_activity_at"),
        )
        .group_by(Message.conversation_id)
        .subquery()
    )

    # Sort by last activity desc (NULLS LAST), fallback to conversation.created_at
    rows = (
        db.query(Conversation, last_activity_subq.c.last_activity_at)
        .outerjoin(last_activity_subq, last_activity_subq.c.cid == Conversation.id)
        .order_by(
            last_activity_subq.c.last_activity_at.desc().nullslast(),
            Conversation.created_at.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    items: List[ConversationListItem] = []
    for c, last_activity_at in rows:
        # Load first ~200 messages for title derivation
        msgs: List[Message] = (
            db.query(Message)
            .filter(Message.conversation_id == c.id)
            .order_by(Message.created_at.asc())
            .limit(200)
            .all()
        )

        last_msg: Optional[Message] = (
            db.query(Message)
            .filter(Message.conversation_id == c.id)
            .order_by(Message.created_at.desc())
            .first()
        )

        message_count = db.query(Message).filter(Message.conversation_id == c.id).count()

        latest_draft: Optional[Draft] = (
            db.query(Draft)
            .filter(Draft.conversation_id == c.id)
            .order_by(Draft.created_at.desc())
            .first()
        )

        items.append(
            ConversationListItem(
                id=c.id,
                created_at=c.created_at,
                last_activity_at=last_activity_at or c.created_at,
                title=_derive_title(msgs),
                last_message_preview=_preview(last_msg.content if last_msg else ""),
                message_count=message_count,
                latest_draft_id=(latest_draft.id if latest_draft else None),
            )
        )

    return ConversationListOut(items=items, total=total, limit=limit, offset=offset)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(
    conversation_id: str,
    message_limit: int = Query(500, ge=1, le=2000),
    db=Depends(get_db),
) -> ConversationDetailOut:
    c: Optional[Conversation] = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages: List[Message] = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .limit(message_limit)
        .all()
    )

    latest_draft: Optional[Draft] = (
        db.query(Draft)
        .filter(Draft.conversation_id == conversation_id)
        .order_by(Draft.created_at.desc())
        .first()
    )

    latest_draft_out: Optional[DraftOut] = None
    if latest_draft:
        latest_draft_out = DraftOut(
            id=latest_draft.id,
            type=getattr(latest_draft, "type", "assistant"),
            title=getattr(latest_draft, "title", "") or "",
            content=getattr(latest_draft, "content", "") or "",
            status=str(getattr(latest_draft, "status", "")),
            created_at=latest_draft.created_at,
            updated_at=getattr(latest_draft, "updated_at", None),
        )

    return ConversationDetailOut(
        id=c.id,
        created_at=c.created_at,
        messages=[
            MessageOut(id=m.id, role=m.role, content=m.content, created_at=m.created_at)
            for m in messages
        ],
        latest_draft=latest_draft_out,
    )
