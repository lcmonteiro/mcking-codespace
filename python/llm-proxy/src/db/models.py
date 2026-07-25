"""
SQLAlchemy ORM models for the LLM Proxy.

Defines the database schema: provider keys, model mappings, access tokens,
wallets, and usage / audit log.
"""
import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    Enum as SAEnum,
    ARRAY,
)
from sqlalchemy.orm import DeclarativeBase, relationship

# ====================================================================================================
# Base
# ====================================================================================================


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


# ====================================================================================================
# Helpers
# ====================================================================================================


def utcnow() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(timezone.utc)


# ====================================================================================================
# Enums
# ====================================================================================================


class ModelAbstraction(str, enum.Enum):
    """Virtual model roles exposed to consumers."""
    CODING       = "coding"
    CHAT         = "chat"
    REASONING    = "reasoning"
    VISION       = "vision"
    EMBEDDING    = "embedding"
    SUMMARIZE    = "summarize"


class BudgetType(str, enum.Enum):
    """Token budget policy for access tokens."""
    TIME_BASED = "time_based"     # Token budget refreshes on schedule
    FIXED      = "fixed"          # One-off fixed token budget
    UNLIMITED  = "unlimited"      # No budget limit


class TokenStatus(str, enum.Enum):
    """Lifecycle status of an access token."""
    ACTIVE    = "active"
    EXPIRED   = "expired"
    REVOKED   = "revoked"
    EXHAUSTED = "exhausted"


class RequestStatus(str, enum.Enum):
    """Outcome of an inference request."""
    SUCCESS = "success"
    ERROR   = "error"
    BLOCKED = "blocked"           # Budget exceeded / auth failed


# ====================================================================================================
# Provider API Keys
# ====================================================================================================


class ProviderKey(Base):
    """
    An API key for a specific LLM provider, owned by a person or team.

    Multiple keys per provider are supported for round-robin or failover.
    """

    __tablename__ = "provider_keys"

    id            : Column = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_label   : Column = Column(String, nullable=False)         # e.g. "alice", "team-backend"
    provider      : Column = Column(String, nullable=False)         # e.g. "openai", "anthropic"
    api_key       : Column = Column(String, nullable=False)         # encrypted at rest recommended
    is_active     : Column = Column(Boolean, default=True)
    priority      : Column = Column(Integer, default=0)             # higher = preferred
    monthly_limit : Column = Column(Integer, nullable=True)         # optional per-key cap (tokens)
    tokens_used   : Column = Column(Integer, default=0)

    # Credit model fields (used by wallet flow)
    credit_model  : Column = Column(String, nullable=False, default="one_time")   # "one_time" | "monthly_reset"
    budget_amount : Column = Column(Integer, nullable=True)         # total budget for this provider key
    budget_spent  : Column = Column(Integer, default=0)             # cumulative spend since last reset
    last_reset_at : Column = Column(DateTime(timezone=True), nullable=True)  # for monthly_reset tracking

    created_at    : Column = Column(DateTime(timezone=True), default=utcnow)
    last_used_at  : Column = Column(DateTime(timezone=True), nullable=True)
    metadata_     : Column = Column("metadata", JSON, default=dict)

    usages        = relationship("UsageLog", back_populates="provider_key")
    wallet_links  = relationship("WalletProviderLink", back_populates="provider_key")


# ====================================================================================================
# Model Registry
# ====================================================================================================


class ModelMapping(Base):
    """
    Maps a virtual model abstraction (e.g. ``coding``) to a real provider model.

    Multiple mappings can exist per abstraction for primary / fallback.
    """

    __tablename__ = "model_mappings"

    id           : Column = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    abstraction  : Column = Column(SAEnum(ModelAbstraction), nullable=False, index=True)
    provider     : Column = Column(String, nullable=False)          # "openai" | "anthropic" | ...
    model_name   : Column = Column(String, nullable=False)          # "gpt-4o" | "claude-3-5-sonnet"
    is_active    : Column = Column(Boolean, default=True)
    priority     : Column = Column(Integer, default=0)              # higher = tried first
    max_tokens   : Column = Column(Integer, nullable=True)
    temperature  : Column = Column(Float, nullable=True)
    extra_params : Column = Column(JSON, default=dict)
    created_at   : Column = Column(DateTime(timezone=True), default=utcnow)
    updated_at   : Column = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ====================================================================================================
# Access Tokens (kept for backward compatibility, but not used in new wallet flow)
# ====================================================================================================


