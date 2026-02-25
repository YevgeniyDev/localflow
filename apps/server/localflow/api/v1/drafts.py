from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..deps import get_db
from ...domain.enums import DraftStatus
from ...services.approval_service import ApprovalService
from ...storage.models import Draft
from ..schemas import ErrorOut
from .schemas import DraftApproveOut, DraftUpdateIn, DraftUpdateOut

router = APIRouter()


@router.post(
    "/drafts/{draft_id}/update",
    response_model=DraftUpdateOut,
    responses={404: {"model": ErrorOut}, 409: {"model": ErrorOut}},
)
def update_draft(draft_id: str, inp: DraftUpdateIn, db: Session = Depends(get_db)):
    d = db.get(Draft, draft_id)
    if not d:
        raise HTTPException(status_code=404, detail="Draft not found")
    if d.status != DraftStatus.drafting.value:
        raise HTTPException(status_code=409, detail="Draft is locked (approved)")

    if inp.title is not None:
        d.title = inp.title
    if inp.content is not None:
        d.content = inp.content

    db.commit()
    return {"ok": True}


@router.post(
    "/drafts/{draft_id}/approve",
    response_model=DraftApproveOut,
    responses={404: {"model": ErrorOut}, 409: {"model": ErrorOut}},
)
def approve_draft(draft_id: str, db: Session = Depends(get_db)):
    d = db.get(Draft, draft_id)
    if not d:
        raise HTTPException(status_code=404, detail="Draft not found")
    try:
        approval = ApprovalService(db).approve(d)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"approval_id": approval.id}
