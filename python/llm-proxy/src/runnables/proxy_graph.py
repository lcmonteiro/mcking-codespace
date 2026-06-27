"""
Proxy Pipeline — end-to-end LLM Proxy as a pure LangChain Runnable.

Streaming::

    async for chunk in proxy_runnable.astream(ProxyInput(...)):
        if chunk.type == "content":
            print(chunk.text)
        elif chunk.type == "done":
            print(f"Usage: {chunk.prompt_tokens} in / {chunk.completion_tokens} out")
        elif chunk.type == "error":
            print(f"Error: {chunk.error}")
"""
import logging
import time
import uuid
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.runnables import Runnable, RunnableConfig
from pydantic import BaseModel

from src.db.models import ModelAbstraction, RequestStatus
from src.runnables.budget_auth import BudgetAuthInput, BudgetAuthRunnable
from src.runnables.budget_deduct import BudgetDeductInput, BudgetDeductRunnable
from src.runnables.model_resolve import ModelResolveInput, ModelResolveRunnable
from src.services.budget import BudgetError

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# I/O Schemas
# ═══════════════════════════════════════════════════════════════════════════════


class ProxyInput(BaseModel):
    """Input to the proxy pipeline."""
    raw_token       : str
    abstraction     : ModelAbstraction
    messages        : List[Dict[str, str]]
    override_params : Dict[str, Any] = {}
    ip_address      : Optional[str]  = None


class ProxyOutput(BaseModel):
    """Output from the proxy pipeline after a non-streaming invocation."""
    request_id       : str               = ""
    response_text    : Optional[str]     = None
    prompt_tokens    : int               = 0
    completion_tokens: int               = 0
    total_tokens     : int               = 0
    latency_ms       : int               = 0
    status           : RequestStatus     = RequestStatus.SUCCESS
    error_message    : Optional[str]     = None
    model_provider   : Optional[str]     = None
    model_name       : Optional[str]     = None


class ChunkType(str, Enum):
    """Types of chunks yielded during streaming."""
    SETUP   = "setup"
    CONTENT = "content"
    DONE    = "done"
    ERROR   = "error"


class StreamChunk(BaseModel):
    """Chunk yielded by ``ProxyRunnable.astream()``."""
    type             : ChunkType      = ChunkType.CONTENT
    text             : str            = ""
    model_provider   : Optional[str]  = None
    model_name       : Optional[str]  = None
    prompt_tokens    : int            = 0
    completion_tokens: int            = 0
    total_tokens     : int            = 0
    request_id       : Optional[str]  = None
    error_message    : Optional[str]  = None


# ═══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _prepare_messages(messages: List[Dict[str, str]]) -> List[BaseMessage]:
    """
    Convert plain-dict messages to LangChain ``BaseMessage`` objects.

    Args:
        messages: List of message dicts (``role``, ``content`` keys).

    Returns:
        A list of LangChain message objects.
    """
    lc: List[BaseMessage] = []
    for msg in messages:
        role    = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                p.get("text", "") for p in content if isinstance(p, dict)
            )
        if role == "system":
            lc.append(SystemMessage(content=content))
        elif role == "assistant":
            lc.append(AIMessage(content=content))
        else:
            lc.append(HumanMessage(content=content))
    return lc


async def _setup(input: ProxyInput) -> tuple:
    """
    Run authentication and model resolution for a proxy request.

    Args:
        input: The proxy pipeline input.

    Returns:
        A tuple ``(request_id, token, model, mapping, key, lc_messages)``.

    Raises:
        BudgetError: If authentication fails.
        ValueError: If model resolution fails.
    """
    request_id = str(uuid.uuid4())
    auth = BudgetAuthRunnable()
    auth_result = await auth.ainvoke(BudgetAuthInput(
        raw_token   = input.raw_token,
        abstraction = input.abstraction,
    ))
    if not auth_result.success:
        raise BudgetError(
            auth_result.error_message or "Authentication failed",
            auth_result.status,
        )

    resolver = ModelResolveRunnable()
    resolve_result = await resolver.ainvoke(ModelResolveInput(
        abstraction     = input.abstraction,
        override_params = input.override_params,
    ))
    if not resolve_result.success:
        raise ValueError(
            resolve_result.error_message or "Model resolution failed"
        )

    return (
        request_id,
        auth_result.access_token,
        resolve_result.model,
        resolve_result.mapping,
        resolve_result.provider_key,
        _prepare_messages(input.messages),
    )


