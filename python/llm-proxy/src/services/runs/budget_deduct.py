"""
BudgetDeductRunnable — deducts tokens from budget and records usage to the audit log.

LangChain Runnable with typed Pydantic I/O.
"""
from __future__ import annotations

from typing import Any, Optional

from langchain_core.runnables import Runnable, RunnableConfig
from pydantic import BaseModel, ConfigDict
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AccessToken, BudgetType, RequestStatus, TokenStatus, UsageLog
from src.db.session import AsyncSessionLocal


# ─── I/O Schema ───────────────────────────────────────────────────────────────

class BudgetDeductInput(BaseModel):
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


# ─── Runnable ─────────────────────────────────────────────────────────────────

class BudgetDeductRunnable(Runnable[BudgetDeductInput, dict]):
    """
    Deduct tokens from the access token budget and persist an audit log entry.

    Usage:
        await BudgetDeductRunnable().ainvoke(BudgetDeductInput(
            token=access_token_obj,
            prompt_tokens=100,
            completion_tokens=50,
            provider_key_id="...",
            abstraction="coding",
            provider="openai",
            model_name="gpt-4o",
            latency_ms=1200,
        ))
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
                # Check exhaustion threshold
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

            # Immutable audit log entry
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
