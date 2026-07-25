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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Wallet, WalletProviderLink, ProviderKey, ModelAbstraction
from src.db.session import db_contex
from src.services.budget import BudgetError, _hash_token
from src.services.credit_models import CreditModelFactory, CreditState

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
    status        : str            = "BLOCKED"  # Using string to match RequestStatus values
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
            wallet = result.access_token
    """

    async def ainvoke(
        self,
        input    : BudgetAuthInput,
        config   : Optional[RunnableConfig] = None,
        **kwargs : Any,
    ) -> BudgetAuthOutput:
        token_hash = _hash_token(input.raw_token)

        async with db_contex() as db:
            # Look up wallet by token_hash
            result = await db.execute(
                select(Wallet).where(Wallet.token_hash == token_hash)
            )
            wallet: Optional[Wallet] = result.scalars().first()

            if wallet is None:
                return BudgetAuthOutput(
                    success       = False,
                    status        = "BLOCKED",
                    error_message = "Invalid access token.",
                )

            # Check wallet status
            if wallet.status != "active":
                return BudgetAuthOutput(
                    success       = False,
                    status        = "BLOCKED",
                    error_message = f"Wallet is not active (status: {wallet.status}).",
                )

            # Check validity window
            now = datetime.now(timezone.utc)
            if wallet.valid_until:
                vu = wallet.valid_until
                if vu.tzinfo is None:
                    vu = vu.replace(tzinfo=timezone.utc)
                if now > vu:
                    return BudgetAuthOutput(
                        success       = False,
                        status        = "BLOCKED",
                        error_message = "Wallet has expired (validity window exceeded).",
                    )

            # Check allowed models
            if wallet.allowed_models is not None and len(wallet.allowed_models) > 0:
                if input.abstraction is None:
                    # No abstraction specified, but wallet has restrictions -> not allowed
                    return BudgetAuthOutput(
                        success       = False,
                        status        = "BLOCKED",
                        error_message = "Wallet requires an abstraction to be specified.",
                    )
                if input.abstraction.value not in wallet.allowed_models:
                    return BudgetAuthOutput(
                        success       = False,
                        status        = "BLOCKED",
                        error_message = f"Wallet is not permitted to use '{input.abstraction.value}' model abstraction.",
                    )

            # Check that at least one linked provider has available credit
            # Fetch linked providers for this wallet
            links_result = await db.execute(
                select(WalletProviderLink, ProviderKey)
                .join(ProviderKey, WalletProviderLink.provider_key_id == ProviderKey.id)
                .where(WalletProviderLink.wallet_id == wallet.id)
            )
            links = links_result.all()

            if not links:
                return BudgetAuthOutput(
                    success       = False,
                    status        = "BLOCKED",
                    error_message = "Wallet has no linked providers with credit.",
                )

            # Check each linked provider for available credit
            has_available_credit = False
            for link, provider in links:
                # Build credit state from provider fields
                # Note: ProviderKey has credit_model, budget_amount, budget_spent, last_reset_at
                credit_state = CreditState(
                    budget_amount=provider.budget_amount,
                    budget_spent=provider.budget_spent,
                    last_reset_at=provider.last_reset_at or datetime.now(timezone.utc),
                    credit_model=CreditModelType(provider.credit_model),  # Convert string to enum
                )

                # Check if provider can spend at least 1 unit (we don't know the amount yet, but we just need to know if there's any credit)
                # We'll check for an amount of 1 token (or 1 unit of credit). The actual deduction will happen later.
                if credit_state.budget_available > 0:
                    has_available_credit = True
                    break

            if not has_available_credit:
                return BudgetAuthOutput(
                    success       = False,
                    status        = "BLOCKED",
                    error_message = "No linked provider has available credit.",
                )

            # All checks passed
            await db.commit()
            return BudgetAuthOutput(
                success      = True,
                access_token = wallet,
                status       = "SUCCESS",
            )


# Note: We removed the refresh logic because wallets do not have a budget that refreshes.
# The budget is managed by the provider keys.