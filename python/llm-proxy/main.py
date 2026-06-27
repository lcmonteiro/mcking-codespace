"""
LLM Proxy — FastAPI application entry point.

Serves the multi-provider LLM proxy built on LangChain / LangGraph.
"""
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config.settings import settings
from src.db.session import db_init
from src.routes.admin import router as admin_router
from src.routes.inference import router as inference_router

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


# ====================================================================================================
# Lifespan
# ====================================================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> None:
    """
    Application lifespan context manager.

    Runs startup logic (database initialisation) before yielding, and
    shutdown cleanup after.

    Args:
        app: The FastAPI application instance.
    """
    logger.info("Starting LLM Proxy", version=settings.APP_VERSION)
    await db_init()
    yield
    logger.info("Shutting down LLM Proxy")


# ====================================================================================================
# App
# ====================================================================================================

DESCRIPTION = """
## LLM Proxy

A multi-provider LLM proxy built on LangChain / LangGraph.

### Key features
- **Model abstractions** — clients reference ``coding``, ``chat``, ``reasoning``,
  etc.; the proxy resolves to the real provider model.
- **Access tokens with budgets** — fixed, time-based, or unlimited token budgets
  with optional expiry dates and per-abstraction restrictions.
- **Multi-key rotation** — register multiple API keys per provider (from
  different owners); keys are rotated via round-robin, priority, or random
  strategies.
- **Full audit log** — every request is recorded with token counts and latency.

### Authentication
- **Inference endpoints** — ``Authorization: Bearer <proxy_token>``
- **Admin endpoints** — ``Authorization: Bearer <ADMIN_API_KEY>``
"""

app = FastAPI(
    title       = settings.APP_NAME,
    version     = settings.APP_VERSION,
    description = DESCRIPTION,
    lifespan    = lifespan,
)


# ====================================================================================================
# CORS
# ====================================================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins  = settings.CORS_ORIGINS,
    allow_credentials = True,
    allow_methods  = ["*"],
    allow_headers  = ["*"],
)


# ====================================================================================================
# Routers
# ====================================================================================================

app.include_router(inference_router)
app.include_router(admin_router)


# ====================================================================================================
# Global error handler
# ====================================================================================================


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all exception handler that logs the error and returns a 500 JSON
    response.
    """
    logger.error("Unhandled exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code = 500,
        content     = {"detail": "Internal server error", "type": type(exc).__name__},
    )


# ====================================================================================================
# Health
# ====================================================================================================


@app.get("/health", tags=["Meta"])
async def health() -> Dict[str, Any]:
    """Return service health status and version."""
    return {"status": "ok", "version": settings.APP_VERSION}


@app.get("/", tags=["Meta"])
async def root() -> Dict[str, Any]:
    """Return service metadata including name, version, and docs link."""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs":    "/docs",
    }


# ====================================================================================================
# Entry point
# ====================================================================================================


def main() -> None:
    """Launch the LLM Proxy via uvicorn."""
    import uvicorn

    uvicorn.run(
        "main:app",
        host    = settings.HOST,
        port    = settings.PORT,
        reload  = settings.DEBUG,
        log_level = settings.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    logging.basicConfig(
        level   = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format  = "%(levelname)s %(message)s",
    )
    main()
