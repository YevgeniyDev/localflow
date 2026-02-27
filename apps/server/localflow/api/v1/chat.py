import re
from pathlib import Path
from urllib.parse import quote_plus, urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..deps import get_db, get_llm, get_rag
from ..schemas import ErrorOut
from .schemas import ChatIn, ChatOut
from ...domain.enums import DraftStatus
from ...rag.service import RagService
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


def _looks_like_rag_request(user_message: str) -> bool:
    text = (user_message or "").strip().lower()
    if not text:
        return False
    rag_patterns = [
        r"\bfind\b.*\b(file|document|doc|pdf|folder)\b",
        r"\b(search|look up|lookup)\b.*\b(my|local|computer|pc|documents|files)\b",
        r"\bfrom\b.*\b(my|local)\b.*\b(files|documents|computer|pc)\b",
        r"\b(use|check|scan)\b.*\b(rag|documents|files|folder)\b",
        r"\b(open|read|summarize)\b.*\b(file|document|pdf|docx|txt)\b",
    ]
    return any(re.search(p, text) for p in rag_patterns)


def _looks_like_file_find_request(user_message: str) -> bool:
    text = (user_message or "").strip().lower()
    if not text:
        return False
    if re.search(r"\breadme\b", text):
        return True
    if re.search(r"\b\w+\.(txt|md|pdf|doc|docx|ppt|pptx|xls|xlsx|csv|json|py|ts|js|cpp|c|java|go|rs)\b", text):
        return True
    if re.search(r"\b(find|search|locate|lookup|look up)\b", text) and re.search(r"\b(for|about)\b", text):
        return True
    return bool(
        re.search(r"\b(find|search|locate|where)\b", text)
        and re.search(
            r"\b(file|files|folder|directory|photo|photos|picture|pictures|image|images|document|documents|pdf|docx|txt)\b",
            text,
        )
    )


