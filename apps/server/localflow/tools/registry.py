from typing import Protocol, Any, Type
from pydantic import BaseModel

class Tool(Protocol):
    name: str
    InputModel: Type[BaseModel]
    risk: str  # "LOW" | "MEDIUM" | "HIGH"

    def validate(self, data: dict) -> BaseModel: ...
    def run(self, validated: BaseModel) -> dict[str, Any]: ...

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise ValueError(f"Unknown tool: {name}")
        return self._tools[name]