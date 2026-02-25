import json
import anyio
from sqlalchemy.orm import Session
from ..domain.hashing import sha256_text, sha256_bytes
from ..storage.models import Execution
from ..storage.models import Approval, Draft
from ..tools.registry import ToolRegistry

def canonical_json(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True)

class ExecutionService:
    def __init__(self, db: Session, tools: ToolRegistry):
        self.db = db
        self.tools = tools

    def _get_approval_and_draft(self, approval_id: str) -> tuple[Approval, Draft]:
        approval = self.db.get(Approval, approval_id)
        if not approval:
            raise ValueError("Approval not found")
        draft = self.db.get(Draft, approval.draft_id)
        if not draft:
            raise ValueError("Draft not found")
        return approval, draft

    async def execute(self, approval_id: str, tool_name: str, tool_input: dict) -> Execution:
        approval, draft = self._get_approval_and_draft(approval_id)

        # Verify draft hash matches approval
        if sha256_text(draft.content) != approval.draft_hash:
            raise ValueError("Draft content changed since approval")

        # Verify toolplan hash matches approval (if toolplan exists)
        current_tp_hash = draft.tool_plan.content_hash if draft.tool_plan else None
        if current_tp_hash != approval.toolplan_hash:
            raise ValueError("Tool plan changed since approval")

        # Validate tool input
        tool = self.tools.get(tool_name)
        validated = tool.validate(tool_input)

        exe = Execution(
            approval_id=approval.id,
            tool_name=tool_name,
            request_json=canonical_json(tool_input),
            status="RUNNING",
        )
        self.db.add(exe)
        self.db.commit()
        self.db.refresh(exe)

        try:
            # Run sync tool in a worker thread (safe for future I/O tools; later move to jobs/queue)
            result = await anyio.to_thread.run_sync(tool.run, validated)
            exe.result_json = canonical_json(result)
            exe.status = "SUCCEEDED"
        except Exception as e:
            exe.result_json = canonical_json({"error": str(e)})
            exe.status = "FAILED"

        self.db.commit()
        self.db.refresh(exe)
        return exe