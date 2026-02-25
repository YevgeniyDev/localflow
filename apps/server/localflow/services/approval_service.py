import json
from sqlalchemy.orm import Session
from ..domain.hashing import sha256_text, sha256_bytes
from ..domain.enums import DraftStatus
from ..storage.models import Approval, ToolPlan, Draft

def canonical_json(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True)

class ApprovalService:
    def __init__(self, db: Session):
        self.db = db

    def upsert_tool_plan(self, draft: Draft, tool_plan_obj: dict) -> ToolPlan:
        if draft.status != DraftStatus.drafting.value:
            raise ValueError("Draft is locked")

        canon = canonical_json(tool_plan_obj)
        h = sha256_bytes(canon.encode("utf-8"))

        if draft.tool_plan:
            draft.tool_plan.json_canonical = canon
            draft.tool_plan.content_hash = h
            tp = draft.tool_plan
        else:
            tp = ToolPlan(draft_id=draft.id, json_canonical=canon, content_hash=h)
            self.db.add(tp)

        self.db.commit()
        self.db.refresh(tp)
        return tp

    def approve(self, draft: Draft) -> Approval:
        if draft.status != DraftStatus.drafting.value:
            raise ValueError("Draft already locked")

        draft_hash = sha256_text(draft.content)
        toolplan_hash = draft.tool_plan.content_hash if draft.tool_plan else None

        approval = Approval(draft_id=draft.id, draft_hash=draft_hash, toolplan_hash=toolplan_hash)
        draft.status = DraftStatus.approved_locked.value

        self.db.add(approval)
        self.db.commit()
        self.db.refresh(approval)
        return approval