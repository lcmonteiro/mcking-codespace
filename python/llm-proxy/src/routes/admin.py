"""
Admin management endpoints (require ADMIN_API_KEY).

- ``/admin/tokens``          — CRUD for access tokens
- ``/admin/provider-keys``   — CRUD for provider API keys
- ``/admin/model-mappings``  — CRUD for abstraction to model mappings
- ``/admin/usage``           — Usage / audit log queries
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    AccessToken,
    BudgetType,
    ModelAbstraction,
    ModelMapping,
    ProviderKey,
    TokenStatus,
    UsageLog,
)
from src.db.session import db_get
from src.middleware.auth import require_admin
from src.services.budget import BudgetService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix       = "/admin",
    tags         = ["Admin"],
    dependencies = [Depends(require_admin)],
)


# ═══════════════════════════════════════════════════════════════════════════════
# Access Token management
# ═══════════════════════════════════════════════════════════════════════════════


class CreateTokenRequest(BaseModel):
    """Request body for creating a new access token."""
    label           : str
    owner           : str
    budget_type     : BudgetType                    = BudgetType.FIXED
    token_budget    : Optional[int]                 = Field(None, description="Max tokens; None = unlimited")
    valid_until     : Optional[datetime]            = None
    refresh_period  : Optional[str]                 = Field(None, description="daily|weekly|monthly")
    allowed_models  : List[str]                     = Field(default_factory=list, description="[] = all abstractions")
    rate_limit_rpm  : Optional[int]                 = None
    metadata        : Dict[str, Any]                = Field(default_factory=dict)


class TokenResponse(BaseModel):
    """Response schema for an access token."""
    id             : str
    label          : str
    owner          : str
    budget_type    : str
    token_budget   : Optional[int]
    tokens_used    : int
    valid_until    : Optional[datetime]
    refresh_period : Optional[str]
    allowed_models : List[str]
    status         : str
    created_at     : datetime


@router.post("/tokens", status_code=status.HTTP_201_CREATED)
async def create_token(
    body: CreateTokenRequest,
    db: AsyncSession = Depends(db_get),
) -> Dict[str, Any]:
    """
    Create a new access token.

    Returns the raw token value **once** — it must be stored securely by the
    caller.

    Args:
        body: Token creation parameters.
        db: Database session dependency.

    Returns:
        The raw token and metadata.
    """
    svc = BudgetService(db)
    raw, token = await svc.create_token(
        label           = body.label,
        owner           = body.owner,
        budget_type     = body.budget_type,
        token_budget    = body.token_budget,
        valid_until     = body.valid_until,
        refresh_period  = body.refresh_period,
        allowed_models  = body.allowed_models,
        rate_limit_rpm  = body.rate_limit_rpm,
        metadata        = body.metadata,
    )
    return {
        "raw_token"    : raw,             # shown ONCE; store securely
        "token_id"     : token.id,
        "label"        : token.label,
        "owner"        : token.owner,
        "budget_type"  : token.budget_type,
        "token_budget" : token.token_budget,
        "valid_until"  : token.valid_until,
    }


@router.get("/tokens", response_model=List[TokenResponse])
async def list_tokens(
    owner: Optional[str] = None,
    db: AsyncSession = Depends(db_get),
) -> List[TokenResponse]:
    """
    List access tokens, optionally filtered by owner.

    Args:
        owner: Optional owner identifier filter.
        db: Database session dependency.

    Returns:
        A list of token responses ordered by creation date descending.
    """
    q = select(AccessToken)
    if owner:
        q = q.where(AccessToken.owner == owner)
    result = await db.execute(q.order_by(AccessToken.created_at.desc()))
    tokens = result.scalars().all()
    return [_token_to_resp(t) for t in tokens]


@router.get("/tokens/{token_id}", response_model=TokenResponse)
async def get_token(
    token_id: str,
    db: AsyncSession = Depends(db_get),
) -> TokenResponse:
    """
    Retrieve a single access token by ID.

    Args:
        token_id: Token UUID.
        db: Database session dependency.

    Returns:
        The token response.

    Raises:
        HTTPException: 404 if not found.
    """
    token = await db.get(AccessToken, token_id)
    if not token:
        raise HTTPException(404, "Token not found")
    return _token_to_resp(token)


@router.patch("/tokens/{token_id}/revoke")
async def revoke_token(
    token_id: str,
    db: AsyncSession = Depends(db_get),
) -> Dict[str, Any]:
    """
    Revoke an access token.

    Args:
        token_id: Token UUID.
        db: Database session dependency.

    Returns:
        Confirmation with token ID.
    """
    token = await db.get(AccessToken, token_id)
    if not token:
        raise HTTPException(404, "Token not found")
    token.status = TokenStatus.REVOKED
    return {"status": "revoked", "token_id": token_id}


@router.patch("/tokens/{token_id}/budget")
async def update_budget(
    token_id: str,
    token_budget: int = Query(..., gt=0),
    db: AsyncSession = Depends(db_get),
) -> Dict[str, Any]:
    """
    Update the token budget for an access token.

    Reactivates the token if it was exhausted.

    Args:
        token_id: Token UUID.
        token_budget: New budget value (must be positive).
        db: Database session dependency.

    Returns:
        Confirmation with new budget.
    """
    token = await db.get(AccessToken, token_id)
    if not token:
        raise HTTPException(404, "Token not found")
    token.token_budget = token_budget
    if token.status == TokenStatus.EXHAUSTED:
        token.status = TokenStatus.ACTIVE
    return {"token_id": token_id, "new_budget": token_budget}


# ═══════════════════════════════════════════════════════════════════════════════
# Provider Key management
# ═══════════════════════════════════════════════════════════════════════════════


class CreateProviderKeyRequest(BaseModel):
    """Request body for registering a new provider API key."""
    owner_label   : str
    provider      : str              = Field(..., description="openai|anthropic|google")
    api_key       : str
    priority      : int              = 0
    monthly_limit : Optional[int]    = None
    metadata      : Dict[str, Any]   = Field(default_factory=dict)


@router.post("/provider-keys", status_code=status.HTTP_201_CREATED)
async def create_provider_key(
    body: CreateProviderKeyRequest,
    db: AsyncSession = Depends(db_get),
) -> Dict[str, Any]:
    """
    Register a new provider API key.

    Args:
        body: Key registration parameters.
        db: Database session dependency.

    Returns:
        Metadata about the stored key (the raw key is not returned).
    """
    key = ProviderKey(
        owner_label   = body.owner_label,
        provider      = body.provider,
        api_key       = body.api_key,
        priority      = body.priority,
        monthly_limit = body.monthly_limit,
        metadata_     = body.metadata,
    )
    db.add(key)
    await db.flush()
    return {
        "id"          : key.id,
        "owner_label" : key.owner_label,
        "provider"    : key.provider,
        "priority"    : key.priority,
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
            "tokens_used"   : k.tokens_used,
            "monthly_limit" : k.monthly_limit,
            "last_used_at"  : k.last_used_at,
        }
        for k in keys
    ]


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
    token_id    : Optional[str] = None,
    provider    : Optional[str] = None,
    abstraction : Optional[str] = None,
    limit       : int           = Query(50, le=500),
    db          : AsyncSession  = Depends(db_get),
) -> List[Dict[str, Any]]:
    """
    Query the usage / audit log with optional filters.

    Args:
        token_id: Optional access token ID filter.
        provider: Optional provider name filter.
        abstraction: Optional abstraction name filter.
        limit: Maximum number of log entries to return (max 500).
        db: Database session dependency.

    Returns:
        A list of usage log entries.
    """
    q = select(UsageLog).order_by(UsageLog.created_at.desc()).limit(limit)
    if token_id:
        q = q.where(UsageLog.access_token_id == token_id)
    if provider:
        q = q.where(UsageLog.provider == provider)
    if abstraction:
        q = q.where(UsageLog.abstraction == abstraction)
    result = await db.execute(q)
    logs = result.scalars().all()
    return [
        {
            "id"                : l.id,
            "access_token_id"   : l.access_token_id,
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


# ====================================================================================================
# Helpers
# ====================================================================================================


def _token_to_resp(t: AccessToken) -> TokenResponse:
    """
    Convert an ORM AccessToken instance to a TokenResponse schema.

    Args:
        t: The AccessToken ORM instance.

    Returns:
        A TokenResponse DTO.
    """
    return TokenResponse(
        id             = t.id,
        label          = t.label,
        owner          = t.owner,
        budget_type    = t.budget_type.value,
        token_budget   = t.token_budget,
        tokens_used    = t.tokens_used,
        valid_until    = t.valid_until,
        refresh_period = t.refresh_period,
        allowed_models = t.allowed_models or [],
        status         = t.status.value,
        created_at     = t.created_at,
    )
