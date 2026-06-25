"""
SQLAlchemy ORM models for the LLM Proxy.
"""
from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, JSON, Enum as SAEnum
)
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


class Base(DeclarativeBase):
    pass


def utcnow():
    return datetime.now(timezone.utc)


# ─── Enums ────────────────────────────────────────────────────────────────────

class ModelAbstraction(str, enum.Enum):
    """Virtual model roles exposed to consumers."""
    CODING       = "coding"
    CHAT         = "chat"
    REASONING    = "reasoning"
    VISION       = "vision"
    EMBEDDING    = "embedding"
    SUMMARIZE    = "summarize"


class BudgetType(str, enum.Enum):
    TIME_BASED   = "time_based"    # Token budget refreshes on schedule
    FIXED        = "fixed"         # One-off fixed token budget
    UNLIMITED    = "unlimited"     # No budget limit


class TokenStatus(str, enum.Enum):
    ACTIVE    = "active"
    EXPIRED   = "expired"
    REVOKED   = "revoked"
    EXHAUSTED = "exhausted"


class RequestStatus(str, enum.Enum):
    SUCCESS = "success"
    ERROR   = "error"
    BLOCKED = "blocked"   # Budget exceeded / auth failed


# ─── Provider API Keys ────────────────────────────────────────────────────────

class ProviderKey(Base):
    """
    An API key for a specific LLM provider, owned by a person/team.
    Multiple keys per provider are supported (round-robin / failover).
    """
    __tablename__ = "provider_keys"

    id            = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_label   = Column(String, nullable=False)          # e.g. "alice", "team-backend"
    provider      = Column(String, nullable=False)          # e.g. "openai", "anthropic"
    api_key       = Column(String, nullable=False)          # encrypted at rest recommended
    is_active     = Column(Boolean, default=True)
    priority      = Column(Integer, default=0)              # higher = preferred
    monthly_limit = Column(Integer, nullable=True)          # optional per-key cap (tokens)
    tokens_used   = Column(Integer, default=0)
    created_at    = Column(DateTime(timezone=True), default=utcnow)
    last_used_at  = Column(DateTime(timezone=True), nullable=True)
    metadata_     = Column("metadata", JSON, default=dict)

    usages = relationship("UsageLog", back_populates="provider_key")


# ─── Model Registry ───────────────────────────────────────────────────────────

class ModelMapping(Base):
    """
    Maps a virtual model abstraction (e.g. 'coding') to a real provider model.
    Multiple mappings can exist per abstraction (primary / fallback).
    """
    __tablename__ = "model_mappings"

    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    abstraction     = Column(SAEnum(ModelAbstraction), nullable=False, index=True)
    provider        = Column(String, nullable=False)         # "openai" | "anthropic" | ...
    model_name      = Column(String, nullable=False)         # "gpt-4o" | "claude-3-5-sonnet"
    is_active       = Column(Boolean, default=True)
    priority        = Column(Integer, default=0)             # higher = tried first
    max_tokens      = Column(Integer, nullable=True)
    temperature     = Column(Float, nullable=True)
    extra_params    = Column(JSON, default=dict)
    created_at      = Column(DateTime(timezone=True), default=utcnow)
    updated_at      = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ─── Access Tokens ────────────────────────────────────────────────────────────

class AccessToken(Base):
    """
    A proxy access token issued to a consumer (user, service, team).
    Carries a budget that can be token-count-based and/or time-limited.
    """
    __tablename__ = "access_tokens"

    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    token_hash      = Column(String, unique=True, nullable=False, index=True)
    label           = Column(String, nullable=False)         # human-readable name
    owner           = Column(String, nullable=False)         # owner identifier

    # Budget configuration
    budget_type     = Column(SAEnum(BudgetType), default=BudgetType.FIXED)
    token_budget    = Column(Integer, nullable=True)         # total tokens allowed
    tokens_used     = Column(Integer, default=0)
    refresh_period  = Column(String, nullable=True)          # "daily"|"weekly"|"monthly"
    last_refresh_at = Column(DateTime(timezone=True), nullable=True)

    # Time window
    valid_from      = Column(DateTime(timezone=True), default=utcnow)
    valid_until     = Column(DateTime(timezone=True), nullable=True)  # None = no expiry

    # Permissions
    allowed_models  = Column(JSON, default=list)             # [] = all abstractions
    status          = Column(SAEnum(TokenStatus), default=TokenStatus.ACTIVE, index=True)
    rate_limit_rpm  = Column(Integer, nullable=True)         # requests per minute

    created_at      = Column(DateTime(timezone=True), default=utcnow)
    updated_at      = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    metadata_       = Column("metadata", JSON, default=dict)

    usages = relationship("UsageLog", back_populates="access_token")


# ─── Usage / Audit Log ────────────────────────────────────────────────────────

class UsageLog(Base):
    """Immutable record of every proxy request."""
    __tablename__ = "usage_logs"

    id                = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    access_token_id   = Column(String, ForeignKey("access_tokens.id"), nullable=True)
    provider_key_id   = Column(String, ForeignKey("provider_keys.id"), nullable=True)

    abstraction       = Column(String, nullable=True)        # virtual model used
    provider          = Column(String, nullable=True)
    model_name        = Column(String, nullable=True)

    prompt_tokens     = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens      = Column(Integer, default=0)

    latency_ms        = Column(Integer, nullable=True)
    status            = Column(SAEnum(RequestStatus), nullable=False)
    error_message     = Column(Text, nullable=True)

    # Request fingerprint (no PII stored by default)
    request_id        = Column(String, nullable=True)
    ip_address        = Column(String, nullable=True)

    created_at        = Column(DateTime(timezone=True), default=utcnow, index=True)

    access_token  = relationship("AccessToken", back_populates="usages")
    provider_key  = relationship("ProviderKey", back_populates="usages")
