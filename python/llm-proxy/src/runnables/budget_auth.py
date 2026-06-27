# ====================================================================================================
# BudgetAuthRunnable
# ====================================================================================================

"""
BudgetAuthRunnable — authenticates a proxy token and checks budget availability.

LangChain Runnable with typed Pydantic I/O.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from langchain_core.runnables import Runnable, RunnableConfig
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AccessToken, BudgetType, ModelAbstraction, RequestStatus, TokenStatus
from src.db.session import AsyncSessionLocal
from src.services.budget import BudgetError, _hash_token, _period_delta

logger = logging.getLogger(__name__)


# ====================================================================================================
# I/O Schemas
# ====================================================================================================


class BudgetAuthInput(BaseModel):
    """Input schema for budget authentication."""

    raw_token    : str
    abstraction  : Optional[ModelAbstraction] = None


class BudgetAuthOutput(BaseModel):
    """Output schema for budget authentication."""

    success       : bool           = False
    access_token  : Optional[Any]  = None
    status        : RequestStatus  = RequestStatus.BLOCKED
    error_message : Optional[str]   = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


# ====================================================================================================
# Runnable
# ====================================================================================================


class BudgetAuthRunnable(Runnable[BudgetAuthInput, BudgetAuthOutput]):
    """
    Authenticate a proxy token and verify budget availability.

    Usage:
        result = await BudgetAuthRunnable().ainvoke(
            BudgetAuthInput(raw_token="llmp_...", abstraction=ModelAbstraction.CODING)
        )
        if result.success:
            token = result.access_token
    """

    async def ainvoke(
        self,
        input    : BudgetAuthInput,
        config   : Optional[RunnableConfig] = None,
        **kwargs : Any,
    ) -> BudgetAuthOutput:
        token_hash = _hash_token(input.raw_token)

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AccessToken).where(AccessToken.token_hash == token_hash)
            )
            token: Optional[AccessToken] = result.scalars().first()

            if token is None:
                return BudgetAuthOutput(
                    success       = False,
                    status        = RequestStatus.BLOCKED,
                    error_message = "Invalid access token.",
                )

            await self._maybe_refresh(db, token)

            try:
                self._assert_active(token)
                self._assert_time_window(token)
                self._assert_budget(token)
                self._assert_model_allowed(token, input.abstraction)
                await db.commit()
                return BudgetAuthOutput(
                    success      = True,
                    access_token = token,
                    status       = RequestStatus.SUCCESS,
                )
            except BudgetError as exc:
                return BudgetAuthOutput(
                    success       = False,
                    status        = exc.status,
                    error_message = str(exc),
                )

    # ==================================================================================================
    # Private helpers
    # ==================================================================================================

    @staticmethod
    async def _maybe_refresh(db: AsyncSession, token: AccessToken) -> None:
        """
        Refresh the token budget if it is time-based and the refresh period has elapsed.

        Args:
            db    : Database session.
            token : Access token to check.
        """
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
        """
        Assert that the token status is active.

        Args:
            token : Access token to check.

        Raises:
            BudgetError : If the token is revoked, expired, or exhausted.
        """
        if token.status == TokenStatus.REVOKED:
            raise BudgetError("Access token has been revoked.")
        if token.status == TokenStatus.EXPIRED:
            raise BudgetError("Access token has expired.")
        if token.status == TokenStatus.EXHAUSTED:
            raise BudgetError("Token budget exhausted. Request more tokens or wait for renewal.")

    @staticmethod
    def _assert_time_window(token: AccessToken) -> None:
        """
        Assert that the current time falls within the token's validity window.

        Args:
            token : Access token to check.

        Raises:
            BudgetError : If the token is not yet valid or has expired.
        """
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
        """
        Assert that the token budget has not been exhausted.

        Args:
            token : Access token to check.

        Raises:
            BudgetError : If the token's budget has been exhausted.
        """
        if token.budget_type == BudgetType.UNLIMITED:
            return
        if token.token_budget is None:
            return
        if token.tokens_used >= token.token_budget:
            raise BudgetError("Token budget exhausted.")

    @staticmethod
    def _assert_model_allowed(
        token: AccessToken, abstraction: Optional[ModelAbstraction]
    ) -> None:
        """
        Assert that the requested model abstraction is permitted for this token.

        Args:
            token      : Access token to check.
            abstraction : Requested model abstraction.

        Raises:
            BudgetError : If the abstraction is not in the token's allowed models.
        """
        if not token.allowed_models:
            return
        if abstraction and abstraction.value not in token.allowed_models:
            raise BudgetError(
                f"Access token is not permitted to use '{abstraction.value}' "
                "model abstraction."
            )
