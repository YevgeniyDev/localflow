from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from localflow.llm.prompt_manager import PromptManager
from localflow.llm.schemas import DraftOut, DraftResponse, ToolPlanOut

log = logging.getLogger("localflow.llm")

_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)
_LEADING_TITLE_RE = re.compile(r"^\s*(subject|title)\s*[:\-]\s*(.+?)\s*$", re.IGNORECASE)
_MAX_HISTORY_MESSAGES = 24
_MAX_HISTORY_CHARS = 1600

_GENERAL_ASSISTANT_RULES = (
    "You are a contextual conversational AI assistant.\n"
    "Use conversation history to answer naturally across mixed tasks in one thread.\n"
    "When asked to draft/write content, produce strong draft.content.\n"
    "When asked a general question, answer directly in assistant_message and include a short supporting draft.\n"
    "Do not ask unnecessary clarifying questions.\n"
)

def _extract_first_json_object(text: str) -> Optional[str]:
    if not text:
        return None
    m = _JSON_OBJ_RE.search(text)
    return m.group(0) if m else None


def _safe_truncate(s: str, n: int = 900) -> str:
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[:n] + "..."


def _clip(s: str, n: int = _MAX_HISTORY_CHARS) -> str:
    s = "" if s is None else str(s).strip()
    return s if len(s) <= n else s[:n] + "..."


def _format_history(history: Optional[List[Dict[str, str]]]) -> str:
    if not history:
        return "(no prior messages)"

    tail = history[-_MAX_HISTORY_MESSAGES:]
    lines: List[str] = []
    for msg in tail:
        role = str(msg.get("role") or "user").strip().lower()
        if role not in {"user", "assistant"}:
            role = "user"
        content = _clip(str(msg.get("content") or ""))
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "(no prior messages)"


def _synthesize_fallback_draft(assistant_message: str) -> DraftOut:
    title = "Conversation notes"
    body = "Summary:\n- [Main point]\n- [Next step]\n"

    if assistant_message and assistant_message.strip():
        body = f"Assistant response:\n{assistant_message.strip()}\n\n---\n\n{body}"

    return DraftOut(title=title, content=body)


def _normalize_title_content(draft: DraftOut) -> DraftOut:
    title = (draft.title or "").strip()
    content = draft.content or ""
    lines = content.splitlines()
    if not lines:
        return draft

    first_idx = 0
    while first_idx < len(lines) and not lines[first_idx].strip():
        first_idx += 1
    if first_idx >= len(lines):
        return draft

    first_line = lines[first_idx]
    m = _LEADING_TITLE_RE.match(first_line)
    if not m:
        return draft

    extracted = m.group(2).strip()
    if not extracted:
        return draft

    if not title:
        title = extracted

    if title.lower() == extracted.lower():
        remainder = lines[:first_idx] + lines[first_idx + 1 :]
        while remainder and not remainder[0].strip():
            remainder.pop(0)
        content = "\n".join(remainder).strip()

    draft.title = title
    draft.content = content
    return draft


def _recover_content_from_assistant_message(assistant_message: str) -> str:
    text = (assistant_message or "").strip()
    if not text:
        return ""

    lower = text.lower()
    markers = [
        "here it is:",
        "draft:",
        "linkedin post draft:",
    ]
    start = -1
    for marker in markers:
        idx = lower.find(marker)
        if idx != -1:
            start = idx + len(marker)
            break

    recovered = text[start:].strip() if start != -1 else text
    return recovered


class OllamaProvider:
    """
    Ollama provider that returns a DraftResponse.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        prompt_manager: PromptManager,
        base_url: str,
        model: str,
        timeout_s: float = 120.0,
        max_repair_attempts: int = 2,
    ) -> None:
        self._client = client
        self._pm = prompt_manager
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_s = timeout_s
        self._max_repairs = max_repair_attempts

    async def generate_draft(
        self,
        user_message: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> DraftResponse:
        system = self._pm.get_system()
        repair_prompt = self._pm.get_repair()
        history_block = _format_history(history)

        prompt = "\n\n".join(
            [
                system,
                _GENERAL_ASSISTANT_RULES,
                "Conversation history:",
                history_block,
                "User message:",
                user_message,
                "",
                "Return ONLY valid JSON with keys: assistant_message, draft, tool_plan.",
                "assistant_message must be non-empty and directly answer the latest user message.",
                "draft must be an object with non-empty content; title may be empty when not needed.",
                "tool_plan is optional; use null when no concrete tool actions are needed.",
            ]
        )

        parsed: Optional[DraftResponse] = None

        for attempt in range(1, self._max_repairs + 2):
            raw = await self._ollama_generate(prompt, force_json=True)

            parsed = self._parse_draft_response(raw)
            if parsed and parsed.draft and not (parsed.draft.content or "").strip():
                parsed.draft.content = _recover_content_from_assistant_message(parsed.assistant_message)
            if parsed and parsed.draft and parsed.draft.content.strip():
                parsed.draft = _normalize_title_content(parsed.draft)
                if not (parsed.assistant_message or "").strip():
                    parsed.assistant_message = parsed.draft.content[:300].strip()
                return parsed

            log.warning("LLM output invalid (attempt %s): draft missing/empty", attempt)
            log.warning("RAW OUTPUT (attempt %s): %r", attempt, _safe_truncate(raw))

            prompt = "\n\n".join(
                [
                    system,
                    repair_prompt,
                    _GENERAL_ASSISTANT_RULES,
                    "Conversation history:",
                    history_block,
                    "The previous output was invalid because draft was null or empty.",
                    "You MUST output JSON with a non-null draft object containing non-empty content.",
                    "You MUST keep assistant_message non-empty and relevant to the latest user message.",
                    "Previous output:",
                    raw,
                    "Original user message:",
                    user_message,
                ]
            )

        assistant_msg = ""
        if parsed:
            assistant_msg = parsed.assistant_message or ""

        return DraftResponse(
            assistant_message=(assistant_msg or "").strip() or "I can help with that.",
            draft=_synthesize_fallback_draft(assistant_msg),
            tool_plan=None,
        )

    async def generate(
        self,
        user_message: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> DraftResponse:
        return await self.generate_draft(user_message=user_message, history=history)

    async def _ollama_generate(self, prompt: str, force_json: bool) -> str:
        url = f"{self._base_url}/api/generate"
        payload: Dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
        }
        if force_json:
            payload["format"] = "json"

        r = await self._client.post(url, json=payload, timeout=self._timeout_s)
        r.raise_for_status()
        data = r.json()
        return str(data.get("response") or "")

    def _parse_draft_response(self, raw: str) -> Optional[DraftResponse]:
        if not raw or not raw.strip():
            return None

        text = raw.strip()

        if not (text.startswith("{") and text.endswith("}")):
            extracted = _extract_first_json_object(text)
            if extracted:
                text = extracted

        try:
            obj = json.loads(text)
        except Exception:
            return None

        if not isinstance(obj, dict):
            return None

        assistant_message = str(obj.get("assistant_message") or "")

        draft = None
        if isinstance(obj.get("draft"), dict):
            try:
                draft = DraftOut.model_validate(obj["draft"])
            except Exception:
                draft = None

        tool_plan = None
        if isinstance(obj.get("tool_plan"), dict):
            try:
                tool_plan = ToolPlanOut.model_validate(obj["tool_plan"])
            except Exception:
                tool_plan = None

        return DraftResponse(
            assistant_message=assistant_message,
            draft=draft,
            tool_plan=tool_plan,
        )
