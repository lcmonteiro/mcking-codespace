"""
Full OpenAI-compatible API surface for the LLM Proxy.

Endpoints implemented:

- ``GET  /v1/models``             — list models (OpenAI Model object format)
- ``GET  /v1/models/{model}``     — retrieve a single model
- ``POST /v1/chat/completions``   — chat completions (non-streaming + SSE)
- ``POST /v1/completions``        — legacy text completions
- ``POST /v1/embeddings``         — embeddings

All responses match the OpenAI API schema exactly so any OpenAI SDK client
(openai-python, openai-node, LangChain ChatOpenAI with base_url=...) works
without modification.
"""
import json
import logging
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Literal, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.db.models import ModelAbstraction, RequestStatus
from src.db.session import AsyncSessionLocal
from src.middleware.auth import extract_bearer_token
from src.services.model_registry import ModelRegistry
from src.runnables.proxy_graph import run_proxy, run_proxy_stream

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["OpenAI-compatible API"])


# ═══════════════════════════════════════════════════════════════════════════════
# Shared types
# ═══════════════════════════════════════════════════════════════════════════════


class _Usage(BaseModel):
    """Token usage summary for a single request."""
    prompt_tokens     : int
    completion_tokens : int
    total_tokens      : int


# ═══════════════════════════════════════════════════════════════════════════════
# GET /v1/models  &  GET /v1/models/{model}
# ═══════════════════════════════════════════════════════════════════════════════


class ModelObject(BaseModel):
    """An OpenAI-compatible model object."""
    id      : str
    object  : Literal["model"] = "model"
    created : int
    owned_by: str              = "llm-proxy"


class ModelList(BaseModel):
    """A list of model objects."""
    object : Literal["list"] = "list"
    data   : List[ModelObject]


@router.get("/models", response_model=ModelList)
async def list_models(
    raw_token: str = Depends(extract_bearer_token),
) -> ModelList:
    """
    List all virtual model abstractions in OpenAI Model object format.

    The ``id`` field is the abstraction name (e.g. ``coding``, ``chat``).

    Args:
        raw_token: Bearer token for authentication.

    Returns:
        A ModelList containing one ModelObject per registered abstraction.
    """
    async with AsyncSessionLocal() as db:
        registry = ModelRegistry(db)
        abstractions = await registry.list_abstractions()

    data = [
        ModelObject(
            id       = a["abstraction"],
            created  = int(time.time()),
            owned_by = f"proxy/{a['primary_provider']}",
        )
        for a in abstractions
    ]
    return ModelList(data=data)


