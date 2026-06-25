"""
Budget Service — validates access tokens and tracks token consumption.

Responsibilities:
  - Authenticate incoming proxy tokens (hash comparison)
  - Check time validity (valid_from / valid_until)
  - Check budget availability (tokens_used < token_budget)
  - Auto-refresh time-based budgets
  - Deduct consumed tokens after a successful LLM call
  - Return structured budget status to callers

LangChain Runnables exposed:
  - BudgetAuthRunnable     : authenticate + budget check
  - BudgetDeductRunnable   : deduct tokens + audit log
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.runnables import Runnable, RunnableConfig
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    AccessToken, BudgetType, ModelAbstraction,
    RequestStatus, TokenStatus, UsageLog
)
from src.db.session import AsyncSessionLocal


# ── Token hashing ─────────────────────────────────────────────────────────────

def _hash_token(raw: str) -> str:
    """SHA-256 hex digest — never store raw tokens in the DB."""
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_token() -> Tuple[str, str]:
    """Returns (raw_token, hash). Caller stores raw; DB stores hash."""
    raw = "llmp_" + secrets.token_urlsafe(32)
    return raw, _hash_token(raw)


# ─── Pydantic schemas for Runnable I/O ────────────────────────────────────────

class BudgetAuthInput(BaseModel):
    """Input schema for BudgetAuthRunnable."""
    raw_token: str
    abstraction: Optional[ModelAbstraction] = None


class BudgetAuthOutput(BaseModel):
    """Output schema for BudgetAuthRunnable."""
    success: bool = False
    access_token: Optional[Any] = None
    status: RequestStatus = RequestStatus.BLOCKED
    error_message: Optional[str] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class BudgetDeductInput(BaseModel):
    """Input schema for BudgetDeductRunnable."""
    token:            Any       = None
    prompt_tokens:    int       = 0
    completion_tokens: int      = 0
    provider_key_id:  str       = ""
    abstraction:      str       = ""
    provider:         str       = ""
    model_name:       str       = ""
    latency_ms:       int       = 0
    request_id:       Optional[str] = None
    ip_address:       Optional[str] = None
    error_message:    Optional[str] = None
    status:           RequestStatus = RequestStatus.SUCCESS

    model_config = ConfigDict(arbitrary_types_allowed=True)


# ── Exception ─────────────────────────────────────────────────────────────────

class BudgetError(Exception):
    """Raised when a request cannot proceed due to budget/auth issues."""
    def __init__(self, message: str, status: RequestStatus = RequestStatus.BLOCKED):
        super().__init__(message)
        self.status = status


# ─── Runnable: BudgetAuthRunnable ─────────────────────────────────────────────

class BudgetAuthRunnable(Runnable[BudgetAuthInput, BudgetAuthOutput]):
    """
    LangChain Runnable that authenticates a proxy token and checks budget.

    Usage:
        result = await runnable.ainvoke(BudgetAuthInput(raw_token="...", abstraction=...))
        if result.success:
            token = result.access_token
    """

    async def ainvoke(
        self,
        input: BudgetAuthInput,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> BudgetAuthOutput:
        token_hash = _hash_token(input.raw_token)

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AccessToken).where(AccessToken.token_hash == token_hash)
            )
            token: Optional[AccessToken] = result.scalars().first()

            if token is None:
                return BudgetAuthOutput(
                    success=False,
                    status=RequestStatus.BLOCKED,
                    error_message="Invalid access token.",
                )

            # Auto-refresh time-based budgets before checking
            await self._maybe_refresh(db, token)

            try:
                self._assert_active(token)
                self._assert_time_window(token)
                self._assert_budget(token)
                self._assert_model_allowed(token, input.abstraction)
                await db.commit()
                return BudgetAuthOutput(
                    success=True,
                    access_token=token,
                    status=RequestStatus.SUCCESS,
                )
            except BudgetError as exc:
                return BudgetAuthOutput(
                    success=False,
                    status=exc.status,
                    error_message=str(exc),
                )

    # ── Private: assertion logic (reused from internal BudgetService) ──────

    @staticmethod
    async def _maybe_refresh(db: AsyncSession, token: AccessToken) -> None:
        if token.budget_type != BudgetType.TIME_BASED or not token.refresh_period:
            return
        now = datetime.now(timezone.utc)
        last = token.last_refresh_at or token.valid_from
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        delta = _period_delta(token.refresh_period)
        if delta and (now - last) >= delta:
            await db.execute(
                update(AccessToken)
                .where(AccessToken.id == token.id)
                .values(tokens_used=0, last_refresh_at=now, status=TokenStatus.ACTIVE)
            )
            token.tokens_used = 0
            token.status = TokenStatus.ACTIVE

    @staticmethod
    def _assert_active(token: AccessToken) -> None:
        if token.status == TokenStatus.REVOKED:
            raise BudgetError("Access token has been revoked.")
        if token.status == TokenStatus.EXPIRED:
            raise BudgetError("Access token has expired.")
        if token.status == TokenStatus.EXHAUSTED:
            raise BudgetError("Token budget exhausted. Request more tokens or wait for renewal.")

    @staticmethod
    def _assert_time_window(token: AccessToken) -> None:
        now = datetime.now(timezone.utc)
        vf = token.valid_from
        if vf:
            if vf.tzinfo is None:
                vf = vf.replace(tzinfo=timezone.utc)
            if now < vf:
                raise BudgetError("Access token is not yet valid.")
        vu = token.valid_until
        if vu:
            if vu.tzinfo is None:
                vu = vu.replace(tzinfo=timezone.utc)
            if now > vu:
                raise BudgetError("Access token has expired (time window exceeded).")

    @staticmethod
    def _assert_budget(token: AccessToken) -> None:
        if token.budget_type == BudgetType.UNLIMITED:
            return
        if token.token_budget is None:
            return
        if token.tokens_used >= token.token_budget:
            raise BudgetError("Token budget exhausted.")

    @staticmethod
    def _assert_model_allowed(token: AccessToken, abstraction: Optional[ModelAbstraction]) -> None:
        if not token.allowed_models:
            return
        if abstraction and abstraction.value not in token.allowed_models:
            raise BudgetError(
                f"Access token is not permitted to use '{abstraction.value}' model abstraction."
            )


# ─── Runnable: BudgetDeductRunnable ───────────────────────────────────────────

class BudgetDeductRunnable(Runnable[BudgetDeductInput, dict]):
    """
    LangChain Runnable that deducts tokens from budget and records usage.

    Usage:
        await runnable.ainvoke(BudgetDeductInput(token=..., prompt_tokens=..., ...))
    """

    async def ainvoke(
        self,
        input: BudgetDeductInput,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> dict:
        async with AsyncSessionLocal() as db:
            total = input.prompt_tokens + input.completion_tokens

            # Update access token counters
            if input.token:
                await db.execute(
                    update(AccessToken)
                    .where(AccessToken.id == input.token.id)
                    .values(tokens_used=AccessToken.tokens_used + total)
                )
                # Check exhaustion
                if (
                    input.token.budget_type != BudgetType.UNLIMITED
                    and input.token.token_budget is not None
                    and (input.token.tokens_used + total) >= input.token.token_budget
                ):
                    await db.execute(
                        update(AccessToken)
                        .where(AccessToken.id == input.token.id)
                        .values(status=TokenStatus.EXHAUSTED)
                    )

            # Immutable audit log
            log = UsageLog(
                access_token_id=getattr(input.token, "id", None) if input.token else None,
                provider_key_id=input.provider_key_id,
                abstraction=input.abstraction,
                provider=input.provider,
                model_name=input.model_name,
                prompt_tokens=input.prompt_tokens,
                completion_tokens=input.completion_tokens,
                total_tokens=total,
                latency_ms=input.latency_ms,
                status=input.status,
                error_message=input.error_message,
                request_id=input.request_id,
                ip_address=input.ip_address,
            )
            db.add(log)
            await db.commit()
        return {}


# ── Internal BudgetService (kept for admin/delegation) ────────────────────────

class BudgetService:
    """
    Internal implementation. Prefer using BudgetAuthRunnable / BudgetDeductRunnable
    when composing LangChain pipelines.
    """
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def authenticate(
        self, raw_token: str, requested_abstraction: Optional[ModelAbstraction] = None
    ) -> AccessToken:
        runnable = BudgetAuthRunnable()
        result = await runnable.ainvoke(BudgetAuthInput(
            raw_token=raw_token, abstraction=requested_abstraction
        ))
        if not result.success:
            raise BudgetError(result.error_message or "Authentication failed", result.status)
        return result.access_token

    async def deduct(self, **kwargs: Any) -> None:
        runnable = BudgetDeductRunnable()
        await runnable.ainvoke(BudgetDeductInput(**kwargs))

    async def create_token(
        self, label: str, owner: str, budget_type: BudgetType = BudgetType.FIXED,
        token_budget: Optional[int] = None, valid_until: Optional[datetime] = None,
        refresh_period: Optional[str] = None, allowed_models: Optional[list] = None,
        rate_limit_rpm: Optional[int] = None, metadata: Optional[dict] = None,
    ) -> Tuple[str, AccessToken]:
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
