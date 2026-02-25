from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorOut(BaseModel):
    detail: str
    error_code: str = Field(..., description="Stable machine-readable error code")
    errors: list[dict[str, Any]] | None = None
