"""
Admin management endpoints (require ADMIN_API_KEY).

- ``/admin/wallets``         — Wallet management (credit from providers)
- ``/admin/provider-keys``   — CRUD for provider API keys
- ``/admin/model-mappings``  — CRUD for abstraction to model mappings
- ``/admin/usage``           — Usage / audit log queries
"""
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    CreditModelType,
    ModelAbstraction,
    ModelMapping,
    ProviderKey,
    UsageLog,
    Wallet,
    WalletProviderLink,
)
from src.db.session import db_get
from src.guards.auth import require_admin
from src.services.budget import _hash_token
from src.services.credit_models import (
    CreditModelFactory,
    CreditState,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix       = "/admin",
    tags         = ["Admin"],
    dependencies = [Depends(require_admin)],
)


# ═══════════════════════════════════════════════════════════════════════════════
# Wallet management
# ═══════════════════════════════════════════════════════════════════════════════


class CreateWalletRequest(BaseModel):
    """Request body for creating a new wallet."""
    label           : str
    owner           : str
    allowed_models  : List[str]                     = Field(default_factory=list)
    valid_until     : Optional[datetime]            = None
    metadata        : Dict[str, Any]                = Field(default_factory=dict)


class WalletResponse(BaseModel):
    """Response schema for a wallet."""
    id             : str
    label          : str
    owner          : str
    balance        : int
    status         : str          # active | revoked
    allowed_models : List[str]     # [] = all abstractions
    valid_until    : Optional[datetime]
    created_at     : datetime
    metadata       : Dict[str, Any]


class AddProviderToWalletRequest(BaseModel):
    """Request body for transferring credit from a provider to a wallet."""
    provider_id     : str = Field(..., description="Provider key UUID")
    credit_amount   : int = Field(..., gt=0, description="Amount of credit to transfer to wallet")


@router.post("/wallets", status_code=status.HTTP_201_CREATED)
async def create_wallet(
    body: CreateWalletRequest,
    db: AsyncSession = Depends(db_get),
) -> Dict[str, Any]:
    """
    Create a new wallet.

    Wallets hold accumulated credit from providers. The balance is
    cumulative — it never resets (unlike provider credit).

    Args:
        body: Wallet creation parameters.
        db: Database session dependency.

    Returns:
        Wallet metadata and the generated token (only shown once).
    """
    # Generate a random token and its hash
    raw_token = f"sk_live_{secrets.token_urlsafe(32)}"
    token_hash = _hash_token(raw_token)

    wallet = Wallet(
        label          = body.label,
        owner          = body.owner,
        balance        = 0,                           # starts empty
        status         = "active",
        allowed_models = body.allowed_models,
        valid_until    = body.valid_until,
        metadata_      = body.metadata,
        token_hash     = token_hash,
    )
    db.add(wallet)
    await db.flush()
    return {
        "wallet_id"     : wallet.id,
        "label"         : wallet.label,
        "owner"         : wallet.owner,
        "balance"       : wallet.balance,
        "status"        : wallet.status,
        "allowed_models": wallet.allowed_models or [],
        "valid_until"   : wallet.valid_until,
        "created_at"    : wallet.created_at,
        "token"         : raw_token,  # Return the raw token only once
    }


@router.get("/wallets", response_model=List[WalletResponse])
async def list_wallets(
    owner: Optional[str] = None,
    db: AsyncSession = Depends(db_get),
) -> List[WalletResponse]:
    """
    List wallets, optionally filtered by owner.

    Args:
        owner: Optional owner filter.
        db: Database session dependency.

    Returns:
        A list of wallets ordered by creation date descending.
    """
    q = select(Wallet)
    if owner:
        q = q.where(Wallet.owner == owner)
    result = await db.execute(q.order_by(Wallet.created_at.desc()))
    wallets = result.scalars().all()
    return [
        WalletResponse(
            id             = w.id,
            label          = w.label,
            owner          = w.owner,
            balance        = w.balance,
            status         = w.status,
            allowed_models = w.allowed_models or [],
            valid_until    = w.valid_until,
            created_at     = w.created_at,
            metadata       = w.metadata_,
        )
        for w in wallets
    ]


