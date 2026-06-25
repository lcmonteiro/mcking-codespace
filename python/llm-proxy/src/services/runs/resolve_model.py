"""
ResolveModelRunnable — LangGraph node that resolves the model abstraction.
Wraps ModelResolveRunnable for graph state compatibility.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from langchain_core.runnables import Runnable, RunnableConfig

from src.db.models import RequestStatus
from src.services.runs.model_resolve import ModelResolveInput, ModelResolveRunnable


class ResolveModelRunnable(Runnable[Dict, Dict]):
    """
    Graph node — resolve the model abstraction to a concrete LangChain model.
    Reads 'abstraction' and 'override_params' from state. Writes 'model',
    'mapping', 'provider_key' back into state. Skips if state already in error.
    """

    async def ainvoke(
        self,
        input: Dict,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> Dict:
        if input.get("status") != RequestStatus.SUCCESS:
            return {}
        resolver = ModelResolveRunnable()
        result = await resolver.ainvoke(ModelResolveInput(
            abstraction=input["abstraction"],
            override_params=input.get("override_params") or {},
        ))
        if result.success:
            return {
                "model": result.model,
                "mapping": result.mapping,
                "provider_key": result.provider_key,
            }
        return {"status": RequestStatus.ERROR, "error_message": result.error_message}
