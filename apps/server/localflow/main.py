from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from localflow.api.router import router as api_router
from localflow.core.config import Settings
from localflow.llm.ollama import OllamaProvider
from localflow.llm.prompt_manager import PromptManager
from localflow.tools import build_registry

log = logging.getLogger("localflow")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Create and store app-wide singletons here.
    Windows-first dev: keep things deterministic and easy to reason about.
    """
    settings = Settings()
    app.state.settings = settings

    # Shared HTTP client for Ollama + future connectors
    http_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))
    app.state.http_client = http_client

    # Prompt pack manager (no hardcoded prompt logic in code)
    # Settings should point at the prompt pack directory (e.g. .../prompt_packs/default)
    # If your Settings uses a different field name, adjust it here.
    prompt_dir = getattr(settings, "prompt_pack_dir", None) or getattr(
        settings, "prompt_pack_path", None
    ) or getattr(settings, "prompt_pack", None)
    if not prompt_dir:
        # Fallback to the default pack path relative to package if settings not present.
        # (Keeps server booting in dev.)
        prompt_dir = "localflow/llm/prompt_packs/default"

    app.state.prompt_manager = PromptManager(prompt_dir)

    # Tool registry (gated execution later)
    app.state.tool_registry = build_registry()

    # LLM provider (swappable)
    base_url = getattr(settings, "ollama_base_url", "http://127.0.0.1:11434")
    model = getattr(settings, "ollama_model", None)
    if not model:
        raise RuntimeError("ollama_model is not configured. Set it in Settings / env.")

    app.state.llm_provider = OllamaProvider(
        client=http_client,
        prompt_manager=app.state.prompt_manager,
        base_url=base_url,
        model=model,
    )

    try:
        yield
    finally:
        await http_client.aclose()


app = FastAPI(title="LocalFlow Assistant", lifespan=lifespan)

# Dev CORS for Vite
settings_for_cors = Settings()
dev_origins = getattr(settings_for_cors, "cors_origins", None) or [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=dev_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root hint endpoint
@app.get("/")
def root():
    return {"ok": True, "hint": "Try /v1/health"}

# API routes
app.include_router(api_router)