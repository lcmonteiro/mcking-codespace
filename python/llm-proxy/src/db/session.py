"""Database engine, session factory, and helpers."""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.db.models import Base
from config.settings import settings


# ─── Engine ───────────────────────────────────────────────────────────────────

def _make_engine():
    url = settings.DATABASE_URL
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
    return create_async_engine(url, echo=settings.DB_ECHO, **kwargs)


engine = _make_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def init_db() -> None:
    """Create all tables (dev / testing convenience)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def db_context() -> AsyncGenerator[AsyncSession, None]:
    """Async-context-manager version for use outside FastAPI."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
