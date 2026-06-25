"""
LangGraph Proxy Pipeline

State machine that processes a proxy request:

  [validate_budget] → [resolve_model] → [call_llm] → [record_usage]
                                              ↓ (on error)
                                        [handle_error]

Each node receives the full ProxyState and returns a partial update.
"""
from __future__ import annotations

import time
import uuid
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END

from src.db.models import ModelAbstraction, RequestStatus
from src.db.session import AsyncSessionLocal
from src.services.budget import BudgetError, BudgetService
from src.services.model_registry import ModelRegistry


# ─── State ────────────────────────────────────────────────────────────────────

class ProxyState(TypedDict):
    # ── Inputs (set before graph runs) ───────────────────────────────────────
    request_id:    str
    raw_token:     str
    abstraction:   ModelAbstraction
    messages:      List[Dict[str, str]]   # [{"role": "user"|"assistant"|"system", "content": "..."}]
    override_params: Dict[str, Any]
    ip_address:    Optional[str]

    # ── Populated by nodes ────────────────────────────────────────────────────
    access_token:  Optional[Any]          # AccessToken ORM object
    model:         Optional[Any]          # BaseChatModel instance
    mapping:       Optional[Any]          # ModelMapping ORM object
    provider_key:  Optional[Any]          # ProviderKey ORM object
    lc_messages:   Optional[List[BaseMessage]]

    # ── Outputs ───────────────────────────────────────────────────────────────
    response_text:      Optional[str]
    prompt_tokens:      int
    completion_tokens:  int
    latency_ms:         int
    status:             RequestStatus
    error_message:      Optional[str]


# ─── Graph Nodes ──────────────────────────────────────────────────────────────

async def validate_budget(state: ProxyState) -> Dict:
    """Authenticate the token and verify budget availability."""
    async with AsyncSessionLocal() as db:
        svc = BudgetService(db)
        try:
            token = await svc.authenticate(
                raw_token=state["raw_token"],
                requested_abstraction=state["abstraction"],
            )
            await db.commit()
            return {"access_token": token, "status": RequestStatus.SUCCESS}
        except BudgetError as exc:
            return {
                "status":        exc.status,
                "error_message": str(exc),
            }


async def resolve_model(state: ProxyState) -> Dict:
    """Resolve the model abstraction to a concrete LangChain model."""
    if state.get("status") != RequestStatus.SUCCESS:
        return {}  # skip — already failed

    async with AsyncSessionLocal() as db:
        registry = ModelRegistry(db)
        try:
            model, mapping, key = await registry.resolve(
                abstraction=state["abstraction"],
                override_params=state.get("override_params") or {},
            )
            return {"model": model, "mapping": mapping, "provider_key": key}
        except ValueError as exc:
            return {
                "status":        RequestStatus.ERROR,
                "error_message": str(exc),
            }


async def prepare_messages(state: ProxyState) -> Dict:
    """Convert raw message dicts to LangChain message objects."""
    if state.get("status") != RequestStatus.SUCCESS:
        return {}

    lc: List[BaseMessage] = []
    for msg in state["messages"]:
        role    = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            lc.append(SystemMessage(content=content))
        elif role == "assistant":
            lc.append(AIMessage(content=content))
        else:
            lc.append(HumanMessage(content=content))

    return {"lc_messages": lc}


async def call_llm(state: ProxyState) -> Dict:
    """Invoke the LangChain model and capture the response."""
    if state.get("status") != RequestStatus.SUCCESS:
        return {}

    model  = state["model"]
    msgs   = state["lc_messages"]
    t0     = time.monotonic()

    try:
        response = await model.ainvoke(msgs)
        latency  = int((time.monotonic() - t0) * 1000)

        # Token usage — LangChain exposes these on response.usage_metadata
        usage    = getattr(response, "usage_metadata", None) or {}
        prompt_t = usage.get("input_tokens", 0)
        comp_t   = usage.get("output_tokens", 0)

        return {
            "response_text":     response.content,
            "prompt_tokens":     prompt_t,
            "completion_tokens": comp_t,
            "latency_ms":        latency,
            "status":            RequestStatus.SUCCESS,
        }
    except Exception as exc:
        latency = int((time.monotonic() - t0) * 1000)
        return {
            "status":        RequestStatus.ERROR,
            "error_message": str(exc),
            "latency_ms":    latency,
        }


async def record_usage(state: ProxyState) -> Dict:
    """Persist usage to the audit log and deduct from the token budget."""
    token    = state.get("access_token")
    mapping  = state.get("mapping")
    key      = state.get("provider_key")

    if not token or not mapping or not key:
        return {}  # nothing to record (auth failed before model was resolved)

    async with AsyncSessionLocal() as db:
        svc = BudgetService(db)
        await svc.deduct(
            token=token,
            prompt_tokens=state.get("prompt_tokens", 0),
            completion_tokens=state.get("completion_tokens", 0),
            provider_key_id=key.id,
            abstraction=state["abstraction"].value,
            provider=mapping.provider,
            model_name=mapping.model_name,
            latency_ms=state.get("latency_ms", 0),
            request_id=state.get("request_id"),
            ip_address=state.get("ip_address"),
            error_message=state.get("error_message"),
            status=state.get("status", RequestStatus.ERROR),
        )
        await db.commit()
    return {}