class AccessToken(Base):
    """
    A proxy access token issued to a consumer (user, service, team).

    Carries a budget that can be token-count-based and/or time-limited.
    """

    __tablename__ = "access_tokens"

    id              : Column = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    token_hash      : Column = Column(String, unique=True, nullable=False, index=True)
    label           : Column = Column(String, nullable=False)          # human-readable name
    owner           : Column = Column(String, nullable=False)          # owner identifier

    # Budget configuration
    budget_type     : Column = Column(SAEnum(BudgetType), default=BudgetType.FIXED)
    token_budget    : Column = Column(Integer, nullable=True)         # total tokens allowed
    tokens_used     : Column = Column(Integer, default=0)
    refresh_period  : Column = Column(String, nullable=True)          # "daily" | "weekly" | "monthly"
    last_refresh_at : Column = Column(DateTime(timezone=True), nullable=True)

    # Time window
    valid_from  : Column = Column(DateTime(timezone=True), default=utcnow)
    valid_until : Column = Column(DateTime(timezone=True), nullable=True)  # None = no expiry

    # Permissions
    allowed_models : Column = Column(JSON, default=list)             # [] = all abstractions
    status         : Column = Column(SAEnum(TokenStatus), default=TokenStatus.ACTIVE, index=True)
    rate_limit_rpm : Column = Column(Integer, nullable=True)         # requests per minute

    created_at : Column = Column(DateTime(timezone=True), default=utcnow)
    updated_at : Column = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    metadata_  : Column = Column("metadata", JSON, default=dict)

    usages = relationship("UsageLog", back_populates="access_token")


# ====================================================================================================
# Wallets (replaces AccessToken for budget management)
# ====================================================================================================


class Wallet(Base):
    """
    A wallet holds accumulated credit from provider keys and is used for authentication.

    Wallets do not have their own budget that refreshes; instead, they draw credit
    from linked provider keys. The wallet's balance is cumulative (total credited)
    and never decreases on usage.
    """

    __tablename__ = "wallets"

    id              : Column = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    token_hash      : Column = Column(String, unique=True, nullable=True, index=True)  # nullable until set on creation
    label           : Column = Column(String, nullable=False)          # human-readable name
    owner           : Column = Column(String, nullable=False)          # owner identifier
    balance         : Column = Column(Integer, nullable=False, default=0)  # total credited from providers
    status          : Column = Column(String, nullable=False, default="active")  # active | revoked
    allowed_models  : Column = Column(ARRAY(String), nullable=True)      # [] = all abstractions
    valid_until     : Column = Column(DateTime(timezone=True), nullable=True)
    metadata_       : Column = Column("metadata", JSON, default=dict)
    created_at      : Column = Column(DateTime(timezone=True), default=utcnow)
    updated_at      : Column = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    provider_links = relationship("WalletProviderLink", back_populates="wallet", cascade="all, delete-orphan")
    usages = relationship("UsageLog", back_populates="wallet")


class WalletProviderLink(Base):
    """
    Links a provider key to a wallet, transferring a credited amount of budget.

    The credited amount is added to the wallet's balance (cumulative) and deducted
    from the provider's available budget according to its credit model.
    """

    __tablename__ = "wallet_provider_links"

    id              : Column = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    wallet_id       : Column = Column(String, ForeignKey("wallets.id"), nullable=False, index=True)
    provider_key_id : Column = Column(String, ForeignKey("provider_keys.id"), nullable=False, index=True)
    credited_amount : Column = Column(Integer, nullable=False)  # amount of credit transferred to wallet
    linked_at       : Column = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    wallet     = relationship("Wallet", back_populates="provider_links")
    provider_key = relationship("ProviderKey", back_populates="wallet_links")


# ====================================================================================================
# Usage / Audit Log
# ====================================================================================================


class UsageLog(Base):
    """Immutable record of every proxy request."""

    __tablename__ = "usage_logs"

    id              : Column = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    wallet_id       : Column = Column(String, ForeignKey("wallets.id"), nullable=True, index=True)
    provider_key_id : Column = Column(String, ForeignKey("provider_keys.id"), nullable=True, index=True)

    abstraction       : Column = Column(String, nullable=True)          # virtual model used
    provider          : Column = Column(String, nullable=True)
    model_name        : Column = Column(String, nullable=True)

    prompt_tokens     : Column = Column(Integer, default=0)
    completion_tokens : Column = Column(Integer, default=0)
    total_tokens      : Column = Column(Integer, default=0)

    latency_ms    : Column = Column(Integer, nullable=True)
    status        : Column = Column(SAEnum(RequestStatus), nullable=False)
    error_message : Column = Column(Text, nullable=True)

    # Request fingerprint (no PII stored by default)
    request_id : Column = Column(String, nullable=True)
    ip_address : Column = Column(String, nullable=True)

    created_at : Column = Column(DateTime(timezone=True), default=utcnow, index=True)

    wallet     = relationship("Wallet", back_populates="usages")
    provider_key = relationship("ProviderKey", back_populates="usages")