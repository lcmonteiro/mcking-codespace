"""
PrepareMessagesRunnable — LangGraph node that converts raw message dicts to
LangChain BaseMessage objects.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.messages import (
    AIMessage, BaseMessage, HumanMessage, SystemMessage,
)
from langchain_core.runnables import Runnable, RunnableConfig

from src.db.models import RequestStatus


class PrepareMessagesRunnable(Runnable[Dict, Dict]):
    """
    Graph node — convert raw message dicts to LangChain message objects.
    Reads 'messages' from state. Writes 'lc_messages' back into state.
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

        lc: List[BaseMessage] = []
        for msg in input["messages"]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                lc.append(SystemMessage(content=content))
            elif role == "assistant":
                lc.append(AIMessage(content=content))
            else:
                lc.append(HumanMessage(content=content))

        return {"lc_messages": lc}
