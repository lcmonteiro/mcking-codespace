"""Application settings loaded from environment / .env file."""
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Server ────────────────────────────────────────────────────────────────
    APP_NAME: str = "LLM Proxy"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./llm_proxy.db"
    DB_ECHO: bool = False

    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    ADMIN_API_KEY: str = "admin-secret-change-me"          # for management endpoints
    TOKEN_HASH_ALGORITHM: str = "HS256"

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    GLOBAL_RATE_LIMIT_RPM: int = 600
    REDIS_URL: Optional[str] = None                        # None = in-memory fallback

    # ── Provider key rotation ─────────────────────────────────────────────────
    KEY_ROTATION_STRATEGY: str = "round_robin"             # round_robin | priority | random

    # ── Observability ─────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    ENABLE_METRICS: bool = True

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: List[str] = ["*"]


settings = Settings()
