# ====================================================================================================
# BudgetDeductRunnable
# ====================================================================================================

"""
BudgetDeductRunnable — deducts tokens from budget and records usage to the audit log.

LangChain Runnable with typed Pydantic I/O.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from langchain_core.runnables import Runnable, RunnableConfig
from pydantic import BaseModel, ConfigDict
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ProviderKey, RequestStatus, UsageLog, Wallet
from src.db.session import db_contex
from src.services.credit_models import CreditModelType, CreditState

logger = logging.getLogger(__name__)


# ====================================================================================================
# I/O Schema
# ====================================================================================================


class BudgetDeductInput(BaseModel):
    """Input schema for budget deduction."""

    token             : Any              = None
    prompt_tokens     : int              = 0
    completion_tokens : int              = 0
    provider_key_id   : str              = ""
    abstraction       : str              = ""
    provider          : str              = ""
    model_name        : str              = ""
    latency_ms        : int              = 0
    request_id        : Optional[str]    = None
    ip_address        : Optional[str]    = None
    error_message     : Optional[str]    = None
    status            : RequestStatus    = RequestStatus.SUCCESS

    model_config = ConfigDict(arbitrary_types_allowed=True)


# ====================================================================================================
# Runnable
# ====================================================================================================


class BudgetDeductRunnable(Runnable[BudgetDeductInput, dict]):
    """
    Deduct tokens from the access token budget and persist an audit log entry.

    Usage:
        result = await BudgetDeductRunnable().ainvoke(BudgetDeductInput(
            token            = access_token_obj,
            prompt_tokens    = 100,
            completion_tokens = 50,
            provider_key_id  = "...",
            abstraction      = "coding",
            provider         = "openai",
            model_name       = "gpt-4o",
            latency_ms       = 1200,
        ))
    """

    async def ainvoke(
        self,
        input    : BudgetDeductInput,
        config   : Optional[RunnableConfig] = None,
        **kwargs : Any,
    ) -> dict:
        async with db_contex() as db:
            total = input.prompt_tokens + input.completion_tokens

            # Deduct from provider's credit budget
            if input.provider_key_id:
                pk = await db.get(ProviderKey, input.provider_key_id)
                if pk:
                    # Build CreditState and maybe reset for monthly_reset model
                    state = CreditState(
                        budget_amount = pk.budget_amount or 0,
                        budget_spent  = pk.budget_spent,
                        last_reset_at = pk.last_reset_at,
                        credit_model  = CreditModelType(pk.credit_model),
                    )

                    # Deduct from provider budget
                    if state.budget_available >= total:
                        pk.budget_spent  += total
                        pk.tokens_used   += total
                        pk.last_used_at  = datetime.now(timezone.utc)
                    else:
                        logger.warning(
                            "Insufficient provider credit: available=%d, requested=%d",
                            state.budget_available, total,
                        )

            # Immutable audit log entry
            log = UsageLog(
                wallet_id        = getattr(input.token, "id", None) if input.token else None,
                provider_key_id  = input.provider_key_id,
                abstraction      = input.abstraction,
                provider         = input.provider,
                model_name       = input.model_name,
                prompt_tokens    = input.prompt_tokens,
                completion_tokens = input.completion_tokens,
                total_tokens     = total,
                latency_ms       = input.latency_ms,
                status           = input.status,
                error_message    = input.error_message,
                request_id       = input.request_id,
                ip_address       = input.ip_address,
            )
            db.add(log)
            await db.commit()
        return {}
