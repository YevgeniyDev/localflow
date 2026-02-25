from fastapi import APIRouter
from .v1.chat import router as chat
from .v1.drafts import router as drafts
from .v1.executions import router as executions
from .v1.health import router as health

router = APIRouter(prefix="/v1")
router.include_router(health, tags=["health"])
router.include_router(chat, tags=["chat"])
router.include_router(drafts, tags=["drafts"])
router.include_router(executions, tags=["executions"])