async def _record(
    input           : ProxyInput,
    request_id      : str,
    token           : Any,
    key             : Any,
    mapping         : Any,
    prompt_tokens   : int,
    completion_tokens: int,
    latency_ms      : int,
    status          : RequestStatus    = RequestStatus.SUCCESS,
    error_message   : Optional[str]    = None,
) -> None:
    """
    Persist a usage record for the proxy request.

    Args:
        input: Original proxy input (for abstraction, provider, IP).
        request_id: Unique request identifier.
        token: The authenticated access token.
        key: The provider key used.
        mapping: The model mapping used.
        prompt_tokens: Number of prompt tokens.
        completion_tokens: Number of completion tokens.
        latency_ms: Request latency in milliseconds.
        status: Request outcome status.
        error_message: Optional error description.
    """
    deduct = BudgetDeductRunnable()
    await deduct.ainvoke(BudgetDeductInput(
        token             = token,
        prompt_tokens     = prompt_tokens,
        completion_tokens = completion_tokens,
        provider_key_id   = key.id,
        abstraction       = input.abstraction.value,
        provider          = mapping.provider,
        model_name        = mapping.model_name,
        latency_ms        = latency_ms,
        request_id        = request_id,
        ip_address        = input.ip_address,
        error_message     = error_message,
        status            = status,
    ))


# ═══════════════════════════════════════════════════════════════════════════════
# ProxyRunnable
# ═══════════════════════════════════════════════════════════════════════════════


