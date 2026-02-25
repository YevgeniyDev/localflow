from contextlib import asynccontextmanager
from fastapi.responses import JSONResponse
import httpx
from fastapi import FastAPI
from .api.router import router as v1_router
from .core.logging import configure_logging
from .core.middleware import CorrelationIdMiddleware
from .storage.db import Base, engine
from .tools import build_registry
from .llm.ollama import OllamaProvider
from .core.config import settings
from fastapi.responses import JSONResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Logging
    configure_logging()

    # DB init (MVP). For production: use Alembic migrations.
    Base.metadata.create_all(bind=engine)

    # Shared HTTP client (connection reuse)
    http_client = httpx.AsyncClient(timeout=settings.llm_timeout_s)

    # Singletons
    app.state.tool_registry = build_registry()
    app.state.llm_provider = OllamaProvider(client=http_client)

    try:
        yield
    finally:
        await http_client.aclose()

def create_app() -> FastAPI:
    app = FastAPI(title="LocalFlow Server", lifespan=lifespan)
    app.add_middleware(CorrelationIdMiddleware)
    app.include_router(v1_router)
    return app

app = create_app()

@app.get("/")
def root():
    return JSONResponse({"ok": True, "hint": "Try /v1/health"})