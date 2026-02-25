from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..deps import get_db
from ...storage.models import Draft
from ...domain.enums import DraftStatus
from ...services.approval_service import ApprovalService

router = APIRouter()

class DraftUpdateIn(BaseModel):
    title: str | None = None
    content: str | None = None

@router.post("/drafts/{draft_id}/update")
def update_draft(draft_id: str, inp: DraftUpdateIn, db: Session = Depends(get_db)):
    d = db.get(Draft, draft_id)
    if not d:
        raise ValueError("Draft not found")
    if d.status != DraftStatus.drafting.value:
        raise ValueError("Draft is locked (approved)")

    if inp.title is not None:
        d.title = inp.title
    if inp.content is not None:
        d.content = inp.content

    db.commit()
    return {"ok": True}

@router.post("/drafts/{draft_id}/approve")
def approve_draft(draft_id: str, db: Session = Depends(get_db)):
    d = db.get(Draft, draft_id)
    if not d:
        raise ValueError("Draft not found")
    approval = ApprovalService(db).approve(d)
    return {"approval_id": approval.id}