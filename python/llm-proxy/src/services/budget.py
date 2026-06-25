"""
Budget Service — shared utilities and internal BudgetService for admin compatibility.
LangChain Runnables are in src/services/runs/budget_auth.py and budget_deduct.py.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import BudgetType, ModelAbstraction, RequestStatus


# ── Token hashing ─────────────────────────────────────────────────────────────

def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_token() -> Tuple[str, str]:
    raw = "llmp_" + secrets.token_urlsafe(32)
    return raw, _hash_token(raw)


# ── Exception ─────────────────────────────────────────────────────────────────

class BudgetError(Exception):
    def __init__(self, message: str, status: RequestStatus = RequestStatus.BLOCKED):
        super().__init__(message)
        self.status = status


# ── Internal BudgetService (admin compat) ─────────────────────────────────────

class BudgetService:
    """
    Internal implementation for admin endpoints.
    Prefer BudgetAuthRunnable / BudgetDeductRunnable for LangChain pipelines.
    """
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def authenticate(
        self, raw_token: str, requested_abstraction: Optional[ModelAbstraction] = None
    ) -> Any:
        # Lazy import to avoid circular deps with runs/
        from src.services.runs.budget_auth import BudgetAuthInput, BudgetAuthRunnable
        runnable = BudgetAuthRunnable()
        result = await runnable.ainvoke(BudgetAuthInput(
            raw_token=raw_token, abstraction=requested_abstraction
        ))
        if not result.success:
            raise BudgetError(result.error_message or "Authentication failed", result.status)
        return result.access_token

    async def deduct(self, **kwargs: Any) -> None:
        from src.services.runs.budget_deduct import BudgetDeductInput, BudgetDeductRunnable
        runnable = BudgetDeductRunnable()
        await runnable.ainvoke(BudgetDeductInput(**kwargs))

    async def create_token(
        self, label: str, owner: str, budget_type: BudgetType = BudgetType.FIXED,
        token_budget: Optional[int] = None, valid_until: Optional[datetime] = None,
        refresh_period: Optional[str] = None, allowed_models: Optional[list] = None,
        rate_limit_rpm: Optional[int] = None, metadata: Optional[dict] = None,
    ) -> Tuple[str, Any]:
        from src.db.models import AccessToken
        raw, token_hash = generate_token()
        token = AccessToken(
            token_hash=token_hash, label=label, owner=owner,
            budget_type=budget_type, token_budget=token_budget,
            valid_until=valid_until, refresh_period=refresh_period,
            allowed_models=allowed_models or [], rate_limit_rpm=rate_limit_rpm,
            metadata_=metadata or {},
        )
        self._db.add(token)
        await self._db.flush()
        return raw, token


# ── Helpers ───────────────────────────────────────────────────────────────────

def _period_delta(period: str) -> Optional[timedelta]:
    return {"daily": timedelta(days=1), "weekly": timedelta(weeks=1), "monthly": timedelta(days=30)}.get(period)