class ProxyRunnable(Runnable[ProxyInput, ProxyOutput]):
    """End-to-end proxy pipeline as a LangChain Runnable."""

    def invoke(
        self,
        input : ProxyInput,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> ProxyOutput:
        """
        Synchronous invoke is not supported — use ``ainvoke()`` instead.

        Raises:
            NotImplementedError: Always, because this proxy is async-only.
        """
        raise NotImplementedError(
            "ProxyRunnable is async-only; use await proxy_runnable.ainvoke(...)"
        )

    async def ainvoke(
        self,
        input : ProxyInput,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> ProxyOutput:
        try:
            request_id, token, model, mapping, key, lc = await _setup(input)
        except BudgetError as exc:
            return ProxyOutput(
                request_id    = str(uuid.uuid4()),
                status        = exc.status,
                error_message = str(exc),
            )
        except ValueError as exc:
            return ProxyOutput(
                request_id    = str(uuid.uuid4()),
                status        = RequestStatus.ERROR,
                error_message = str(exc),
            )

        t0 = time.monotonic()
        try:
            response = await model.ainvoke(lc)
            latency  = int((time.monotonic() - t0) * 1000)
            usage    = getattr(response, "usage_metadata", None) or {}
            prompt_t = usage.get("input_tokens", 0)
            comp_t   = usage.get("output_tokens", 0)
            await _record(
                input, request_id, token, key, mapping,
                prompt_t, comp_t, latency,
            )
            return ProxyOutput(
                request_id        = request_id,
                response_text     = response.content,
                prompt_tokens     = prompt_t,
                completion_tokens = comp_t,
                total_tokens      = prompt_t + comp_t,
                latency_ms        = latency,
                status            = RequestStatus.SUCCESS,
                model_provider    = mapping.provider,
                model_name        = mapping.model_name,
            )
        except Exception as exc:
            latency  = int((time.monotonic() - t0) * 1000)
            prompt_t = (
                len(" ".join(
                    m.get("content", "") for m in input.messages
                ).split()) * 4 // 3
            )
            await _record(
                input, request_id, token, key, mapping,
                prompt_t, 0, latency,
                status        = RequestStatus.ERROR,
                error_message = str(exc),
            )
            return ProxyOutput(
                request_id    = request_id,
                status        = RequestStatus.ERROR,
                error_message = str(exc),
                latency_ms    = latency,
            )

    async def astream(
        self,
        input : ProxyInput,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream tokens with rich metadata.

        Yields:
            StreamChunk(type="setup"): Model info before streaming starts.
            StreamChunk(type="content"): Individual token chunks.
            StreamChunk(type="done"): Final chunk with usage.
            StreamChunk(type="error"): On failure.
        """
        try:
            request_id, token, model, mapping, key, lc = await _setup(input)
        except BudgetError as exc:
            yield StreamChunk(type=ChunkType.ERROR, error_message=str(exc))
            return
        except ValueError as exc:
            yield StreamChunk(type=ChunkType.ERROR, error_message=str(exc))
            return

        # ── Setup: model info ─────────────────────────────────────────────────
        yield StreamChunk(
            type            = ChunkType.SETUP,
            model_provider  = mapping.provider,
            model_name      = mapping.model_name,
            request_id      = request_id,
        )

        t0      = time.monotonic()
        full_text         = ""
        prompt_tokens     = 0
        completion_tokens = 0
        recorded          = False

        try:
            async for chunk in model.astream(lc):
                text = chunk.content or ""
                full_text += text
                usage = getattr(chunk, "usage_metadata", None) or {}
                if usage.get("input_tokens"):
                    prompt_tokens     = usage["input_tokens"]
                    completion_tokens = usage.get("output_tokens", 0)
                yield StreamChunk(type=ChunkType.CONTENT, text=text)
        except Exception as exc:
            latency = int((time.monotonic() - t0) * 1000)
            await _record(
                input, request_id, token, key, mapping,
                prompt_tokens or len(full_text.split()) * 4 // 3,
                completion_tokens or 0,
                latency,
                status        = RequestStatus.ERROR,
                error_message = str(exc),
            )
            recorded = True
            yield StreamChunk(type=ChunkType.ERROR, error_message=str(exc))
            return
        finally:
            if not recorded and full_text:
                latency = int((time.monotonic() - t0) * 1000)
                if not prompt_tokens:
                    prompt_tokens     = (
                        len(" ".join(
                            m.get("content", "") for m in input.messages
                        ).split()) * 4 // 3
                    )
                    completion_tokens = len(full_text.split()) * 4 // 3
                await _record(
                    input, request_id, token, key, mapping,
                    prompt_tokens, completion_tokens, latency,
                )

        # ── Done ──────────────────────────────────────────────────────────────
        yield StreamChunk(
            type              = ChunkType.DONE,
            prompt_tokens     = prompt_tokens,
            completion_tokens = completion_tokens,
            total_tokens      = prompt_tokens + completion_tokens,
            request_id        = request_id,
            model_provider    = mapping.provider,
            model_name        = mapping.model_name,
        )


# Singleton
proxy_runnable = ProxyRunnable()


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience entry points
# ═══════════════════════════════════════════════════════════════════════════════


async def run_proxy(*args: Any, **kwargs: Any) -> ProxyOutput:
    """Convenience wrapper around ``ProxyRunnable.ainvoke()``."""
    return await proxy_runnable.ainvoke(ProxyInput(**kwargs))


async def run_proxy_stream(*args: Any, **kwargs: Any) -> AsyncIterator[StreamChunk]:
    """Convenience wrapper around ``ProxyRunnable.astream()``."""
    async for chunk in proxy_runnable.astream(ProxyInput(**kwargs)):
        yield chunk
