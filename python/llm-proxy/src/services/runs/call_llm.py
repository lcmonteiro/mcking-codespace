"""
CallLlmRunnable — LangGraph node that invokes the resolved LangChain model.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from langchain_core.runnables import Runnable, RunnableConfig

from src.db.models import RequestStatus


class CallLlmRunnable(Runnable[Dict, Dict]):
    """
    Graph node — invoke the resolved LangChain model with prepared messages.
    Reads 'model' and 'lc_messages' from state. Writes 'response_text',
    'prompt_tokens', 'completion_tokens', 'latency_ms', 'status' back.
    Skips if state already in error.
    """

    async def ainvoke(
        self,
        input: Dict,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> Dict:
        if input.get("status") != RequestStatus.SUCCESS:
            return {}

        model = input["model"]
        msgs = input["lc_messages"]
        t0 = time.monotonic()

        try:
            response = await model.ainvoke(msgs)
            latency = int((time.monotonic() - t0) * 1000)
            usage = getattr(response, "usage_metadata", None) or {}
            prompt_t = usage.get("input_tokens", 0)
            comp_t = usage.get("output_tokens", 0)
            return {
                "response_text": response.content,
                "prompt_tokens": prompt_t,
                "completion_tokens": comp_t,
                "latency_ms": latency,
                "status": RequestStatus.SUCCESS,
            }
        except Exception as exc:
            latency = int((time.monotonic() - t0) * 1000)
            return {
                "status": RequestStatus.ERROR,
                "error_message": str(exc),
                "latency_ms": latency,
            }
