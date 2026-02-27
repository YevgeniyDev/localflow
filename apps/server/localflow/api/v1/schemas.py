from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ChatIn(BaseModel):
    conversation_id: str | None = None
    message: str
    force_file_search: bool = False


class DraftOut(BaseModel):
    id: str
    type: str
    title: str
    content: str
    status: str


class ChatOut(BaseModel):
    conversation_id: str
    assistant_message: str
    draft: DraftOut
    tool_plan: dict[str, Any] | None = None
    rag_hits: list[dict[str, Any]] | None = None
    rag_permission_required: bool = False
    rag_permission_message: str | None = None
    rag_suggested_path: str | None = None


class DraftUpdateIn(BaseModel):
    title: str | None = None
    content: str | None = None


class DraftUpdateOut(BaseModel):
    ok: bool


class DraftApproveOut(BaseModel):
    approval_id: str


class ExecuteIn(BaseModel):
    approval_id: str
    tool_name: str
    tool_input: dict[str, Any]
    confirmation: dict[str, Any] | None = None


class ExecuteOut(BaseModel):
    execution_id: str
    status: str
    result: Any


class HealthOut(BaseModel):
    app: str
    env: str
    llm_provider: str
    ollama_base_url: str
    ollama_model: str
    has_llm_provider: bool