def _extract_drive_hints(user_message: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in re.findall(r"\b([a-zA-Z]):\b", user_message or ""):
        drive = f"{m.upper()}:\\"
        if drive not in seen:
            seen.add(drive)
            out.append(drive)
    return out


def _extract_named_folder_hint(user_message: str) -> str | None:
    text = (user_message or "").lower()
    home = Path.home()
    candidates = [
        ("downloads", home / "Downloads"),
        ("documents", home / "Documents"),
        ("desktop", home / "Desktop"),
        ("pictures", home / "Pictures"),
        ("photos", home / "Pictures"),
        ("videos", home / "Videos"),
        ("music", home / "Music"),
    ]
    for key, path in candidates:
        if key in text and path.exists():
            return str(path)
    return None


def _default_docs_path() -> str:
    home = Path.home()
    return str(home)


def _rag_context_block(hits: list[dict]) -> str:
    if not hits:
        return ""
    lines = [
        "Local document context (use only if relevant; cite file paths inline when used):",
    ]
    for i, hit in enumerate(hits, start=1):
        path = str(hit.get("path") or "")
        snippet = str(hit.get("snippet") or "").replace("\n", " ").strip()
        lines.append(f"[RAG {i}] path={path}")
        lines.append(f"[RAG {i}] snippet={snippet[:700]}")
    lines.append("If context is not relevant, ignore it.")
    return "\n".join(lines)


@router.post("/chat", response_model=ChatOut, responses={404: {"model": ErrorOut}, 502: {"model": ErrorOut}})
async def chat(
    inp: ChatIn,
    db: Session = Depends(get_db),
    llm=Depends(get_llm),
    rag: RagService = Depends(get_rag),
):
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

    permissions = rag.list_permissions()
    force_file_search = bool(getattr(inp, "force_file_search", False))

    if (force_file_search or _looks_like_rag_request(inp.message)) and not permissions:
        assistant_message = (
            "Sure, but I need your permission to access local files first. "
            "Please approve folder access in the permission popup."
        )
        draft = Draft(
            conversation_id=conv.id,
            type="assistant",
            title="",
            content=assistant_message,
            status=DraftStatus.drafting.value,
        )
        db.add(draft)
        db.add(Message(conversation_id=conv.id, role="assistant", content=assistant_message))
        db.commit()
        db.refresh(draft)
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
            "tool_plan": None,
            "rag_hits": [],
            "rag_permission_required": True,
            "rag_permission_message": assistant_message,
            "rag_suggested_path": _default_docs_path(),
        }

    if _looks_like_file_find_request(inp.message) and not force_file_search:
        assistant_message = (
            "Please turn on File Search mode and select allowed folders/disks to search. "
            "Then ask your file query again."
        )
        draft = Draft(
            conversation_id=conv.id,
            type="assistant",
            title="",
            content=assistant_message,
            status=DraftStatus.drafting.value,
        )
        db.add(draft)
        db.add(Message(conversation_id=conv.id, role="assistant", content=assistant_message))
        db.commit()
        db.refresh(draft)
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
            "tool_plan": None,
            "rag_hits": [],
            "rag_permission_required": False,
            "rag_permission_message": None,
            "rag_suggested_path": None,
        }

    if force_file_search or _looks_like_file_find_request(inp.message):
        folder_hint = _extract_named_folder_hint(inp.message)
        if folder_hint and not rag.is_path_allowed(folder_hint):
            assistant_message = (
                f"Sure, but I need your permission to access {folder_hint} first. "
                "Please approve folder access in the permission popup."
            )
            draft = Draft(
                conversation_id=conv.id,
                type="assistant",
                title="",
                content=assistant_message,
                status=DraftStatus.drafting.value,
            )
            db.add(draft)
            db.add(Message(conversation_id=conv.id, role="assistant", content=assistant_message))
            db.commit()
            db.refresh(draft)
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
                "tool_plan": None,
                "rag_hits": [],
                "rag_permission_required": True,
                "rag_permission_message": assistant_message,
                "rag_suggested_path": folder_hint,
            }

        drive_hints = _extract_drive_hints(inp.message)
        if drive_hints:
            permission_roots = [p.lower() for p in permissions]
            needed = [d for d in drive_hints if not any(r.startswith(d.lower()) for r in permission_roots)]
            if needed:
                assistant_message = (
                    f"Sure, but I need your permission to access {needed[0]} first. "
                    "Please approve folder access in the permission popup."
                )
                draft = Draft(
                    conversation_id=conv.id,
                    type="assistant",
                    title="",
                    content=assistant_message,
                    status=DraftStatus.drafting.value,
                )
                db.add(draft)
                db.add(Message(conversation_id=conv.id, role="assistant", content=assistant_message))
                db.commit()
                db.refresh(draft)
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
                    "tool_plan": None,
                    "rag_hits": [],
                    "rag_permission_required": True,
                    "rag_permission_message": assistant_message,
                    "rag_suggested_path": needed[0],
                }

        file_roots = [folder_hint] if folder_hint and rag.is_path_allowed(folder_hint) else None
        file_hits = rag.find_files(inp.message, top_k=8, roots=file_roots)
        rag_payload = [{"path": h.path, "score": round(h.score, 4), "snippet": h.snippet} for h in file_hits]
        if file_hits:
            assistant_message = "I found these matching local paths:\n" + "\n".join(
                f"- {h.path}" for h in file_hits
            )
        else:
            assistant_message = (
                "I searched your approved local folders but couldn't find a clear match. "
                "Try adding more details like filename, extension, or parent folder."
            )

        draft = Draft(
            conversation_id=conv.id,
            type="assistant",
            title="",
            content=assistant_message,
            status=DraftStatus.drafting.value,
        )
        db.add(draft)
        db.add(Message(conversation_id=conv.id, role="assistant", content=assistant_message))
        db.commit()
        db.refresh(draft)
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
            "tool_plan": None,
            "rag_hits": rag_payload,
            "rag_permission_required": False,
            "rag_permission_message": None,
            "rag_suggested_path": None,
        }

    rag_hits = rag.search(inp.message, top_k=4)
    llm_message = inp.message
    if rag_hits:
        rag_payload = [{"path": h.path, "score": round(h.score, 4), "snippet": h.snippet} for h in rag_hits]
        llm_message = f"{inp.message}\n\n{_rag_context_block(rag_payload)}"
    else:
        rag_payload = []

    try:
        out = await llm.generate_draft(user_message=llm_message, history=history)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM generation failed: {str(e)}")

    if not out.draft:
        raise HTTPException(status_code=502, detail="LLM generation failed: missing draft")

    assistant_message = _assistant_from_draft(out.draft.title or "", out.draft.content or "")
    if rag_payload:
        seen_paths: set[str] = set()
        source_paths: list[str] = []
        for hit in rag_payload:
            p = str(hit.get("path") or "").strip()
            if p and p not in seen_paths:
                seen_paths.add(p)
                source_paths.append(p)
            if len(source_paths) >= 4:
                break
        if source_paths:
            assistant_message = (
                f"{assistant_message}\n\nSources:\n"
                + "\n".join(f"- {p}" for p in source_paths)
            )

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
        "rag_hits": rag_payload,
        "rag_permission_required": False,
        "rag_permission_message": None,
        "rag_suggested_path": None,
    }
