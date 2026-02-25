from fastapi import Depends, Request
from sqlalchemy.orm import Session
from ..storage.db import SessionLocal
from ..llm.provider import LLMProvider
from ..tools.registry import ToolRegistry

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_llm(request: Request) -> LLMProvider:
    return request.app.state.llm_provider

def get_tools(request: Request) -> ToolRegistry:
    return request.app.state.tool_registry