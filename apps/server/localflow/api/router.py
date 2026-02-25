from __future__ import annotations

from fastapi import APIRouter

from localflow.api.v1.health import router as health_router
from localflow.api.v1.chat import router as chat_router
from localflow.api.v1.drafts import router as drafts_router
from localflow.api.v1.executions import router as executions_router
from localflow.api.v1.conversations import router as conversations_router

router = APIRouter()

# Everything versioned under /v1
v1 = APIRouter(prefix="/v1")

v1.include_router(health_router)
v1.include_router(chat_router)
v1.include_router(drafts_router)
v1.include_router(executions_router)
v1.include_router(conversations_router)

router.include_router(v1)