# ─── Routing ──────────────────────────────────────────────────────────────────

def _route_after_budget(state: ProxyState) -> str:
    if state.get("status") != RequestStatus.SUCCESS:
        return "record_usage"  # skip LLM, log the block
    return "resolve_model"


def _route_after_model(state: ProxyState) -> str:
    if state.get("status") != RequestStatus.SUCCESS:
        return "record_usage"
    return "prepare_messages"


def _route_after_llm(state: ProxyState) -> str:
    return "record_usage"  # always record


# ─── Graph Assembly ───────────────────────────────────────────────────────────

def build_proxy_graph() -> StateGraph:
    g = StateGraph(ProxyState)

    g.add_node("validate_budget",  validate_budget)
    g.add_node("resolve_model",    resolve_model)
    g.add_node("prepare_messages", prepare_messages)
    g.add_node("call_llm",         call_llm)
    g.add_node("record_usage",     record_usage)

    g.set_entry_point("validate_budget")

    g.add_conditional_edges("validate_budget",  _route_after_budget, {
        "resolve_model": "resolve_model",
        "record_usage":  "record_usage",
    })
    g.add_conditional_edges("resolve_model",    _route_after_model, {
        "prepare_messages": "prepare_messages",
        "record_usage":     "record_usage",
    })
    g.add_edge("prepare_messages", "call_llm")
    g.add_conditional_edges("call_llm", _route_after_llm, {
        "record_usage": "record_usage",
    })
    g.add_edge("record_usage", END)

    return g


# Compiled graph (singleton)
_proxy_graph = build_proxy_graph().compile()


async def run_proxy(
    raw_token: str,
    abstraction: ModelAbstraction,
    messages: List[Dict[str, str]],
    override_params: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> ProxyState:
    """Entry point — run the full proxy pipeline and return final state."""
    initial: ProxyState = {
        "request_id":      str(uuid.uuid4()),
        "raw_token":       raw_token,
        "abstraction":     abstraction,
        "messages":        messages,
        "override_params": override_params or {},
        "ip_address":      ip_address,
        # Populated by nodes:
        "access_token":    None,
        "model":           None,
        "mapping":         None,
        "provider_key":    None,
        "lc_messages":     None,
        "response_text":   None,
        "prompt_tokens":   0,
        "completion_tokens": 0,
        "latency_ms":      0,
        "status":          RequestStatus.SUCCESS,
        "error_message":   None,
    }
    return await _proxy_graph.ainvoke(initial)


async def run_proxy_stream(
    raw_token: str,
    abstraction: ModelAbstraction,
    messages: List[Dict[str, str]],
    override_params: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
):
    """
    Streaming entry point.
    Yields tuples of (chunk_text, prompt_tokens, completion_tokens, mapping).
    Handles auth + budget validation before streaming begins, then records
    usage after the stream is exhausted.
    """
    from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage

    request_id = str(uuid.uuid4())

    # ── 1. Auth + budget check ─────────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        svc = BudgetService(db)
        try:
            token = await svc.authenticate(raw_token, abstraction)
            await db.commit()
        except BudgetError as exc:
            raise exc

    # ── 2. Resolve model ───────────────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        registry = ModelRegistry(db)
        model, mapping, key = await registry.resolve(abstraction, override_params or {})

    # ── 3. Build LangChain messages ────────────────────────────────────────
    lc: List[BaseMessage] = []
    for msg in messages:
        role    = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
        if role == "system":
            lc.append(SystemMessage(content=content))
        elif role == "assistant":
            lc.append(AIMessage(content=content))
        else:
            lc.append(HumanMessage(content=content))

    # ── 4. Stream ──────────────────────────────────────────────────────────
    t0 = time.monotonic()
    full_text         = ""
    prompt_tokens     = 0
    completion_tokens = 0

    try:
        async for chunk in model.astream(lc):
            text = chunk.content or ""
            full_text += text

            # Accumulate usage if provided mid-stream
            usage = getattr(chunk, "usage_metadata", None) or {}
            if usage.get("input_tokens"):
                prompt_tokens     = usage["input_tokens"]
                completion_tokens = usage.get("output_tokens", 0)

            yield text, prompt_tokens, completion_tokens, mapping

    finally:
        # ── 5. Record usage ────────────────────────────────────────────────
        latency = int((time.monotonic() - t0) * 1000)
        # Estimate tokens if provider didn't send them mid-stream
        if not prompt_tokens:
            prompt_tokens     = len(" ".join(m.get("content", "") for m in messages).split()) * 4 // 3
            completion_tokens = len(full_text.split()) * 4 // 3

        async with AsyncSessionLocal() as db:
            svc = BudgetService(db)
            await svc.deduct(
                token=token,
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
            )
            await db.commit()
