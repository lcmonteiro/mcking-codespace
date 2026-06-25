"""
ProxyRunnable — end-to-end proxy pipeline as a single LangChain Runnable.

Assembles a LangGraph with 5 nodes (all LangChain Runnables) and exposes:
  - ProxyRunnable        : non-streaming entry point
  - run_proxy()          : convenience wrapper
  - run_proxy_stream()   : streaming entry point (bypasses graph)

Every path through the graph ends at [RecordUsage] so even blocked/errored
requests are logged.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, TypedDict

from langchain_core.messages import (
    AIMessage, BaseMessage, HumanMessage, SystemMessage,
)
from langchain_core.runnables import Runnable, RunnableConfig
from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from src.db.models import ModelAbstraction, RequestStatus
from src.services.runs.validate_budget import ValidateBudgetRunnable
from src.services.runs.resolve_model import ResolveModelRunnable
from src.services.runs.prepare_messages import PrepareMessagesRunnable
from src.services.runs.call_llm import CallLlmRunnable
from src.services.runs.record_usage import RecordUsageRunnable
from src.services.runs.budget_auth import BudgetAuthInput, BudgetAuthRunnable
from src.services.runs.budget_deduct import BudgetDeductInput, BudgetDeductRunnable
from src.services.runs.model_resolve import ModelResolveInput, ModelResolveRunnable
from src.services.budget import BudgetError


# ═══════════════════════════════════════════════════════════════════════════════
# State — shared TypedDict for LangGraph
# ═══════════════════════════════════════════════════════════════════════════════

class ProxyState(TypedDict):
    """Mutable state flowing through the graph pipeline."""
    # ── Inputs ─────────────────────────────────────────────────────────────────
    request_id:       str
    raw_token:        str
    abstraction:      ModelAbstraction
    messages:         List[Dict[str, str]]
    override_params:  Dict[str, Any]
    ip_address:       Optional[str]

    # ── Populated by nodes ─────────────────────────────────────────────────────
    access_token:     Optional[Any]          # AccessToken ORM
    model:            Optional[Any]          # BaseChatModel instance
    mapping:          Optional[Any]          # ModelMapping ORM
    provider_key:     Optional[Any]          # ProviderKey ORM
    lc_messages:      Optional[List[BaseMessage]]

    # ── Outputs ────────────────────────────────────────────────────────────────
    response_text:      Optional[str]
    prompt_tokens:      int
    completion_tokens:  int
    latency_ms:         int
    status:             RequestStatus
    error_message:      Optional[str]


# ═══════════════════════════════════════════════════════════════════════════════
# Routing functions (plain callables for LangGraph conditional edges)
# ═══════════════════════════════════════════════════════════════════════════════

def route_after_budget(state: ProxyState) -> str:
    return "resolve_model" if state.get("status") == RequestStatus.SUCCESS else "record_usage"


def route_after_model(state: ProxyState) -> str:
    return "prepare_messages" if state.get("status") == RequestStatus.SUCCESS else "record_usage"


def route_after_llm(state: ProxyState) -> str:
    return "record_usage"


# ═══════════════════════════════════════════════════════════════════════════════
# Pipeline (compiled singleton)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_graph() -> StateGraph:
    """Assemble the LangGraph state machine from Runnable nodes."""
    g = StateGraph(ProxyState)

    g.add_node("validate_budget",  ValidateBudgetRunnable())
    g.add_node("resolve_model",    ResolveModelRunnable())
    g.add_node("prepare_messages", PrepareMessagesRunnable())
    g.add_node("call_llm",         CallLlmRunnable())
    g.add_node("record_usage",     RecordUsageRunnable())

    g.set_entry_point("validate_budget")

    g.add_conditional_edges("validate_budget", route_after_budget, {
        "resolve_model": "resolve_model",
        "record_usage":  "record_usage",
    })
    g.add_conditional_edges("resolve_model", route_after_model, {
        "prepare_messages": "prepare_messages",
        "record_usage":     "record_usage",
    })
    g.add_edge("prepare_messages", "call_llm")
    g.add_conditional_edges("call_llm", route_after_llm, {
        "record_usage": "record_usage",
    })
    g.add_edge("record_usage", END)

    return g


_graph = _build_graph().compile()


# ═══════════════════════════════════════════════════════════════════════════════
# ProxyRunnable — top-level Runnable
# ═══════════════════════════════════════════════════════════════════════════════

class ProxyInput(BaseModel):
    """Input schema for ProxyRunnable (non-streaming)."""
    raw_token:       str
    abstraction:     ModelAbstraction
    messages:        List[Dict[str, str]]
    override_params: Dict[str, Any] = {}
    ip_address:      Optional[str] = None


class ProxyOutput(BaseModel):
    """Output schema for ProxyRunnable (non-streaming)."""
    request_id:       str = ""
    response_text:    Optional[str] = None
    prompt_tokens:    int = 0
    completion_tokens: int = 0
    total_tokens:     int = 0
    latency_ms:       int = 0
    status:           RequestStatus = RequestStatus.SUCCESS
    error_message:    Optional[str] = None
    model_provider:   Optional[str] = None
    model_name:       Optional[str] = None


class ProxyRunnable(Runnable[ProxyInput, ProxyOutput]):
    """
    End-to-end proxy pipeline as a LangChain Runnable.

    Usage:
        output = await proxy_runnable.ainvoke(ProxyInput(
            raw_token="llmp_...",
            abstraction=ModelAbstraction.CHAT,
            messages=[{"role": "user", "content": "Hello!"}],
        ))
        print(output.response_text)
    """

    async def ainvoke(
        self,
        input: ProxyInput,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> ProxyOutput:
        initial: ProxyState = {
            "request_id":        str(uuid.uuid4()),
            "raw_token":         input.raw_token,
            "abstraction":       input.abstraction,
            "messages":          input.messages,
            "override_params":   input.override_params,
            "ip_address":        input.ip_address,
            "access_token":      None,
            "model":             None,
            "mapping":           None,
            "provider_key":      None,
            "lc_messages":       None,
            "response_text":     None,
            "prompt_tokens":     0,
            "completion_tokens": 0,
            "latency_ms":        0,
            "status":            RequestStatus.SUCCESS,
            "error_message":     None,
        }
        state = await _graph.ainvoke(initial)

        mapping = state.get("mapping")
        return ProxyOutput(
            request_id=state.get("request_id", ""),
            response_text=state.get("response_text"),
            prompt_tokens=state.get("prompt_tokens", 0),
            completion_tokens=state.get("completion_tokens", 0),
            total_tokens=state.get("prompt_tokens", 0) + state.get("completion_tokens", 0),
            latency_ms=state.get("latency_ms", 0),
            status=state.get("status", RequestStatus.SUCCESS),
            error_message=state.get("error_message"),
            model_provider=mapping.provider if mapping else None,
            model_name=mapping.model_name if mapping else None,
        )


# Singleton for direct use in routes
proxy_runnable = ProxyRunnable()


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience entry points (backward-compatible)
# ═══════════════════════════════════════════════════════════════════════════════

async def run_proxy(
    raw_token: str,
    abstraction: ModelAbstraction,
    messages: List[Dict[str, str]],
    override_params: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> ProxyOutput:
    """Non-streaming entry point — delegates to proxy_runnable."""
    return await proxy_runnable.ainvoke(ProxyInput(
        raw_token=raw_token,
        abstraction=abstraction,
        messages=messages,
        override_params=override_params or {},
        ip_address=ip_address,
    ))


async def run_proxy_stream(
    raw_token: str,
    abstraction: ModelAbstraction,
    messages: List[Dict[str, str]],
    override_params: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> AsyncIterator[tuple]:
    """
    Streaming entry point.
    Yields (chunk_text, prompt_tokens, completion_tokens, mapping).

    Auth + budget validation happens before streaming; usage is recorded
    after the stream exhausts.  This bypasses the graph (LangGraph does not
    natively support streaming token-by-token through the graph), but uses
    the same individual Runnable services.
    """
    request_id = str(uuid.uuid4())

    # ── 1. Auth + budget check ────────────────────────────────────────────────
    auth = BudgetAuthRunnable()
    auth_result = await auth.ainvoke(BudgetAuthInput(raw_token=raw_token, abstraction=abstraction))
    if not auth_result.success:
        raise BudgetError(
            auth_result.error_message or "Authentication failed",
            auth_result.status,
        )

    # ── 2. Resolve model ──────────────────────────────────────────────────────
    resolver = ModelResolveRunnable()
    resolve_result = await resolver.ainvoke(ModelResolveInput(
        abstraction=abstraction,
        override_params=override_params or {},
    ))
    if not resolve_result.success:
        raise ValueError(resolve_result.error_message or "Model resolution failed")

    model, mapping, key = resolve_result.model, resolve_result.mapping, resolve_result.provider_key

    # ── 3. Build LangChain messages ───────────────────────────────────────────
    lc: List[BaseMessage] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
        if role == "system":
            lc.append(SystemMessage(content=content))
        elif role == "assistant":
            lc.append(AIMessage(content=content))
        else:
            lc.append(HumanMessage(content=content))

    # ── 4. Stream ─────────────────────────────────────────────────────────────
    t0 = time.monotonic()
    full_text = ""
    prompt_tokens = 0
    completion_tokens = 0

    try:
        async for chunk in model.astream(lc):
            text = chunk.content or ""
            full_text += text
            usage = getattr(chunk, "usage_metadata", None) or {}
            if usage.get("input_tokens"):
                prompt_tokens = usage["input_tokens"]
                completion_tokens = usage.get("output_tokens", 0)
            yield text, prompt_tokens, completion_tokens, mapping
    finally:
        # ── 5. Record usage ───────────────────────────────────────────────────
        latency = int((time.monotonic() - t0) * 1000)
        if not prompt_tokens:
            prompt_tokens = len(" ".join(m.get("content", "") for m in messages).split()) * 4 // 3
            completion_tokens = len(full_text.split()) * 4 // 3

        deduct = BudgetDeductRunnable()
        await deduct.ainvoke(BudgetDeductInput(
            token=auth_result.access_token,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            provider_key_id=key.id,
            abstraction=abstraction.value,
            provider=mapping.provider,
            model_name=mapping.model_name,
            latency_ms=latency,
            request_id=request_id,
            ip_address=ip_address,
            status=RequestStatus.SUCCESS,
        ))
