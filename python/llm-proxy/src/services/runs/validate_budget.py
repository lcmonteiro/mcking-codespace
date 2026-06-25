"""
ValidateBudgetRunnable — LangGraph node that authenticates the proxy token.
Wraps BudgetAuthRunnable for graph state compatibility.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from langchain_core.runnables import Runnable, RunnableConfig

from src.db.models import RequestStatus
from src.services.runs.budget_auth import BudgetAuthInput, BudgetAuthRunnable


class ValidateBudgetRunnable(Runnable[Dict, Dict]):
    """
    Graph node — authenticate the proxy token and verify budget availability.
    Reads 'raw_token' and 'abstraction' from state. Writes 'access_token'
    and 'status' back into state.
    """

    async def ainvoke(
        self,
        input: Dict,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> Dict:
        auth = BudgetAuthRunnable()
        result = await auth.ainvoke(BudgetAuthInput(
            raw_token=input["raw_token"],
            abstraction=input.get("abstraction"),
        ))
        if result.success:
            return {"access_token": result.access_token, "status": RequestStatus.SUCCESS}
        return {"status": result.status, "error_message": result.error_message}
