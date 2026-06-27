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


_engine = _make_engine()

_async_session_local = async_sessionmaker(
    bind=_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def db_init() -> None:
    """Create all tables (dev / testing convenience)."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def db_contex() -> AsyncGenerator[AsyncSession, None]:
    """Async-context-manager — provides a DB session with auto commit/rollback."""
    async with _async_session_local() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def db_get() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a session per request."""
    async with db_contex() as session:
        yield session
