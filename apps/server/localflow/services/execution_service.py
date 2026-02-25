import json
import time
from datetime import datetime, timezone

import anyio
from sqlalchemy.orm import Session

from ..domain.hashing import sha256_text
from ..storage.models import Approval, Draft, Execution
from ..tools.registry import ToolRegistry


def canonical_json(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True)


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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

    def _is_tool_input_approved(self, draft: Draft, tool_name: str, tool_input: dict) -> bool:
        if not draft.tool_plan:
            return tool_input == {}

        try:
            tool_plan_obj = json.loads(draft.tool_plan.json_canonical)
        except Exception:
            return False

        wanted = canonical_json(tool_input)
        actions = tool_plan_obj.get("actions") if isinstance(tool_plan_obj, dict) else None
        if not isinstance(actions, list):
            return False

        for action in actions:
            if not isinstance(action, dict):
                continue
            if action.get("tool") != tool_name:
                continue
            params = action.get("params")
            if isinstance(params, dict) and canonical_json(params) == wanted:
                return True
        return False

    def _extract_action_ids(self, tool_input: dict) -> list[str]:
        actions = tool_input.get("actions") if isinstance(tool_input, dict) else None
        if not isinstance(actions, list):
            return []
        out: list[str] = []
        for action in actions:
            if not isinstance(action, dict):
                continue
            aid = action.get("id")
            if isinstance(aid, str) and aid.strip():
                out.append(aid.strip())
        return out

    def _enforce_tool_policy(self, tool_name: str, tool_input: dict, confirmation: dict | None) -> None:
        tool = self.tools.get(tool_name)
        risk = str(getattr(tool, "risk", "LOW")).upper()
        if risk == "LOW":
            return

        if not isinstance(confirmation, dict):
            raise ValueError("Confirmation payload is required for medium/high-risk tools")

        approved_actions_raw = confirmation.get("approved_actions")
        approved_actions = (
            {str(x).strip() for x in approved_actions_raw if str(x).strip()}
            if isinstance(approved_actions_raw, list)
            else set()
        )

        action_ids = self._extract_action_ids(tool_input)
        if action_ids and not all(aid in approved_actions for aid in action_ids):
            raise ValueError("Confirmation payload is missing one or more approved action ids")

        if risk == "HIGH" and not bool(confirmation.get("allow_high_risk")):
            raise ValueError("High-risk tool requires confirmation.allow_high_risk=true")

    async def execute(
        self,
        approval_id: str,
        tool_name: str,
        tool_input: dict,
        confirmation: dict | None = None,
    ) -> Execution:
        approval, draft = self._get_approval_and_draft(approval_id)

        if sha256_text(draft.content) != approval.draft_hash:
            raise ValueError("Draft content changed since approval")

        current_tp_hash = draft.tool_plan.content_hash if draft.tool_plan else None
        if current_tp_hash != approval.toolplan_hash:
            raise ValueError("Tool plan changed since approval")

        if not self._is_tool_input_approved(draft, tool_name, tool_input):
            raise ValueError("Tool input not approved by locked tool plan")

        self._enforce_tool_policy(tool_name, tool_input, confirmation)
        tool = self.tools.get(tool_name)
        validated = tool.validate(tool_input)

        request_canonical = canonical_json(tool_input)
        started_at = utc_iso()
        started_ns = time.perf_counter_ns()

        exe = Execution(
            approval_id=approval.id,
            tool_name=tool_name,
            request_json=canonical_json(
                {
                    "tool_input": tool_input,
                    "confirmation": confirmation,
                    "tool_input_hash": sha256_text(request_canonical),
                    "started_at": started_at,
                }
            ),
            status="RUNNING",
        )
        self.db.add(exe)
        self.db.commit()
        self.db.refresh(exe)

        try:
            result = await anyio.to_thread.run_sync(tool.run, validated)
            status = "SUCCEEDED"
            payload = {
                "output": result,
                "error": None,
            }
        except Exception as e:
            status = "FAILED"
            payload = {
                "output": None,
                "error": str(e),
            }

        duration_ms = int((time.perf_counter_ns() - started_ns) / 1_000_000)
        payload["meta"] = {
            "started_at": started_at,
            "finished_at": utc_iso(),
            "duration_ms": duration_ms,
        }

        exe.result_json = canonical_json(payload)
        exe.status = status
        self.db.commit()
        self.db.refresh(exe)
        return exe