@router.get("/wallets/{wallet_id}", response_model=WalletResponse)
async def get_wallet(
    wallet_id: str,
    db: AsyncSession = Depends(db_get),
) -> WalletResponse:
    """
    Retrieve a single wallet by ID.

    Args:
        wallet_id: Wallet UUID.
        db: Database session dependency.

    Returns:
        The wallet response.

    Raises:
        HTTPException: 404 if not found.
    """
    wallet = await db.get(Wallet, wallet_id)
    if not wallet:
        raise HTTPException(404, "Wallet not found")
    return WalletResponse(
        id            = wallet.id,
        label         = wallet.label,
        owner         = wallet.owner,
        balance       = wallet.balance,
        status        = wallet.status,
        allowed_models= wallet.allowed_models or [],
        valid_until   = wallet.valid_until,
        created_at    = wallet.created_at,
        metadata      = wallet.metadata_,
    )


@router.patch("/wallets/{wallet_id}/revoke")
async def revoke_wallet(
    wallet_id: str,
    db: AsyncSession = Depends(db_get),
) -> Dict[str, Any]:
    """
    Revoke a wallet (sets status to 'revoked').

    Args:
        wallet_id: Wallet UUID.
        db: Database session dependency.

    Returns:
        Confirmation with wallet ID.
    """
    wallet = await db.get(Wallet, wallet_id)
    if not wallet:
        raise HTTPException(404, "Wallet not found")
    wallet.status = "revoked"
    await db.flush()
    return {
        "status": "revoked",
        "wallet_id": wallet.id
    }


@router.get("/wallets/{wallet_id}/providers")
async def list_wallet_providers(
    wallet_id: str,
    db: AsyncSession = Depends(db_get),
) -> List[Dict[str, Any]]:
    """
    List providers linked to a wallet.

    Args:
        wallet_id: Wallet UUID.
        db: Database session dependency.

    Returns:
        A list of provider link details.

    Raises:
        HTTPException: 404 if wallet not found.
    """
    wallet = await db.get(Wallet, wallet_id)
    if not wallet:
        raise HTTPException(404, "Wallet not found")

    result = await db.execute(
        select(WalletProviderLink, ProviderKey)
        .join(ProviderKey, WalletProviderLink.provider_key_id == ProviderKey.id)
        .where(WalletProviderLink.wallet_id == wallet_id)
        .order_by(WalletProviderLink.linked_at.desc())
    )
    links = result.all()
    return [
        {
            "id"              : link.id,
            "provider_id"     : link.provider_key_id,
            "provider_name"   : provider.provider,
            "credited_amount" : link.credited_amount,
            "linked_at"       : link.linked_at,
        }
        for link, provider in links
    ]


@router.delete("/wallets/{wallet_id}/providers/{provider_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_provider_from_wallet(
    wallet_id: str,
    provider_key_id: str,
    db: AsyncSession = Depends(db_get),
) -> None:
    """
    Unlink a provider from a wallet. Credit is not refunded.

    Args:
        wallet_id: Wallet UUID.
        provider_key_id: Provider key UUID.
        db: Database session dependency.

    Raises:
        HTTPException: 404 if link not found.
    """
    result = await db.execute(
        select(WalletProviderLink).where(
            WalletProviderLink.wallet_id == wallet_id,
            WalletProviderLink.provider_key_id == provider_key_id,
        )
    )
    link = result.scalars().first()
    if not link:
        raise HTTPException(404, "Provider link not found")
    await db.delete(link)


