from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from localflow.api.router import router as api_router
from localflow.core.config import Settings
from localflow.llm.gemini import GeminiProvider
from localflow.llm.ollama import OllamaProvider
from localflow.llm.prompt_manager import PromptManager
from localflow.rag import RagService
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

    # Local RAG service (permissioned local file retrieval)
    app.state.rag_service = RagService(
        store_dir=getattr(settings, "rag_store_dir", ".localflow_rag"),
        chunk_size=int(getattr(settings, "rag_chunk_size", 1200)),
        chunk_overlap=int(getattr(settings, "rag_chunk_overlap", 200)),
        embedding_dim=int(getattr(settings, "rag_embedding_dim", 384)),
    )

    # LLM provider (swappable)
    provider = (getattr(settings, "llm_provider", "ollama") or "ollama").strip().lower()
    timeout_s = float(getattr(settings, "llm_timeout_s", 120))

    if provider == "gemini":
        api_key = getattr(settings, "gemini_api_key", None)
        model = getattr(settings, "gemini_model", None)
        if not api_key:
            raise RuntimeError("gemini_api_key is not configured. Set it in Settings / env.")
        if not model:
            raise RuntimeError("gemini_model is not configured. Set it in Settings / env.")
        app.state.llm_provider = GeminiProvider(
            client=http_client,
            prompt_manager=app.state.prompt_manager,
            api_key=api_key,
            model=model,
            timeout_s=timeout_s,
        )
    elif provider == "ollama":
        base_url = getattr(settings, "ollama_base_url", "http://127.0.0.1:11434")
        model = getattr(settings, "ollama_model", None)
        if not model:
            raise RuntimeError("ollama_model is not configured. Set it in Settings / env.")
        app.state.llm_provider = OllamaProvider(
            client=http_client,
            prompt_manager=app.state.prompt_manager,
            base_url=base_url,
            model=model,
            timeout_s=timeout_s,
        )
    else:
        raise RuntimeError(f"Unsupported llm_provider: {provider}")

    try:
        yield
    finally:
        await http_client.aclose()


app = FastAPI(title="LocalFlow Assistant", lifespan=lifespan)


def _error_code(status_code: int) -> str:
    if status_code == 400:
        return "INVALID_REQUEST"
    if status_code == 401:
        return "UNAUTHORIZED"
    if status_code == 403:
        return "FORBIDDEN"
    if status_code == 404:
        return "NOT_FOUND"
    if status_code == 409:
        return "CONFLICT"
    if status_code == 422:
        return "VALIDATION_ERROR"
    if status_code >= 500:
        return "INTERNAL_ERROR"
    return "ERROR"


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail, "error_code": _error_code(exc.status_code)},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "error_code": _error_code(422),
            "errors": exc.errors(),
        },
    )


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "error_code": _error_code(400)},
    )


# Dev CORS for Vite
settings_for_cors = Settings()
dev_origins = getattr(settings_for_cors, "cors_origins", None) or [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=dev_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"ok": True, "hint": "Try /v1/health"}


app.include_router(api_router)