@router.get("/models/{model_id}", response_model=ModelObject)
async def retrieve_model(
    model_id : str,
    raw_token: str = Depends(extract_bearer_token),
) -> ModelObject:
    """
    Retrieve a single model object by its abstraction id.

    Args:
        model_id: The abstraction name (e.g. ``coding``).
        raw_token: Bearer token for authentication.

    Returns:
        A ModelObject representing the abstraction.

    Raises:
        HTTPException: 404 if the model does not exist.
    """
    async with AsyncSessionLocal() as db:
        registry = ModelRegistry(db)
        abstractions = await registry.list_abstractions()

    match = next(
        (a for a in abstractions if a["abstraction"] == model_id), None
    )
    if not match:
        raise HTTPException(
            status_code = 404,
            detail      = {
                "message": f"The model '{model_id}' does not exist",
                "type"   : "invalid_request_error",
                "code"   : "model_not_found",
            },
        )
    return ModelObject(
        id       = match["abstraction"],
        created  = int(time.time()),
        owned_by = f"proxy/{match['primary_provider']}",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# POST /v1/chat/completions
# ═══════════════════════════════════════════════════════════════════════════════


class ContentPartText(BaseModel):
    """A text content part within a multi-part message."""
    type: Literal["text"]
    text: str


class ContentPartImage(BaseModel):
    """An image URL content part within a multi-part message."""
    type     : Literal["image_url"]
    image_url: Dict[str, str]


class ChatMessageRequest(BaseModel):
    """A single message in the chat completion request."""
    role         : Literal["system", "user", "assistant", "tool"]
    content      : Union[str, List[Union[ContentPartText, ContentPartImage]], None] = None
    name         : Optional[str]            = None
    tool_calls   : Optional[List[Dict[str, Any]]] = None
    tool_call_id : Optional[str]            = None


class FunctionDef(BaseModel):
    """Definition of a function available to the model (tool calling)."""
    name       : str
    description: Optional[str]          = None
    parameters : Optional[Dict[str, Any]] = None


class ToolDef(BaseModel):
    """A tool definition wrapping a function."""
    type     : Literal["function"] = "function"
    function : FunctionDef


class ResponseFormatTyped(BaseModel):
    """Controls the response format (text, JSON object, or JSON schema)."""
    type        : Literal["text", "json_object", "json_schema"] = "text"
    json_schema : Optional[Dict[str, Any]]                      = None


class LogprobContent(BaseModel):
    """Token-level log probability information."""
    token        : str
    logprob      : float
    bytes        : Optional[List[int]]                     = None
    top_logprobs : Optional[List[Dict[str, Any]]]          = None


class ChatCompletionRequest(BaseModel):
    """Request body for ``POST /v1/chat/completions``."""
    model               : str
    messages            : List[ChatMessageRequest]
    temperature         : Optional[float]                     = Field(None, ge=0, le=2)
    top_p               : Optional[float]                     = Field(None, ge=0, le=1)
    n                   : int                                 = Field(1, ge=1, le=4)
    stream              : bool                                = False
    stream_options      : Optional[Dict[str, Any]]            = None
    stop                : Optional[Union[str, List[str]]]     = None
    max_tokens          : Optional[int]                       = None
    max_completion_tokens : Optional[int]                     = None
    presence_penalty    : Optional[float]                     = Field(None, ge=-2, le=2)
    frequency_penalty   : Optional[float]                     = Field(None, ge=-2, le=2)
    logit_bias          : Optional[Dict[str, float]]          = None
    logprobs            : Optional[bool]                      = None
    top_logprobs        : Optional[int]                       = Field(None, ge=0, le=20)
    user                : Optional[str]                       = None
    tools               : Optional[List[ToolDef]]             = None
    tool_choice         : Optional[Union[str, Dict[str, Any]]] = None
    parallel_tool_calls : Optional[bool]                      = None
    response_format     : Optional[ResponseFormatTyped]       = None
    seed                : Optional[int]                       = None
    service_tier        : Optional[str]                       = None


# ── Response types ────────────────────────────────────────────────────────────


class ChatMessageResponse(BaseModel):
    """The assistant message returned in a chat completion response."""
    role       : Literal["assistant"]          = "assistant"
    content    : Optional[str]                 = None
    tool_calls : Optional[List[Dict[str, Any]]] = None
    refusal    : Optional[str]                 = None


class TopLogprob(BaseModel):
    """A single top-K candidate for a token's log probability."""
    token   : str
    logprob : float
    bytes   : Optional[List[int]] = None


class TokenLogprob(BaseModel):
    """Log probability for a single token, including top candidates."""
    token        : str
    logprob      : float
    bytes        : Optional[List[int]] = None
    top_logprobs : List[TopLogprob]    = []


class ChoiceLogprobs(BaseModel):
    """Log probabilities for a completion choice."""
    content : Optional[List[TokenLogprob]] = None
    refusal : Optional[List[TokenLogprob]] = None


class ChatChoice(BaseModel):
    """A single completion choice returned by the model."""
    index        : int
    message      : ChatMessageResponse
    finish_reason : Optional[Literal["stop", "length", "tool_calls", "content_filter", "function_call"]] = "stop"
    logprobs     : Optional[ChoiceLogprobs] = None


class CompletionTokensDetails(BaseModel):
    """Detailed breakdown of completion tokens."""
    reasoning_tokens           : Optional[int] = None
    accepted_prediction_tokens : Optional[int] = None
    rejected_prediction_tokens : Optional[int] = None


class UsageWithDetails(_Usage):
    """Token usage with optional completion token details."""
    completion_tokens_details : Optional[CompletionTokensDetails] = None


class ChatCompletionResponse(BaseModel):
    """The full chat completion response, matching OpenAI's schema."""
    id                 : str
    object             : Literal["chat.completion"] = "chat.completion"
    created            : int
    model              : str
    choices            : List[ChatChoice]
    usage              : UsageWithDetails
    system_fingerprint : Optional[str] = None
    service_tier       : Optional[str] = None


# ── Streaming chunk types ─────────────────────────────────────────────────────


class DeltaMessage(BaseModel):
    """The delta (incremental) content in a streaming chunk."""
    role       : Optional[str]                   = None
    content    : Optional[str]                   = None
    tool_calls : Optional[List[Dict[str, Any]]]  = None
    refusal    : Optional[str]                   = None


class StreamChoice(BaseModel):
    """A streaming chunk's choice with delta content."""
    index        : int
    delta        : DeltaMessage
    finish_reason : Optional[str]             = None
    logprobs     : Optional[ChoiceLogprobs]    = None


class ChatCompletionChunk(BaseModel):
    """A streaming chunk matching OpenAI's chat completion chunk schema."""
    id                 : str
    object             : Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created            : int
    model              : str
    choices            : List[StreamChoice]
    usage              : Optional[UsageWithDetails]  = None
    system_fingerprint : Optional[str]               = None
    service_tier       : Optional[str]               = None


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.post("/chat/completions")
async def chat_completions(
    body     : ChatCompletionRequest,
    request  : Request,
    raw_token: str = Depends(extract_bearer_token),
) -> Any:
    """
    Create a chat completion.

    Supports both non-streaming and SSE streaming responses.  When
    ``body.stream`` is ``True``, returns a ``text/event-stream`` response.

    Args:
        body: Chat completion request body.
        request: FastAPI request object (used for client IP extraction).
        raw_token: Bearer token for authentication.

    Returns:
        A ``ChatCompletionResponse`` for non-streaming, or a ``StreamingResponse``
        for streaming.
    """
    abstraction = _parse_abstraction(body.model)
    override    = _build_override(body)
    messages    = [_normalise_message(m) for m in body.messages]
    ip          = _client_ip(request)

    if body.stream:
        return StreamingResponse(
            _stream_chat(raw_token, abstraction, messages, override, ip, body),
            media_type = "text/event-stream",
            headers    = {
                "Cache-Control"    : "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    result = await run_proxy(
        raw_token       = raw_token,
        abstraction     = abstraction,
        messages        = messages,
        override_params = override,
        ip_address      = ip,
    )
    _raise_if_error(result)

    model_name = result.model_provider or ""
    model_id   = (
        f"{result.model_provider}/{result.model_name}"
        if result.model_provider else body.model
    )

    return ChatCompletionResponse(
        id      = f"chatcmpl-{result.request_id}",
        created = int(time.time()),
        model   = model_id,
        choices = [
            ChatChoice(
                index        = 0,
                message      = ChatMessageResponse(content=result.response_text),
                finish_reason = "stop",
            )
        ],
        usage = UsageWithDetails(
            prompt_tokens     = result.prompt_tokens,
            completion_tokens = result.completion_tokens,
            total_tokens      = result.total_tokens,
        ),
        system_fingerprint = f"fp_{result.request_id[:8]}",
    )


async def _stream_chat(
    raw_token   : str,
    abstraction : ModelAbstraction,
    messages    : List[Dict[str, str]],
    override    : Dict[str, Any],
    ip          : Optional[str],
    body        : ChatCompletionRequest,
) -> AsyncIterator[str]:
    """
    Yield SSE data lines for streaming chat completions.

    Args:
        raw_token: Bearer token for authentication.
        abstraction: The requested model abstraction.
        messages: Normalised message list.
        override: Override parameters for the model call.
        ip: Client IP address.
        body: Original request (for stream_options).

    Yields:
        ``data: ...`` SSE lines, ending with ``data: [DONE]``.
    """
    from src.runnables.proxy_graph import (
        ChunkType,
        ProxyInput,
        proxy_runnable,
        StreamChunk,
    )

    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created       = int(time.time())
    include_usage = (body.stream_options or {}).get("include_usage", False)

    stream = proxy_runnable.astream(ProxyInput(
        raw_token       = raw_token,
        abstraction     = abstraction,
        messages        = messages,
        override_params = override,
        ip_address      = ip,
    ))

    # ── First chunk: setup or error ───────────────────────────────────────────
    first = await anext(stream, None)
    if first is None:
        yield "data: [DONE]\n\n"
        return

    if first.type == ChunkType.ERROR:
        yield _sse_error(first.error_message or "Unknown error")
        yield "data: [DONE]\n\n"
        return

    model_id = (
        f"{first.model_provider}/{first.model_name}"
        if first.model_provider else body.model
    )

    # ── Role chunk ────────────────────────────────────────────────────────────
    yield _sse(ChatCompletionChunk(
        id      = completion_id,
        created = created,
        model   = model_id,
        choices = [
            StreamChoice(
                index        = 0,
                delta        = DeltaMessage(role="assistant"),
                finish_reason = None,
            )
        ],
    ))

    prompt_tokens     = 0
    completion_tokens = 0

    async for chunk in stream:
        if chunk.type == ChunkType.CONTENT:
            yield _sse(ChatCompletionChunk(
                id      = completion_id,
                created = created,
                model   = model_id,
                choices = [
                    StreamChoice(
                        index        = 0,
                        delta        = DeltaMessage(content=chunk.text),
                        finish_reason = None,
                    )
                ],
            ))
        elif chunk.type == ChunkType.ERROR:
            yield _sse_error(chunk.error_message or "Unexpected error")
            yield "data: [DONE]\n\n"
            return
        elif chunk.type == ChunkType.DONE:
            prompt_tokens     = chunk.prompt_tokens
            completion_tokens = chunk.completion_tokens

    # ── Finish chunk ──────────────────────────────────────────────────────────
    finish_chunk = ChatCompletionChunk(
        id      = completion_id,
        created = created,
        model   = model_id,
        choices = [
            StreamChoice(
                index        = 0,
                delta        = DeltaMessage(),
                finish_reason = "stop",
            )
        ],
    )
    if include_usage:
        finish_chunk.usage = UsageWithDetails(
            prompt_tokens     = prompt_tokens,
            completion_tokens = completion_tokens,
            total_tokens      = prompt_tokens + completion_tokens,
        )
    yield _sse(finish_chunk)
    yield "data: [DONE]\n\n"


# ═══════════════════════════════════════════════════════════════════════════════
# POST /v1/completions  (legacy text completions)
# ═══════════════════════════════════════════════════════════════════════════════


class CompletionRequest(BaseModel):
    """Request body for ``POST /v1/completions`` (legacy text completions)."""
    model             : str
    prompt            : Union[str, List[str], List[int], List[List[int]]]
    suffix            : Optional[str]                     = None
    max_tokens        : int                               = 16
    temperature       : Optional[float]                   = Field(None, ge=0, le=2)
    top_p             : Optional[float]                   = Field(None, ge=0, le=1)
    n                 : int                               = 1
    stream            : bool                              = False
    logprobs          : Optional[int]                     = None
    echo              : bool                              = False
    stop              : Optional[Union[str, List[str]]]   = None
    presence_penalty  : Optional[float]                   = Field(None, ge=-2, le=2)
    frequency_penalty : Optional[float]                   = Field(None, ge=-2, le=2)
    best_of           : int                               = 1
    user              : Optional[str]                     = None
    seed              : Optional[int]                     = None


class CompletionChoice(BaseModel):
    """A single choice in a legacy text completion response."""
    text          : str
    index         : int
    logprobs      : None = None
    finish_reason : str  = "stop"


class CompletionResponse(BaseModel):
    """Full legacy text completion response matching OpenAI's schema."""
    id      : str
    object  : Literal["text_completion"] = "text_completion"
    created : int
    model   : str
    choices : List[CompletionChoice]
    usage   : _Usage


@router.post("/completions", response_model=CompletionResponse)
async def text_completions(
    body     : CompletionRequest,
    request  : Request,
    raw_token: str = Depends(extract_bearer_token),
) -> CompletionResponse:
    """
    Legacy text completions — wraps the prompt as a user message internally.

    Args:
        body: Completion request body.
        request: FastAPI request object.
        raw_token: Bearer token for authentication.

    Returns:
        A CompletionResponse matching the OpenAI format.
    """
    abstraction = _parse_abstraction(body.model)

    prompt_text = (
        body.prompt if isinstance(body.prompt, str) else str(body.prompt)
    )
    messages = [{"role": "user", "content": prompt_text}]

    override: Dict[str, Any] = {}
    if body.temperature is not None:
        override["temperature"] = body.temperature
    if body.max_tokens:
        override["max_tokens"] = body.max_tokens

    result = await run_proxy(
        raw_token       = raw_token,
        abstraction     = abstraction,
        messages        = messages,
        override_params = override,
        ip_address      = _client_ip(request),
    )
    _raise_if_error(result)

    model_id = (
        f"{result.model_provider}/{result.model_name}"
        if result.model_provider else body.model
    )
    text = result.response_text or ""
    if body.echo:
        text = prompt_text + text

    return CompletionResponse(
        id      = f"cmpl-{result.request_id}",
        created = int(time.time()),
        model   = model_id,
        choices = [CompletionChoice(text=text, index=0)],
        usage   = _Usage(
            prompt_tokens     = result.prompt_tokens,
            completion_tokens = result.completion_tokens,
            total_tokens      = result.total_tokens,
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# POST /v1/embeddings
# ═══════════════════════════════════════════════════════════════════════════════


class EmbeddingRequest(BaseModel):
    """Request body for ``POST /v1/embeddings``."""
    model           : str
    input           : Union[str, List[str], List[int], List[List[int]]]
    encoding_format : Literal["float", "base64"] = "float"
    dimensions      : Optional[int]              = None
    user            : Optional[str]              = None


class EmbeddingObject(BaseModel):
    """A single embedding vector."""
    object    : Literal["embedding"] = "embedding"
    embedding : List[float]
    index     : int


class EmbeddingResponse(BaseModel):
    """Full embedding response matching OpenAI's schema."""
    object : Literal["list"] = "list"
    data   : List[EmbeddingObject]
    model  : str
    usage  : _Usage


@router.post("/embeddings", response_model=EmbeddingResponse)
async def create_embeddings(
    body     : EmbeddingRequest,
    raw_token: str = Depends(extract_bearer_token),
) -> EmbeddingResponse:
    """
    Creates embeddings via the ``embedding`` model abstraction.

    The backing model must be an embedding model (e.g. ``text-embedding-3-small``).

    Args:
        body: Embedding request body.
        raw_token: Bearer token for authentication.

    Returns:
        An EmbeddingResponse matching the OpenAI format.
    """
    from src.db.session import AsyncSessionLocal
    from src.services.budget import BudgetError, BudgetService
    from src.services.model_registry import ModelRegistry

    abstraction = ModelAbstraction.EMBEDDING

    async with AsyncSessionLocal() as db:
        budget_svc = BudgetService(db)
        try:
            token = await budget_svc.authenticate(raw_token, abstraction)
        except BudgetError as exc:
            raise HTTPException(
                status_code = 403,
                detail      = _openai_error(str(exc), "invalid_request_error"),
            )

        registry = ModelRegistry(db)
        try:
            model, mapping, key = await registry.resolve(abstraction)
        except ValueError as exc:
            raise HTTPException(
                status_code = 400,
                detail      = _openai_error(str(exc), "invalid_request_error"),
            )

        inputs = (
            [body.input] if isinstance(body.input, str) else body.input
        )
        # For token list inputs, we skip embedding and raise a clear error
        if inputs and not isinstance(inputs[0], str):
            raise HTTPException(
                status_code = 400,
                detail      = _openai_error(
                    "Token-list inputs are not yet supported by this proxy.",
                    "invalid_request_error",
                ),
            )

        import time as _time
        t0 = _time.monotonic()
        try:
            from langchain_openai import OpenAIEmbeddings
            embed_model = OpenAIEmbeddings(
                model          = mapping.model_name,
                openai_api_key = key.api_key,
                **({"dimensions": body.dimensions} if body.dimensions else {}),
            )
            vectors = await embed_model.aembed_documents(inputs)
            latency = int((_time.monotonic() - t0) * 1000)
        except Exception as exc:
            raise HTTPException(
                status_code = 502,
                detail      = _openai_error(str(exc), "server_error"),
            )

        # Approximate token count (4 chars approximately 1 token)
        total_chars   = sum(len(s) for s in inputs)
        approx_tokens = total_chars // 4

        await budget_svc.deduct(
            token            = token,
            prompt_tokens    = approx_tokens,
            completion_tokens = 0,
            provider_key_id  = key.id,
            abstraction      = abstraction.value,
            provider         = mapping.provider,
            model_name       = mapping.model_name,
            latency_ms       = latency,
            status           = RequestStatus.SUCCESS,
        )
        await db.commit()

    return EmbeddingResponse(
        data  = [
            EmbeddingObject(embedding=vec, index=i)
            for i, vec in enumerate(vectors)
        ],
        model = f"{mapping.provider}/{mapping.model_name}",
        usage = _Usage(
            prompt_tokens     = approx_tokens,
            completion_tokens = 0,
            total_tokens      = approx_tokens,
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_abstraction(model_str: str) -> ModelAbstraction:
    """
    Parse a model string into a ModelAbstraction enum.

    Args:
        model_str: The model abstraction name.

    Returns:
        The corresponding ModelAbstraction value.

    Raises:
        HTTPException: 400 if the abstraction is not recognised.
    """
    try:
        return ModelAbstraction(model_str.lower())
    except ValueError:
        valid = [e.value for e in ModelAbstraction]
        raise HTTPException(
            status_code = 400,
            detail      = _openai_error(
                f"The model '{model_str}' does not exist or you do not have "
                f"access to it. Available abstractions: {valid}",
                "invalid_request_error",
                "model_not_found",
            ),
        )


def _build_override(body: ChatCompletionRequest) -> Dict[str, Any]:
    """
    Extract override parameters from a chat completion request.

    Args:
        body: The chat completion request body.

    Returns:
        A dictionary of parameters to override on the model call.
    """
    o: Dict[str, Any] = {}
    if body.temperature          is not None:
        o["temperature"]         = body.temperature
    if body.top_p                is not None:
        o["top_p"]               = body.top_p
    if body.max_tokens           is not None:
        o["max_tokens"]          = body.max_tokens
    if body.max_completion_tokens is not None:
        o["max_tokens"]          = body.max_completion_tokens
    if body.presence_penalty     is not None:
        o["presence_penalty"]    = body.presence_penalty
    if body.frequency_penalty    is not None:
        o["frequency_penalty"]   = body.frequency_penalty
    if body.stop                 is not None:
        o["stop"]                = body.stop
    if body.seed                 is not None:
        o["seed"]                = body.seed
    if body.tools:
        o["tools"]               = [t.model_dump() for t in body.tools]
    if body.tool_choice          is not None:
        o["tool_choice"]         = body.tool_choice
    if body.response_format      is not None:
        o["response_format"]     = body.response_format.model_dump()
    return o


def _normalise_message(m: ChatMessageRequest) -> Dict[str, Any]:
    """
    Convert a Pydantic ``ChatMessageRequest`` to a plain dict.

    Preserves multipart content (lists of content parts).

    Args:
        m: The chat message to normalise.

    Returns:
        A plain dictionary representation.
    """
    d: Dict[str, Any] = {"role": m.role}
    if isinstance(m.content, list):
        d["content"] = [part.model_dump() for part in m.content]
    else:
        d["content"] = m.content or ""
    if m.name:
        d["name"]         = m.name
    if m.tool_calls:
        d["tool_calls"]   = m.tool_calls
    if m.tool_call_id:
        d["tool_call_id"] = m.tool_call_id
    return d


def _raise_if_error(result: Any) -> None:
    """
    Raise an HTTPException if the proxy result indicates an error.

    Args:
        result: The proxy output to check.

    Raises:
        HTTPException: 403 for blocked requests, 502 for upstream errors.
    """
    if result.status == RequestStatus.BLOCKED:
        raise HTTPException(
            status_code = 403,
            detail      = _openai_error(
                result.error_message or "Blocked",
                "invalid_request_error",
            ),
        )
    if result.status == RequestStatus.ERROR:
        raise HTTPException(
            status_code = 502,
            detail      = _openai_error(
                result.error_message or "Upstream LLM error",
                "server_error",
            ),
        )


def _openai_error(
    message   : str,
    error_type: str,
    code      : Optional[str] = None,
) -> Dict[str, Any]:
    """
    Format an error response exactly as OpenAI does.

    Args:
        message: Human-readable error message.
        error_type: Machine-readable error type.
        code: Optional error code (e.g. ``model_not_found``).

    Returns:
        An OpenAI-compatible error dictionary.
    """
    err: Dict[str, Any] = {
        "message": message,
        "type"   : error_type,
        "param"  : None,
        "code"   : code,
    }
    return {"error": err}


def _sse(chunk: ChatCompletionChunk) -> str:
    """
    Serialise a ``ChatCompletionChunk`` to an SSE ``data:`` line.

    Args:
        chunk: The streaming chunk to serialise.

    Returns:
        An SSE-formatted string.
    """
    return f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"


def _sse_error(message: str) -> str:
    """
    Serialise an error message to an SSE ``data:`` line.

    Args:
        message: The error message.

    Returns:
        An SSE-formatted error string.
    """
    payload = json.dumps({"error": {"message": message, "type": "server_error"}})
    return f"data: {payload}\n\n"


def _client_ip(request: Request) -> Optional[str]:
    """
    Extract the client IP address from a request.

    Respects the ``X-Forwarded-For`` header when behind a reverse proxy.

    Args:
        request: The FastAPI request object.

    Returns:
        The client IP address string, or None.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return getattr(request.client, "host", None)
