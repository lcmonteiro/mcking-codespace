"""
Proxy Pipeline — end-to-end LLM Proxy as a pure LangChain Runnable.

Estrutura:
  [preprocess]  →  [model.astream()]  →  [postprocess]
     auth                    tokens           audit_log
     resolve
     prepare

Non-streaming:   proxy_runnable.ainvoke(input)
Streaming:       proxy_runnable.astream(input)  →  yields tokens natively
"""
from __future__ import annotations

import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from langchain_core.messages import (
    AIMessage, BaseMessage, HumanMessage, SystemMessage,
)
from langchain_core.runnables import Runnable, RunnableConfig
from pydantic import BaseModel

from src.db.models import ModelAbstraction, RequestStatus
from src.runnables.budget_auth import BudgetAuthInput, BudgetAuthRunnable
from src.runnables.budget_deduct import BudgetDeductInput, BudgetDeductRunnable
from src.runnables.model_resolve import ModelResolveInput, ModelResolveRunnable
from src.services.budget import BudgetError


# ═══════════════════════════════════════════════════════════════════════════════
# I/O Schemas
# ═══════════════════════════════════════════════════════════════════════════════

class ProxyInput(BaseModel):
    raw_token:       str
    abstraction:     ModelAbstraction
    messages:        List[Dict[str, str]]
    override_params: Dict[str, Any] = {}
    ip_address:      Optional[str] = None


class ProxyOutput(BaseModel):
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


# ═══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _prepare_messages(messages: List[Dict[str, str]]) -> List[BaseMessage]:
    """Convert raw message dicts to LangChain message objects."""
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
    return lc


async def _setup(input: ProxyInput) -> tuple:
    """
    Pre-processing: authenticate token + resolve model + prepare messages.
    Returns (token, model, mapping, key, lc_messages).
    Raises BudgetError or ValueError on failure.
    """
    request_id = str(uuid.uuid4())

    # 1. Auth + budget check
    auth = BudgetAuthRunnable()
    auth_result = await auth.ainvoke(BudgetAuthInput(
        raw_token=input.raw_token,
        abstraction=input.abstraction,
    ))
    if not auth_result.success:
        raise BudgetError(
            auth_result.error_message or "Authentication failed",
            auth_result.status,
        )
    token = auth_result.access_token

    # 2. Resolve model
    resolver = ModelResolveRunnable()
    resolve_result = await resolver.ainvoke(ModelResolveInput(
        abstraction=input.abstraction,
        override_params=input.override_params,
    ))
    if not resolve_result.success:
        raise ValueError(resolve_result.error_message or "Model resolution failed")

    # 3. Prepare messages
    lc_messages = _prepare_messages(input.messages)

    return request_id, token, resolve_result.model, resolve_result.mapping, resolve_result.provider_key, lc_messages


async def _record(
    input: ProxyInput,
    request_id: str,
    token: Any,
    key: Any,
    mapping: Any,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    status: RequestStatus = RequestStatus.SUCCESS,
    error_message: Optional[str] = None,
) -> None:
    """Post-processing: persist audit log and deduct from budget."""
    deduct = BudgetDeductRunnable()
    await deduct.ainvoke(BudgetDeductInput(
        token=token,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        provider_key_id=key.id,
        abstraction=input.abstraction.value,
        provider=mapping.provider,
        model_name=mapping.model_name,
        latency_ms=latency_ms,
        request_id=request_id,
        ip_address=input.ip_address,
        error_message=error_message,
        status=status,
    ))


# ═══════════════════════════════════════════════════════════════════════════════
# ProxyRunnable — top-level Runnable (composable, streamable)
# ═══════════════════════════════════════════════════════════════════════════════

class ProxyRunnable(Runnable[ProxyInput, ProxyOutput]):
    """
    End-to-end proxy pipeline como LangChain Runnable.

    Non-streaming:
        output = await proxy_runnable.ainvoke(ProxyInput(...))

    Streaming (nativo — tokens do LLM um a um):
        async for chunk in proxy_runnable.astream(ProxyInput(...)):
            print(chunk)  # cada token do LLM
    """

    async def ainvoke(
        self,
        input: ProxyInput,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> ProxyOutput:
        try:
            request_id, token, model, mapping, key, lc = await _setup(input)
        except BudgetError as exc:
            return ProxyOutput(
                request_id=str(uuid.uuid4()),
                status=exc.status,
                error_message=str(exc),
            )
        except ValueError as exc:
            return ProxyOutput(
                request_id=str(uuid.uuid4()),
                status=RequestStatus.ERROR,
                error_message=str(exc),
            )

        t0 = time.monotonic()
        try:
            response = await model.ainvoke(lc)
            latency = int((time.monotonic() - t0) * 1000)
            usage = getattr(response, "usage_metadata", None) or {}
            prompt_t = usage.get("input_tokens", 0)
            comp_t = usage.get("output_tokens", 0)

            await _record(input, request_id, token, key, mapping, prompt_t, comp_t, latency)

            return ProxyOutput(
                request_id=request_id,
                response_text=response.content,
                prompt_tokens=prompt_t,
                completion_tokens=comp_t,
                total_tokens=prompt_t + comp_t,
                latency_ms=latency,
                status=RequestStatus.SUCCESS,
                model_provider=mapping.provider,
                model_name=mapping.model_name,
            )
        except Exception as exc:
            latency = int((time.monotonic() - t0) * 1000)
            prompt_t = len(" ".join(m.get("content", "") for m in input.messages).split()) * 4 // 3
            await _record(
                input, request_id, token, key, mapping,
                prompt_t, 0, latency,
                status=RequestStatus.ERROR, error_message=str(exc),
            )
            return ProxyOutput(
                request_id=request_id,
                status=RequestStatus.ERROR,
                error_message=str(exc),
                latency_ms=latency,
            )

    async def astream(
        self,
        input: ProxyInput,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ProxyOutput]:
        """
        Stream de tokens do LLM. Cada iteração devolve um chunk de texto.

        Exemplo:
            full = ""
            async for chunk in proxy_runnable.astream(ProxyInput(...)):
                print(chunk, end="", flush=True)
                full += chunk
        """
        try:
            request_id, token, model, mapping, key, lc = await _setup(input)
        except BudgetError as exc:
            yield ProxyOutput(
                request_id=str(uuid.uuid4()),
                status=exc.status,
                error_message=str(exc),
            )
            return
        except ValueError as exc:
            yield ProxyOutput(
                request_id=str(uuid.uuid4()),
                status=RequestStatus.ERROR,
                error_message=str(exc),
            )
            return

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
                yield text
        finally:
            latency = int((time.monotonic() - t0) * 1000)
            if not prompt_tokens:
                prompt_tokens = len(" ".join(m.get("content", "") for m in input.messages).split()) * 4 // 3
                completion_tokens = len(full_text.split()) * 4 // 3

            await _record(input, request_id, token, key, mapping, prompt_tokens, completion_tokens, latency)


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton for direct use
# ═══════════════════════════════════════════════════════════════════════════════

proxy_runnable = ProxyRunnable()


# ═══════════════════════════════════════════════════════════════════════════════
# Compat entry points
# ═══════════════════════════════════════════════════════════════════════════════

async def run_proxy(*args, **kwargs) -> ProxyOutput:
    return await proxy_runnable.ainvoke(ProxyInput(**kwargs) if not isinstance(kwargs.get("raw_token"), str) else ProxyInput(**kwargs))


async def run_proxy_stream(*args, **kwargs) -> AsyncIterator[str]:
    async for chunk in proxy_runnable.astream(ProxyInput(**kwargs)):
        yield chunk
