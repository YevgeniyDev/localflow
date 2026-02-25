from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..deps import get_db, get_llm
from ..schemas import ErrorOut
from .schemas import ChatIn, ChatOut
from ...domain.enums import DraftStatus
from ...services.approval_service import ApprovalService
from ...storage.models import Conversation, Draft, Message

router = APIRouter()


def _assistant_from_draft(title: str, content: str) -> str:
    c = (content or "").strip()
    if c:
        return c
    return (title or "").strip()


@router.post("/chat", response_model=ChatOut, responses={404: {"model": ErrorOut}, 502: {"model": ErrorOut}})
async def chat(inp: ChatIn, db: Session = Depends(get_db), llm=Depends(get_llm)):
    if inp.conversation_id:
        conv = db.get(Conversation, inp.conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conv = Conversation(title="New chat")
        db.add(conv)
        db.commit()
        db.refresh(conv)

    history_rows = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in history_rows]

    db.add(Message(conversation_id=conv.id, role="user", content=inp.message))
    db.commit()

    try:
        out = await llm.generate_draft(user_message=inp.message, history=history)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"LLM generation failed: {str(e)}")

    if not out.draft:
        raise HTTPException(status_code=502, detail="LLM generation failed: missing draft")

    assistant_message = _assistant_from_draft(out.draft.title or "", out.draft.content or "")

    draft = Draft(
        conversation_id=conv.id,
        type="assistant",
        title=out.draft.title or "",
        content=out.draft.content,
        status=DraftStatus.drafting.value,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)

    if out.tool_plan:
        tool_plan = out.tool_plan.model_dump()
        if isinstance(tool_plan.get("actions"), list):
            ApprovalService(db).upsert_tool_plan(draft, tool_plan)

    db.add(Message(conversation_id=conv.id, role="assistant", content=assistant_message))
    db.commit()

    return {
        "conversation_id": conv.id,
        "assistant_message": assistant_message,
        "draft": {
            "id": draft.id,
            "type": draft.type,
            "title": draft.title,
            "content": draft.content,
            "status": draft.status,
        },
        "tool_plan": out.tool_plan.model_dump() if out.tool_plan else None,
    }
