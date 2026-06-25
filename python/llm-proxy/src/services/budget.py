"""
Budget Service — validates access tokens and tracks token consumption.

Responsibilities:
  - Authenticate incoming proxy tokens (hash comparison)
  - Check time validity (valid_from / valid_until)
  - Check budget availability (tokens_used < token_budget)
  - Auto-refresh time-based budgets
  - Deduct consumed tokens after a successful LLM call
  - Return structured budget status to callers
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    AccessToken, BudgetType, ModelAbstraction,
    RequestStatus, TokenStatus, UsageLog
)


def _hash_token(raw: str) -> str:
    """SHA-256 hex digest — never store raw tokens in the DB."""
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_token() -> Tuple[str, str]:
    """Returns (raw_token, hash). Caller stores raw; DB stores hash."""
    raw = "llmp_" + secrets.token_urlsafe(32)
    return raw, _hash_token(raw)


class BudgetError(Exception):
    """Raised when a request cannot proceed due to budget/auth issues."""
    def __init__(self, message: str, status: RequestStatus = RequestStatus.BLOCKED):
        super().__init__(message)
        self.status = status


class BudgetService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Authentication ────────────────────────────────────────────────────────

    async def authenticate(
        self,
        raw_token: str,
        requested_abstraction: Optional[ModelAbstraction] = None,
    ) -> AccessToken:
        """
        Validate the token and return the AccessToken row.
        Raises BudgetError on any failure.
        """
        token_hash = _hash_token(raw_token)
        result = await self._db.execute(
            select(AccessToken).where(AccessToken.token_hash == token_hash)
        )
        token: Optional[AccessToken] = result.scalars().first()

        if token is None:
            raise BudgetError("Invalid access token.", RequestStatus.BLOCKED)

        # Auto-refresh time-based budgets before checking
        await self._maybe_refresh(token)

        self._assert_active(token)
        self._assert_time_window(token)
        self._assert_budget(token)
        self._assert_model_allowed(token, requested_abstraction)

        return token

    # ── Budget deduction ──────────────────────────────────────────────────────

    async def deduct(
        self,
        token: AccessToken,
        prompt_tokens: int,
        completion_tokens: int,
        provider_key_id: str,
        abstraction: str,
        provider: str,
        model_name: str,
        latency_ms: int,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        error_message: Optional[str] = None,
        status: RequestStatus = RequestStatus.SUCCESS,
    ) -> None:
        """Record usage and deduct from budget. Must be called after LLM call."""
        total = prompt_tokens + completion_tokens

        # Update access token counters
        await self._db.execute(
            update(AccessToken)
            .where(AccessToken.id == token.id)
            .values(tokens_used=AccessToken.tokens_used + total)
        )

        # Check exhaustion threshold
        if (
            token.budget_type != BudgetType.UNLIMITED
            and token.token_budget is not None
            and (token.tokens_used + total) >= token.token_budget
        ):
            await self._db.execute(
                update(AccessToken)
                .where(AccessToken.id == token.id)
                .values(status=TokenStatus.EXHAUSTED)
            )

        # Immutable audit log
        log = UsageLog(
            access_token_id=token.id,
            provider_key_id=provider_key_id,
            abstraction=abstraction,
            provider=provider,
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            latency_ms=latency_ms,
            status=status,
            error_message=error_message,
            request_id=request_id,
            ip_address=ip_address,
        )
        self._db.add(log)

    # ── Token CRUD helpers ────────────────────────────────────────────────────

    async def create_token(
        self,
        label: str,
        owner: str,
        budget_type: BudgetType = BudgetType.FIXED,
        token_budget: Optional[int] = None,
        valid_until: Optional[datetime] = None,
        refresh_period: Optional[str] = None,
        allowed_models: Optional[list] = None,
        rate_limit_rpm: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> Tuple[str, AccessToken]:
        raw, token_hash = generate_token()
        token = AccessToken(
            token_hash=token_hash,
            label=label,
            owner=owner,
            budget_type=budget_type,
            token_budget=token_budget,
            valid_until=valid_until,
            refresh_period=refresh_period,
            allowed_models=allowed_models or [],
            rate_limit_rpm=rate_limit_rpm,
            metadata_=metadata or {},
        )
        self._db.add(token)
        await self._db.flush()
        return raw, token

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _maybe_refresh(self, token: AccessToken) -> None:
        """Reset tokens_used if a time-based budget period has elapsed."""
        if token.budget_type != BudgetType.TIME_BASED or not token.refresh_period:
            return

        now = datetime.now(timezone.utc)
        last = token.last_refresh_at or token.valid_from
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)

        delta = _period_delta(token.refresh_period)
        if delta and (now - last) >= delta:
            await self._db.execute(
                update(AccessToken)
                .where(AccessToken.id == token.id)
                .values(
                    tokens_used=0,
                    last_refresh_at=now,
                    status=TokenStatus.ACTIVE,
                )
            )
            # refresh in-memory object too
            token.tokens_used = 0
            token.status = TokenStatus.ACTIVE

    def _assert_active(self, token: AccessToken) -> None:
        if token.status == TokenStatus.REVOKED:
            raise BudgetError("Access token has been revoked.")
        if token.status == TokenStatus.EXPIRED:
            raise BudgetError("Access token has expired.")
        if token.status == TokenStatus.EXHAUSTED:
            raise BudgetError("Token budget exhausted. Request more tokens or wait for renewal.")

    def _assert_time_window(self, token: AccessToken) -> None:
        now = datetime.now(timezone.utc)
        valid_from = token.valid_from
        if valid_from and valid_from.tzinfo is None:
            valid_from = valid_from.replace(tzinfo=timezone.utc)
        if valid_from and now < valid_from:
            raise BudgetError("Access token is not yet valid.")

        valid_until = token.valid_until
        if valid_until:
            if valid_until.tzinfo is None:
                valid_until = valid_until.replace(tzinfo=timezone.utc)
            if now > valid_until:
                raise BudgetError("Access token has expired (time window exceeded).")

    def _assert_budget(self, token: AccessToken) -> None:
        if token.budget_type == BudgetType.UNLIMITED:
            return
        if token.token_budget is None:
            return
        if token.tokens_used >= token.token_budget:
            raise BudgetError("Token budget exhausted.")

    def _assert_model_allowed(
        self,
        token: AccessToken,
        abstraction: Optional[ModelAbstraction],
    ) -> None:
        if not token.allowed_models:          # empty list = all abstractions allowed
            return
        if abstraction and abstraction.value not in token.allowed_models:
            raise BudgetError(
                f"Access token is not permitted to use '{abstraction.value}' model abstraction."
            )


def _period_delta(period: str) -> Optional[timedelta]:
    return {
        "daily":   timedelta(days=1),
        "weekly":  timedelta(weeks=1),
        "monthly": timedelta(days=30),
    }.get(period)
