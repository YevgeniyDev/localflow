from pydantic import BaseModel, Field
from typing import Literal, Any

DraftKind = Literal["email", "routine", "code", "linkedin"]

class DraftOut(BaseModel):
    type: DraftKind
    title: str = ""
    content: str

class ToolAction(BaseModel):
    tool: Literal["open_links"]  # later: "search", "playwright"
    risk: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    params: dict[str, Any] = Field(default_factory=dict)

class ToolPlanOut(BaseModel):
    actions: list[ToolAction] = Field(default_factory=list)

class DraftResponse(BaseModel):
    assistant_message: str
    draft: DraftOut
    tool_plan: ToolPlanOut | None = None