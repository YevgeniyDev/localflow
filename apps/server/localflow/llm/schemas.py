from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator


class ToolActionOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tool: str
    params: Dict[str, Any] = Field(default_factory=dict)


class ToolPlanOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    actions: List[ToolActionOut] = Field(default_factory=list)

    @field_validator("actions")
    @classmethod
    def cap_actions(cls, v: List[ToolActionOut]) -> List[ToolActionOut]:
        # safety: avoid huge tool plans
        return v[:10]


class DraftOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(default="")
    content: str = Field(default="")

    @field_validator("title", "content")
    @classmethod
    def normalize_strings(cls, v: str) -> str:
        if v is None:
            return ""
        return str(v)


class DraftResponse(BaseModel):
    """
    LLM output schema.
    - draft may be null (model asks clarifying question), but backend will synthesize a draft.
    - tool_plan is optional and sanitized elsewhere.
    """
    model_config = ConfigDict(extra="ignore")

    assistant_message: str = Field(default="")
    draft: Optional[DraftOut] = None
    tool_plan: Optional[ToolPlanOut] = None

    @field_validator("assistant_message")
    @classmethod
    def normalize_assistant_message(cls, v: str) -> str:
        if v is None:
            return ""
        return str(v)