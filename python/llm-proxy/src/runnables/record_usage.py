"""
RecordUsageRunnable — LangGraph node that persists usage to the audit log.
Wraps BudgetDeductRunnable for graph state compatibility.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from langchain_core.runnables import Runnable, RunnableConfig

from src.runnables.budget_deduct import BudgetDeductInput, BudgetDeductRunnable


class RecordUsageRunnable(Runnable[Dict, Dict]):
    """
    Graph node — persist usage to the audit log and deduct from token budget.
    Reads 'access_token', 'mapping', 'provider_key' and token counters from state.
    Skips if no token/mapping/key (nothing to record).
    """

    async def ainvoke(
        self,
        input: Dict,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> Dict:
        token = input.get("access_token")
        mapping = input.get("mapping")
        key = input.get("provider_key")

        if not token or not mapping or not key:
            return {}  # nothing to record

        deduct = BudgetDeductRunnable()
        await deduct.ainvoke(BudgetDeductInput(
            token=token,
            prompt_tokens=input.get("prompt_tokens", 0),
            completion_tokens=input.get("completion_tokens", 0),
            provider_key_id=key.id,
            abstraction=input["abstraction"].value,
            provider=mapping.provider,
            model_name=mapping.model_name,
            latency_ms=input.get("latency_ms", 0),
            request_id=input.get("request_id"),
            ip_address=input.get("ip_address"),
            error_message=input.get("error_message"),
            status=input.get("status"),
        ))
        return {}
