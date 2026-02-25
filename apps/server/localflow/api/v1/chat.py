from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..deps import get_db, get_llm
from ...storage.models import Conversation, Message, Draft
from ...domain.enums import DraftStatus
from ...services.approval_service import ApprovalService

router = APIRouter()

class ChatIn(BaseModel):
    conversation_id: str | None = None
    mode: str = "email"
    message: str

@router.post("/chat")
async def chat(inp: ChatIn, db: Session = Depends(get_db), llm=Depends(get_llm)):
    # Create or load conversation
    if inp.conversation_id:
        conv = db.get(Conversation, inp.conversation_id)
        if not conv:
            raise ValueError("Conversation not found")
    else:
        conv = Conversation(title="New chat")
        db.add(conv)
        db.commit()
        db.refresh(conv)

    db.add(Message(conversation_id=conv.id, role="user", content=inp.message))
    db.commit()

    out = await llm.generate_draft(mode=inp.mode, user_message=inp.message)

    draft = Draft(
        conversation_id=conv.id,
        type=out.draft.type,
        title=out.draft.title,
        content=out.draft.content,
        status=DraftStatus.drafting.value,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)

    if out.tool_plan:
        ApprovalService(db).upsert_tool_plan(draft, out.tool_plan.model_dump())

    db.add(Message(conversation_id=conv.id, role="assistant", content=out.assistant_message))
    db.commit()

    return {
        "conversation_id": conv.id,
        "assistant_message": out.assistant_message,
        "draft": {
            "id": draft.id,
            "type": draft.type,
            "title": draft.title,
            "content": draft.content,
            "status": draft.status,
        },
        "tool_plan": out.tool_plan.model_dump() if out.tool_plan else None,
    }