@router.post("/wallets/{wallet_id}/providers")
async def add_provider_to_wallet(
    wallet_id: str,
    body: AddProviderToWalletRequest,
    db: AsyncSession = Depends(db_get),
) -> Dict[str, Any]:
    """
    Transfer credit from a provider to a wallet.

    The amount is deducted from the provider's available budget (according
    to its credit model) and added to the wallet's balance. The wallet is
    cumulative — it never resets.

    Args:
        wallet_id: Wallet UUID.
        body: Transfer parameters (provider_key_id and amount).
        db: Database session dependency.

    Returns:
        Updated wallet and provider details.

    Raises:
        HTTPException: 404 if wallet or provider not found.
        HTTPException: 400 if insufficient provider credit.
    """
    wallet = await db.get(Wallet, wallet_id)
    if not wallet:
        raise HTTPException(404, "Wallet not found")

    provider_key = await db.get(ProviderKey, body.provider_key_id)
    if not provider_key:
        raise HTTPException(404, "Provider key not found")

    # Build CreditState from the provider's current state
    state = CreditState(
        budget_amount  = provider_key.budget_amount,
        budget_spent   = provider_key.budget_spent,
        last_reset_at  = provider_key.last_reset_at or datetime.now(timezone.utc),
        credit_model   = CreditModelType(provider_key.credit_model),
    )

    # Check availability via the credit model strategy
    strategy = CreditModelFactory.get_strategy(state.credit_model)
    if not strategy.check_availability(state, body.credit_amount):
        raise HTTPException(
            400,
            f"Insufficient credit. Available: {state.budget_available}, requested: {body.credit_amount}",
        )

    # Deduct from provider
    new_state = strategy.deduct(state, body.credit_amount)
    provider_key.budget_spent  = new_state.budget_spent
    provider_key.last_used_at  = datetime.now(timezone.utc)

    # Record the link
    link = WalletProviderLink(
        wallet_id       = wallet.id,
        provider_key_id = provider_key.id,
        credited_amount = body.credit_amount,
    )
    db.add(link)

    # Add to wallet (cumulative — never resets)
    wallet.balance += body.credit_amount

    await db.flush()

    return {
        "wallet_id"         : wallet.id,
        "wallet_balance"    : wallet.balance,
        "provider_id"       : provider_key.id,
        "credit_transferred": body.credit_amount,
        "provider_remaining": new_state.budget_available,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Provider Key management
# ═══════════════════════════════════════════════════════════════════════════════


class CreateProviderKeyRequest(BaseModel):
    """Request body for registering a new provider API key."""
    owner_label   : str
    provider      : str              = Field(..., description="openai|anthropic|google")
    api_key       : str
    priority      : int              = 0
    credit_model  : str              = Field(default="one_time", description="Credit model: one_time or monthly_reset")
    budget_amount : int              = Field(..., gt=0, description="Budget amount for the provider")
    metadata      : Dict[str, Any]   = Field(default_factory=dict)


@router.post("/provider-keys", status_code=status.HTTP_201_CREATED)
async def create_provider_key(
    body: CreateProviderKeyRequest,
    db: AsyncSession = Depends(db_get),
) -> Dict[str, Any]:
    """
    Register a new provider API key with credit model configuration.

    Args:
        body: Key registration parameters.
        db: Database session dependency.

    Returns:
        Metadata about the stored key (the raw key is not returned).
    """
    from datetime import timezone
    key = ProviderKey(
        owner_label   = body.owner_label,
        provider      = body.provider,
        api_key       = body.api_key,
        priority      = body.priority,
        credit_model  = body.credit_model,
        budget_amount = body.budget_amount,
        budget_spent  = 0,
        last_reset_at = datetime.now(timezone.utc),
        metadata_     = body.metadata,
    )
    db.add(key)
    await db.flush()
    return {
        "id"          : key.id,
        "owner_label" : key.owner_label,
        "provider"    : key.provider,
        "priority"    : key.priority,
        "credit_model": key.credit_model,
        "budget_amount": key.budget_amount,
        "budget_spent": key.budget_spent,
        "is_active"   : key.is_active,
    }


@router.get("/provider-keys")
async def list_provider_keys(
    provider: Optional[str] = None,
    db: AsyncSession = Depends(db_get),
) -> List[Dict[str, Any]]:
    """
    List registered provider keys, optionally filtered by provider name.

    Args:
        provider: Optional provider name filter (e.g. ``openai``).
        db: Database session dependency.

    Returns:
        A list of provider key metadata (raw keys are never exposed).
    """
    q = select(ProviderKey)
    if provider:
        q = q.where(ProviderKey.provider == provider)
    result = await db.execute(
        q.order_by(ProviderKey.provider, ProviderKey.priority.desc())
    )
    keys = result.scalars().all()
    return [
        {
            "id"            : k.id,
            "owner_label"   : k.owner_label,
            "provider"      : k.provider,
            "priority"      : k.priority,
            "is_active"     : k.is_active,
            "credit_model"  : k.credit_model,
            "budget_amount" : k.budget_amount,
            "budget_spent"  : k.budget_spent,
            "budget_available": max(0, k.budget_amount - k.budget_spent),
            "last_used_at"  : k.last_used_at,
            "last_reset_at" : k.last_reset_at,
        }
        for k in keys
    ]


@router.patch("/provider-keys/{key_id}/budget")
async def update_provider_budget(
    key_id: str,
    credit_model: Optional[str] = Query(None, description="Credit model: one_time or monthly_reset"),
    budget_amount: Optional[int] = Query(None, gt=0, description="New budget amount"),
    db: AsyncSession = Depends(db_get),
) -> Dict[str, Any]:
    """
    Update provider budget configuration (credit model and/or amount).

    When budget_type changes (e.g. monthly_reset → one_time), the spent
    counter is kept unless budget_amount also changes (then spent resets to 0).

    Args:
        key_id: Provider key UUID.
        credit_model: New credit model (one_time, monthly_reset).
        budget_amount: New budget amount (must be positive).
        db: Database session dependency.

    Returns:
        Updated provider metadata.
    """
    key = await db.get(ProviderKey, key_id)
    if not key:
        raise HTTPException(404, "Provider key not found")

    if credit_model is not None:
        valid_models = {"one_time", "monthly_reset"}
        if credit_model not in valid_models:
            raise HTTPException(400, f"Invalid credit model. Valid: {', '.join(sorted(valid_models))}")
        key.credit_model = credit_model

    if budget_amount is not None:
        key.budget_amount = budget_amount
        # Reset spent when budget amount is explicitly updated
        key.budget_spent = 0

    return {
        "id"            : key.id,
        "credit_model"  : key.credit_model,
        "budget_amount" : key.budget_amount,
        "budget_spent"  : key.budget_spent,
    }


@router.patch("/provider-keys/{key_id}/toggle")
async def toggle_provider_key(
    key_id: str,
    db: AsyncSession = Depends(db_get),
) -> Dict[str, Any]:
    """
    Toggle the active status of a provider key.

    Args:
        key_id: Provider key UUID.
        db: Database session dependency.

    Returns:
        Confirmation with new active state.
    """
    key = await db.get(ProviderKey, key_id)
    if not key:
        raise HTTPException(404, "Provider key not found")
    key.is_active = not key.is_active
    return {"id": key_id, "is_active": key.is_active}


@router.delete("/provider-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider_key(
    key_id: str,
    db: AsyncSession = Depends(db_get),
) -> None:
    """
    Delete a provider key.

    Args:
        key_id: Provider key UUID.
        db: Database session dependency.
    """
    key = await db.get(ProviderKey, key_id)
    if not key:
        raise HTTPException(404, "Provider key not found")
    await db.delete(key)


# ═══════════════════════════════════════════════════════════════════════════════
# Model Mapping management
# ═══════════════════════════════════════════════════════════════════════════════


class CreateMappingRequest(BaseModel):
    """Request body for creating a new abstraction-to-model mapping."""
    abstraction  : ModelAbstraction
    provider     : str
    model_name   : str
    priority     : int                     = 0
    max_tokens   : Optional[int]           = None
    temperature  : Optional[float]         = None
    extra_params : Dict[str, Any]          = Field(default_factory=dict)


@router.post("/model-mappings", status_code=status.HTTP_201_CREATED)
async def create_model_mapping(
    body: CreateMappingRequest,
    db: AsyncSession = Depends(db_get),
) -> Dict[str, Any]:
    """
    Create a new abstraction-to-model mapping.

    Args:
        body: Mapping parameters.
        db: Database session dependency.

    Returns:
        Metadata about the created mapping.
    """
    mapping = ModelMapping(
        abstraction  = body.abstraction,
        provider     = body.provider,
        model_name   = body.model_name,
        priority     = body.priority,
        max_tokens   = body.max_tokens,
        temperature  = body.temperature,
        extra_params = body.extra_params,
    )
    db.add(mapping)
    await db.flush()
    return {
        "id"          : mapping.id,
        "abstraction" : mapping.abstraction,
        "provider"    : mapping.provider,
        "model_name"  : mapping.model_name,
        "priority"    : mapping.priority,
    }


@router.get("/model-mappings")
async def list_model_mappings(
    db: AsyncSession = Depends(db_get),
) -> List[Dict[str, Any]]:
    """
    List all model mappings ordered by abstraction and priority.

    Args:
        db: Database session dependency.

    Returns:
        A list of mapping metadata.
    """
    result = await db.execute(
        select(ModelMapping).order_by(
            ModelMapping.abstraction,
            ModelMapping.priority.desc(),
        )
    )
    mappings = result.scalars().all()
    return [
        {
            "id"          : m.id,
            "abstraction" : m.abstraction,
            "provider"    : m.provider,
            "model_name"  : m.model_name,
            "priority"    : m.priority,
            "is_active"   : m.is_active,
            "max_tokens"  : m.max_tokens,
            "temperature" : m.temperature,
        }
        for m in mappings
    ]


@router.patch("/model-mappings/{mapping_id}/toggle")
async def toggle_mapping(
    mapping_id: str,
    db: AsyncSession = Depends(db_get),
) -> Dict[str, Any]:
    """
    Toggle the active status of a model mapping.

    Args:
        mapping_id: Mapping UUID.
        db: Database session dependency.

    Returns:
        Confirmation with new active state.
    """
    m = await db.get(ModelMapping, mapping_id)
    if not m:
        raise HTTPException(404, "Mapping not found")
    m.is_active = not m.is_active
    return {"id": mapping_id, "is_active": m.is_active}


@router.delete("/model-mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mapping(
    mapping_id: str,
    db: AsyncSession = Depends(db_get),
) -> None:
    """
    Delete a model mapping.

    Args:
        mapping_id: Mapping UUID.
        db: Database session dependency.
    """
    m = await db.get(ModelMapping, mapping_id)
    if not m:
        raise HTTPException(404, "Mapping not found")
    await db.delete(m)


# ═══════════════════════════════════════════════════════════════════════════════
# Usage / Audit Log
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/usage")
async def get_usage(
    wallet_id   : Optional[str] = None,
    provider    : Optional[str] = None,
    abstraction : Optional[str] = None,
    limit       : int           = Query(50, le=500),
    db          : AsyncSession  = Depends(db_get),
) -> List[Dict[str, Any]]:
    """
    Query the usage / audit log with optional filters.

    Args:
        wallet_id: Optional wallet ID filter.
        provider: Optional provider name filter.
        abstraction: Optional abstraction name filter.
        limit: Maximum number of log entries to return (max 500).
        db: Database session dependency.

    Returns:
        A list of usage log entries.
    """
    q = select(UsageLog).order_by(UsageLog.created_at.desc()).limit(limit)
    if wallet_id:
        q = q.where(UsageLog.access_token_id == wallet_id)
    if provider:
        q = q.where(UsageLog.provider == provider)
    if abstraction:
        q = q.where(UsageLog.abstraction == abstraction)
    result = await db.execute(q)
    logs = result.scalars().all()
    return [
        {
            "id"                : l.id,
            "wallet_id"         : l.access_token_id,
            "abstraction"       : l.abstraction,
            "provider"          : l.provider,
            "model_name"        : l.model_name,
            "prompt_tokens"     : l.prompt_tokens,
            "completion_tokens" : l.completion_tokens,
            "total_tokens"      : l.total_tokens,
            "latency_ms"        : l.latency_ms,
            "status"            : l.status,
            "created_at"        : l.created_at,
        }
        for l in logs
    ]


@router.get("/usage/stats")
async def usage_stats(
    db: AsyncSession = Depends(db_get),
) -> Dict[str, Any]:
    """
    Aggregate token usage per abstraction and provider.

    Args:
        db: Database session dependency.

    Returns:
        Aggregated statistics grouped by abstraction and provider.
    """
    result = await db.execute(
        select(
            UsageLog.abstraction,
            UsageLog.provider,
            func.count(UsageLog.id).label("requests"),
            func.sum(UsageLog.total_tokens).label("total_tokens"),
            func.avg(UsageLog.latency_ms).label("avg_latency_ms"),
        )
        .group_by(UsageLog.abstraction, UsageLog.provider)
        .order_by(func.sum(UsageLog.total_tokens).desc())
    )
    return {"stats": [dict(row._mapping) for row in result]}


