from fastapi import APIRouter, Request

from ...core.config import settings
from .schemas import HealthOut

router = APIRouter()


@router.get("/health", response_model=HealthOut)
def health(request: Request):
    return {
        "app": settings.app_name,
        "env": settings.env,
        "llm_provider": settings.llm_provider,
        "ollama_base_url": settings.ollama_base_url,
        "ollama_model": settings.ollama_model,
        "has_llm_provider": request.app.state.llm_provider is not None,
    }
