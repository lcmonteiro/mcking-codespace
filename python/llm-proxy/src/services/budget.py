# ====================================================================================================
# Budget Service
# ====================================================================================================

"""
Budget Service — shared utilities and internal BudgetService for admin compatibility.

LangChain Runnables are in src/services/runs/budget_auth.py and budget_deduct.py.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import BudgetType, ModelAbstraction, RequestStatus

logger = logging.getLogger(__name__)


# ====================================================================================================
# Token hashing
# ====================================================================================================


def _hash_token(raw: str) -> str:
    """
    Hash a raw token string using SHA-256.

    Args:
        raw : Raw token string.

    Returns:
        Hex-encoded SHA-256 digest.
    """
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_token() -> Tuple[str, str]:
    """
    Generate a new API token with a random secret.

    Returns:
        Tuple of (raw_token, hashed_token).
    """
    raw = "llmp_" + secrets.token_urlsafe(32)
    return raw, _hash_token(raw)


# ====================================================================================================
# Exception
# ====================================================================================================


class BudgetError(Exception):
    """Raised when a budget check fails."""

    def __init__(self, message: str, status: RequestStatus = RequestStatus.BLOCKED):
        super().__init__(message)
        self.status = status


# ====================================================================================================
# Helpers
# ====================================================================================================


def _period_delta(period: str) -> Optional[timedelta]:
    """
    Convert a period name to a timedelta.

    Args:
        period : Period name ('daily', 'weekly', 'monthly').

    Returns:
        Corresponding timedelta, or None if unknown.
    """
    return {
        "daily"   : timedelta(days=1),
        "weekly"  : timedelta(weeks=1),
        "monthly" : timedelta(days=30),
    }.get(period)


# ====================================================================================================
# Internal BudgetService (admin compat)
# ====================================================================================================


class BudgetService:
    """
    Internal implementation for admin endpoints.

    Prefer BudgetAuthRunnable / BudgetDeductRunnable for LangChain pipelines.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with a database session.

        Args:
            db : Async database session.
        """
        self._db = db

    async def authenticate(
        self,
        raw_token               : str,
        requested_abstraction   : Optional[ModelAbstraction] = None,
    ) -> Any:
        """
        Authenticate a raw token and check budget availability.

        Args:
            raw_token             : Raw access token string.
            requested_abstraction : Optional model abstraction to validate.

        Returns:
            Authenticated AccessToken instance.

        Raises:
            BudgetError : If authentication fails.
        """
        # Lazy import to avoid circular deps with runs/
        from src.runnables.budget_auth import BudgetAuthInput, BudgetAuthRunnable
        runnable = BudgetAuthRunnable()
        result = await runnable.ainvoke(BudgetAuthInput(
            raw_token=raw_token, abstraction=requested_abstraction
        ))
        if not result.success:
            raise BudgetError(result.error_message or "Authentication failed", result.status)
        return result.access_token

    async def deduct(self, **kwargs: Any) -> None:
        """
        Record token usage and deduct from budget.

        Args:
            **kwargs : Arguments forwarded to BudgetDeductInput.
        """
        from src.runnables.budget_deduct import BudgetDeductInput, BudgetDeductRunnable
        runnable = BudgetDeductRunnable()
        await runnable.ainvoke(BudgetDeductInput(**kwargs))

    async def create_token(
        self,
        label           : str,
        owner           : str,
        budget_type     : BudgetType          = BudgetType.FIXED,
        token_budget    : Optional[int]        = None,
        valid_until     : Optional[datetime]    = None,
        refresh_period  : Optional[str]         = None,
        allowed_models  : Optional[List[str]]   = None,
        rate_limit_rpm  : Optional[int]         = None,
        metadata        : Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Any]:
        """
        Create a new access token.

        Args:
            label          : Human-readable label.
            owner          : Owner identifier.
            budget_type    : Type of budget (FIXED, TIME_BASED, UNLIMITED).
            token_budget   : Maximum token count.
            valid_until    : Expiration datetime.
            refresh_period : Refresh interval name ('daily', 'weekly', 'monthly').
            allowed_models : List of allowed model abstraction values.
            rate_limit_rpm : Rate limit in requests per minute.
            metadata       : Arbitrary metadata dictionary.

        Returns:
            Tuple of (raw_token, AccessToken instance).
        """
        from src.db.models import AccessToken
        raw, token_hash = generate_token()
        token = AccessToken(
            token_hash      = token_hash,
            label           = label,
            owner           = owner,
            budget_type     = budget_type,
            token_budget    = token_budget,
            valid_until     = valid_until,
            refresh_period  = refresh_period,
            allowed_models  = allowed_models or [],
            rate_limit_rpm  = rate_limit_rpm,
            metadata_       = metadata or {},
        )
        self._db.add(token)
        await self._db.flush()
        return raw, token
