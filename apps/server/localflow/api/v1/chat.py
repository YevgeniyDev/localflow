import re
from urllib.parse import quote_plus, urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..deps import get_db, get_llm
from ..schemas import ErrorOut
from .schemas import ChatIn, ChatOut
from ...domain.enums import DraftStatus
from ...services.approval_service import ApprovalService
from ...storage.models import Conversation, Draft, Message

router = APIRouter()
_URL_RE = re.compile(r"https?://[^\s)]+", re.IGNORECASE)


def _assistant_from_draft(title: str, content: str) -> str:
    c = (content or "").strip()
    if c:
        return c
    return (title or "").strip()


def _normalize_search_query(query: str) -> str:
    q = (query or "").strip()
    prefixes = [
        "open ",
        "find ",
        "search ",
        "look up ",
        "please open ",
        "please find ",
        "please search ",
    ]
    lowered = q.lower()
    for p in prefixes:
        if lowered.startswith(p):
            q = q[len(p):].strip()
            lowered = q.lower()
            break
    q = q.replace("'s linkedin", " linkedin").replace(" profile", " ").strip()
    return " ".join(q.split())


def _sanitize_url(raw: str) -> str | None:
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    s = s.strip("<>[](){}\"'")
    s = s.rstrip(".,;:!?")
    if not s:
        return None
    parsed = urlparse(s)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return s


def _is_linkedin_profile_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    return "linkedin.com" in host and path.startswith("/in/")


def _normalize_tool_plan(user_message: str, tool_plan: dict | None) -> dict | None:
    if not isinstance(tool_plan, dict):
        return None
    actions = tool_plan.get("actions")
    if not isinstance(actions, list):
        return None

    user_has_explicit_url = bool(_URL_RE.search(user_message or ""))
    normalized_query = _normalize_search_query(user_message or "")
    has_browser_search = any(isinstance(a, dict) and a.get("tool") == "browser_search" for a in actions)

    normalized_actions: list[dict] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        tool = action.get("tool")
        params = action.get("params")
        if tool == "open_links" and isinstance(params, dict):
            urls = params.get("urls")
            if not isinstance(urls, list):
                continue
            sanitized_urls: list[str] = []
            for u in urls:
                su = _sanitize_url(u)
                if su and su not in sanitized_urls:
                    sanitized_urls.append(su)
            if not sanitized_urls:
                continue

            # Do not trust model-guessed LinkedIn profile slugs unless user supplied a URL.
            if (not user_has_explicit_url) and any(_is_linkedin_profile_url(u) for u in sanitized_urls):
                if normalized_query and not has_browser_search:
                    normalized_actions.append(
                        {
                            "tool": "browser_search",
                            "params": {"query": normalized_query, "max_results": 5, "headless": True},
                        }
                    )
                    has_browser_search = True
                if normalized_query:
                    sanitized_urls = [f"https://www.google.com/search?q={quote_plus(normalized_query)}"]

            normalized_actions.append({"tool": "open_links", "params": {"urls": sanitized_urls[:10]}})
            continue

        normalized_actions.append(action)

    if not normalized_actions:
        return None
    return {"actions": normalized_actions}


def _fallback_tool_plan(user_message: str, assistant_message: str) -> dict | None:
    text = f"{user_message}\n{assistant_message}".lower()
    # Only trust URLs explicitly provided by the user, not assistant-generated text.
    urls = _URL_RE.findall(user_message or "")

    if urls and ("open" in text or "browser" in text or "link" in text):
        unique_urls: list[str] = []
        seen: set[str] = set()
        for u in urls:
            if u not in seen:
                unique_urls.append(u)
                seen.add(u)
        return {
            "actions": [
                {
                    "tool": "open_links",
                    "params": {"urls": unique_urls[:10]},
                }
            ]
        }

    # Generic, non-domain-specific fallback for "open/find/search profile/page" intents
    # when user provided no explicit URL.
    wants_open = any(word in text for word in ["open", "find", "search", "profile", "page"])
    query = (user_message or "").strip()
    if wants_open and query:
        normalized_query = _normalize_search_query(query)
        actions: list[dict] = []
        actions.append(
            {
                "tool": "browser_search",
                "params": {"query": normalized_query, "max_results": 5, "headless": True},
            }
        )
        if any(word in text for word in ["open", "browser", "link"]):
            search_url = f"https://www.google.com/search?q={quote_plus(normalized_query)}"
            actions.append(
                {
                    "tool": "open_links",
                    "params": {"urls": [search_url]},
                }
            )
        return {"actions": actions}
    return None


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
    except Exception as e:
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

    tool_plan = out.tool_plan.model_dump() if out.tool_plan else None
    tool_plan = _normalize_tool_plan(inp.message, tool_plan)
    has_actions = isinstance((tool_plan or {}).get("actions"), list) and bool(tool_plan.get("actions"))
    if not has_actions:
        tool_plan = _fallback_tool_plan(inp.message, assistant_message)
        tool_plan = _normalize_tool_plan(inp.message, tool_plan)

    if isinstance((tool_plan or {}).get("actions"), list):
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
        "tool_plan": tool_plan,
    }
