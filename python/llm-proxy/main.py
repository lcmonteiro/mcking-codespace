"""
LLM Proxy — FastAPI application entry point.
"""
import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config.settings import settings
from src.db.session import init_db
from src.routes.admin import router as admin_router
from src.routes.inference import router as inference_router

logger = structlog.get_logger()


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting LLM Proxy", version=settings.APP_VERSION)
    await init_db()
    yield
    logger.info("Shutting down LLM Proxy")


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## LLM Proxy

A multi-provider LLM proxy built on LangChain / LangGraph.

### Key features
- **Model abstractions** — clients reference `coding`, `chat`, `reasoning`, etc.;  
  the proxy resolves to the real provider model.
- **Access tokens with budgets** — fixed, time-based, or unlimited token budgets  
  with optional expiry dates and per-abstraction restrictions.
- **Multi-key rotation** — register multiple API keys per provider (from different  
  owners); keys are rotated via round-robin, priority, or random strategies.
- **Full audit log** — every request is recorded with token counts and latency.

### Authentication
- **Inference endpoints** — `Authorization: Bearer <proxy_token>`
- **Admin endpoints** — `Authorization: Bearer <ADMIN_API_KEY>`
""",
    lifespan=lifespan,
)

# ─── CORS ─────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────────────────────────

app.include_router(inference_router)
app.include_router(admin_router)


# ─── Global error handler ─────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Meta"])
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}


@app.get("/", tags=["Meta"])
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs":    "/docs",
    }
