"""
Full OpenAI-compatible API surface.

Endpoints implemented:
  GET  /v1/models                  — list models (OpenAI Model object format)
  GET  /v1/models/{model}          — retrieve a single model
  POST /v1/chat/completions        — chat completions (non-streaming + SSE streaming)
  POST /v1/completions             — legacy text completions
  POST /v1/embeddings              — embeddings

All responses match the OpenAI API schema exactly so any OpenAI SDK client
(openai-python, openai-node, LangChain ChatOpenAI with base_url=...) works
without modification.
"""
from __future__ import annotations

import json
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

router = APIRouter(prefix="/v1", tags=["OpenAI-compatible API"])


# ══════════════════════════════════════════════════════════════════════════════
# Shared types
# ══════════════════════════════════════════════════════════════════════════════

class _Usage(BaseModel):
    prompt_tokens:     int
    completion_tokens: int
    total_tokens:      int


# ══════════════════════════════════════════════════════════════════════════════
# GET /v1/models  &  GET /v1/models/{model}
# ══════════════════════════════════════════════════════════════════════════════

class ModelObject(BaseModel):
    id:       str
    object:   Literal["model"] = "model"
    created:  int
    owned_by: str = "llm-proxy"


class ModelList(BaseModel):
    object: Literal["list"] = "list"
    data:   List[ModelObject]


@router.get("/models", response_model=ModelList)
async def list_models(raw_token: str = Depends(extract_bearer_token)):
    """
    Lists all virtual model abstractions in OpenAI Model object format.
    The `id` field is the abstraction name (e.g. 'coding', 'chat').
    """
    async with AsyncSessionLocal() as db:
        registry = ModelRegistry(db)
        abstractions = await registry.list_abstractions()

    data = [
        ModelObject(
            id=a["abstraction"],
            created=int(time.time()),
            owned_by=f"proxy/{a['primary_provider']}",
        )
        for a in abstractions
    ]
    return ModelList(data=data)


@router.get("/models/{model_id}", response_model=ModelObject)
async def retrieve_model(model_id: str, raw_token: str = Depends(extract_bearer_token)):
    """Retrieve a single model object by its abstraction id."""
    async with AsyncSessionLocal() as db:
        registry = ModelRegistry(db)
        abstractions = await registry.list_abstractions()

    match = next((a for a in abstractions if a["abstraction"] == model_id), None)
    if not match:
        raise HTTPException(
            status_code=404,
            detail={"message": f"The model '{model_id}' does not exist", "type": "invalid_request_error", "code": "model_not_found"},
        )
    return ModelObject(
        id=match["abstraction"],
        created=int(time.time()),
        owned_by=f"proxy/{match['primary_provider']}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# POST /v1/chat/completions
# ══════════════════════════════════════════════════════════════════════════════

# ── Request ───────────────────────────────────────────────────────────────────

class ContentPartText(BaseModel):
    type: Literal["text"]
    text: str


class ContentPartImage(BaseModel):
    type: Literal["image_url"]
    image_url: Dict[str, str]


class ChatMessageRequest(BaseModel):
    role:    Literal["system", "user", "assistant", "tool"]
    content: Union[str, List[Union[ContentPartText, ContentPartImage]], None] = None
    name:    Optional[str] = None
    # tool_calls / tool_call_id forwarded as-is
    tool_calls:    Optional[List[Dict[str, Any]]] = None
    tool_call_id:  Optional[str] = None


class FunctionDef(BaseModel):
    name:        str
    description: Optional[str] = None
    parameters:  Optional[Dict[str, Any]] = None


class ToolDef(BaseModel):
    type:     Literal["function"] = "function"
    function: FunctionDef


class ResponseFormatTyped(BaseModel):
    type: Literal["text", "json_object", "json_schema"] = "text"
    json_schema: Optional[Dict[str, Any]] = None


class LogprobContent(BaseModel):
    token:        str
    logprob:      float
    bytes:        Optional[List[int]] = None
    top_logprobs: Optional[List[Dict[str, Any]]] = None


class ChatCompletionRequest(BaseModel):
    model:             str
    messages:          List[ChatMessageRequest]
    temperature:       Optional[float]  = Field(None, ge=0, le=2)
    top_p:             Optional[float]  = Field(None, ge=0, le=1)
    n:                 int              = Field(1, ge=1, le=4)
    stream:            bool             = False
    stream_options:    Optional[Dict[str, Any]] = None
    stop:              Optional[Union[str, List[str]]] = None
    max_tokens:        Optional[int]    = None
    max_completion_tokens: Optional[int] = None
    presence_penalty:  Optional[float]  = Field(None, ge=-2, le=2)
    frequency_penalty: Optional[float]  = Field(None, ge=-2, le=2)
    logit_bias:        Optional[Dict[str, float]] = None
    logprobs:          Optional[bool]   = None
    top_logprobs:      Optional[int]    = Field(None, ge=0, le=20)
    user:              Optional[str]    = None
    tools:             Optional[List[ToolDef]] = None
    tool_choice:       Optional[Union[str, Dict[str, Any]]] = None
    parallel_tool_calls: Optional[bool] = None
    response_format:   Optional[ResponseFormatTyped] = None
    seed:              Optional[int]    = None
    service_tier:      Optional[str]    = None


# ── Response ──────────────────────────────────────────────────────────────────

class ChatMessageResponse(BaseModel):
    role:       Literal["assistant"] = "assistant"
    content:    Optional[str]        = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    refusal:    Optional[str]        = None


class TopLogprob(BaseModel):
    token:   str
    logprob: float
    bytes:   Optional[List[int]] = None


class TokenLogprob(BaseModel):
    token:        str
    logprob:      float
    bytes:        Optional[List[int]] = None
    top_logprobs: List[TopLogprob]    = []


class ChoiceLogprobs(BaseModel):
    content: Optional[List[TokenLogprob]] = None
    refusal: Optional[List[TokenLogprob]] = None


class ChatChoice(BaseModel):
    index:         int
    message:       ChatMessageResponse
    finish_reason: Optional[Literal["stop", "length", "tool_calls", "content_filter", "function_call"]] = "stop"
    logprobs:      Optional[ChoiceLogprobs] = None


class CompletionTokensDetails(BaseModel):
    reasoning_tokens:           Optional[int] = None
    accepted_prediction_tokens: Optional[int] = None
    rejected_prediction_tokens: Optional[int] = None


class UsageWithDetails(_Usage):
    completion_tokens_details: Optional[CompletionTokensDetails] = None


class ChatCompletionResponse(BaseModel):
    id:                str
    object:            Literal["chat.completion"] = "chat.completion"
    created:           int
    model:             str
    choices:           List[ChatChoice]
    usage:             UsageWithDetails
    system_fingerprint: Optional[str] = None
    service_tier:      Optional[str]  = None


# ── Streaming chunk types ─────────────────────────────────────────────────────

class DeltaMessage(BaseModel):
    role:       Optional[str] = None
    content:    Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    refusal:    Optional[str] = None


class StreamChoice(BaseModel):
    index:         int
    delta:         DeltaMessage
    finish_reason: Optional[str]          = None
    logprobs:      Optional[ChoiceLogprobs] = None


class ChatCompletionChunk(BaseModel):
    id:                str
    object:            Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created:           int
    model:             str
    choices:           List[StreamChoice]
    usage:             Optional[UsageWithDetails] = None
    system_fingerprint: Optional[str] = None
    service_tier:       Optional[str] = None


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    request: Request,
    raw_token: str = Depends(extract_bearer_token),
):
    abstraction = _parse_abstraction(body.model)
    override    = _build_override(body)
    messages    = [_normalise_message(m) for m in body.messages]
    ip          = _client_ip(request)

    if body.stream:
        return StreamingResponse(
            _stream_chat(raw_token, abstraction, messages, override, ip, body),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    state = await run_proxy(
        raw_token=raw_token,
        abstraction=abstraction,
        messages=messages,
        override_params=override,
        ip_address=ip,
    )
    _raise_if_error(state)

    mapping = state["mapping"]
    model_id = f"{mapping.provider}/{mapping.model_name}"

    return ChatCompletionResponse(
        id=f"chatcmpl-{state['request_id']}",
        created=int(time.time()),
        model=model_id,
        choices=[
            ChatChoice(
                index=0,
                message=ChatMessageResponse(content=state["response_text"]),
                finish_reason="stop",
            )
        ],
        usage=UsageWithDetails(
            prompt_tokens=state["prompt_tokens"],
            completion_tokens=state["completion_tokens"],
            total_tokens=state["prompt_tokens"] + state["completion_tokens"],
        ),
        system_fingerprint=f"fp_{state['request_id'][:8]}",
    )


async def _stream_chat(
    raw_token:   str,
    abstraction: ModelAbstraction,
    messages:    List[Dict[str, str]],
    override:    Dict[str, Any],
    ip:          Optional[str],
    body:        ChatCompletionRequest,
) -> AsyncIterator[str]:
    """Yield SSE data: lines for streaming chat."""
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created       = int(time.time())
    model_id      = body.model  # will be updated after first token

    include_usage = (body.stream_options or {}).get("include_usage", False)

    # ── role chunk (first) ────────────────────────────────────────────────────
    yield _sse(ChatCompletionChunk(
        id=completion_id, created=created, model=model_id,
        choices=[StreamChoice(index=0, delta=DeltaMessage(role="assistant"), finish_reason=None)],
    ))

    prompt_tokens = 0
    completion_tokens = 0
    full_text = ""

    try:
        async for chunk_text, p_tok, c_tok, mapping in run_proxy_stream(
            raw_token=raw_token,
            abstraction=abstraction,
            messages=messages,
            override_params=override,
            ip_address=ip,
        ):
            if mapping:
                model_id = f"{mapping.provider}/{mapping.model_name}"
            prompt_tokens     = p_tok
            completion_tokens = c_tok
            full_text        += chunk_text

            yield _sse(ChatCompletionChunk(
                id=completion_id, created=created, model=model_id,
                choices=[StreamChoice(index=0, delta=DeltaMessage(content=chunk_text), finish_reason=None)],
            ))

    except Exception as exc:
        # Emit an error chunk then close
        yield _sse_error(str(exc))
        yield "data: [DONE]\n\n"
        return

    # ── finish chunk ──────────────────────────────────────────────────────────
    finish_chunk = ChatCompletionChunk(
        id=completion_id, created=created, model=model_id,
        choices=[StreamChoice(index=0, delta=DeltaMessage(), finish_reason="stop")],
    )
    if include_usage:
        finish_chunk.usage = UsageWithDetails(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
    yield _sse(finish_chunk)
    yield "data: [DONE]\n\n"


# ══════════════════════════════════════════════════════════════════════════════
# POST /v1/completions  (legacy text completions)
# ══════════════════════════════════════════════════════════════════════════════

class CompletionRequest(BaseModel):
    model:             str
    prompt:            Union[str, List[str], List[int], List[List[int]]]
    suffix:            Optional[str]   = None
    max_tokens:        int             = 16
    temperature:       Optional[float] = Field(None, ge=0, le=2)
    top_p:             Optional[float] = Field(None, ge=0, le=1)
    n:                 int             = 1
    stream:            bool            = False
    logprobs:          Optional[int]   = None
    echo:              bool            = False
    stop:              Optional[Union[str, List[str]]] = None
    presence_penalty:  Optional[float] = Field(None, ge=-2, le=2)
    frequency_penalty: Optional[float] = Field(None, ge=-2, le=2)
    best_of:           int             = 1
    user:              Optional[str]   = None
    seed:              Optional[int]   = None


class CompletionChoice(BaseModel):
    text:          str
    index:         int
    logprobs:      None = None
    finish_reason: str  = "stop"


class CompletionResponse(BaseModel):
    id:      str
    object:  Literal["text_completion"] = "text_completion"
    created: int
    model:   str
    choices: List[CompletionChoice]
    usage:   _Usage


@router.post("/completions", response_model=CompletionResponse)
async def text_completions(
    body: CompletionRequest,
    request: Request,
    raw_token: str = Depends(extract_bearer_token),
):
    """Legacy text completions — wraps the prompt as a user message internally."""
    abstraction = _parse_abstraction(body.model)

    prompt_text = body.prompt if isinstance(body.prompt, str) else str(body.prompt)
    messages = [{"role": "user", "content": prompt_text}]

    override: Dict[str, Any] = {}
    if body.temperature is not None:
        override["temperature"] = body.temperature
    if body.max_tokens:
        override["max_tokens"] = body.max_tokens

    state = await run_proxy(
        raw_token=raw_token,
        abstraction=abstraction,
        messages=messages,
        override_params=override,
        ip_address=_client_ip(request),
    )
    _raise_if_error(state)

    mapping  = state["mapping"]
    model_id = f"{mapping.provider}/{mapping.model_name}"
    text     = state["response_text"] or ""
    if body.echo:
        text = prompt_text + text

    return CompletionResponse(
        id=f"cmpl-{state['request_id']}",
        created=int(time.time()),
        model=model_id,
        choices=[CompletionChoice(text=text, index=0)],
        usage=_Usage(
            prompt_tokens=state["prompt_tokens"],
            completion_tokens=state["completion_tokens"],
            total_tokens=state["prompt_tokens"] + state["completion_tokens"],
        ),
    )


# ══════════════════════════════════════════════════════════════════════════════
# POST /v1/embeddings
# ══════════════════════════════════════════════════════════════════════════════

class EmbeddingRequest(BaseModel):
    model:           str
    input:           Union[str, List[str], List[int], List[List[int]]]
    encoding_format: Literal["float", "base64"] = "float"
    dimensions:      Optional[int] = None
    user:            Optional[str] = None


class EmbeddingObject(BaseModel):
    object:    Literal["embedding"] = "embedding"
    embedding: List[float]
    index:     int


class EmbeddingResponse(BaseModel):
    object: Literal["list"] = "list"
    data:   List[EmbeddingObject]
    model:  str
    usage:  _Usage


@router.post("/embeddings", response_model=EmbeddingResponse)
async def create_embeddings(
    body: EmbeddingRequest,
    raw_token: str = Depends(extract_bearer_token),
):
    """
    Creates embeddings via the 'embedding' model abstraction.
    The backing model must be an embedding model (e.g. text-embedding-3-small).
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
            raise HTTPException(status_code=403, detail=_openai_error(str(exc), "invalid_request_error"))

        registry = ModelRegistry(db)
        try:
            model, mapping, key = await registry.resolve(abstraction)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=_openai_error(str(exc), "invalid_request_error"))

        inputs = [body.input] if isinstance(body.input, str) else body.input
        # For token list inputs, we skip embedding and raise a clear error
        if inputs and not isinstance(inputs[0], str):
            raise HTTPException(
                status_code=400,
                detail=_openai_error("Token-list inputs are not yet supported by this proxy.", "invalid_request_error"),
            )

        import time as _time
        t0 = _time.monotonic()
        try:
            from langchain_openai import OpenAIEmbeddings
            embed_model = OpenAIEmbeddings(
                model=mapping.model_name,
                openai_api_key=key.api_key,
                **({"dimensions": body.dimensions} if body.dimensions else {}),
            )
            vectors = await embed_model.aembed_documents(inputs)
            latency = int((_time.monotonic() - t0) * 1000)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=_openai_error(str(exc), "server_error"))

        # Approximate token count (4 chars ≈ 1 token)
        total_chars = sum(len(s) for s in inputs)
        approx_tokens = total_chars // 4

        await budget_svc.deduct(
            token=token,
            prompt_tokens=approx_tokens,
            completion_tokens=0,
            provider_key_id=key.id,
            abstraction=abstraction.value,
            provider=mapping.provider,
            model_name=mapping.model_name,
            latency_ms=latency,
            status=RequestStatus.SUCCESS,
        )
        await db.commit()

    return EmbeddingResponse(
        data=[EmbeddingObject(embedding=vec, index=i) for i, vec in enumerate(vectors)],
        model=f"{mapping.provider}/{mapping.model_name}",
        usage=_Usage(
            prompt_tokens=approx_tokens,
            completion_tokens=0,
            total_tokens=approx_tokens,
        ),
    )


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _parse_abstraction(model_str: str) -> ModelAbstraction:
    try:
        return ModelAbstraction(model_str.lower())
    except ValueError:
        valid = [e.value for e in ModelAbstraction]
        raise HTTPException(
            status_code=400,
            detail=_openai_error(
                f"The model '{model_str}' does not exist or you do not have access to it. "
                f"Available abstractions: {valid}",
                "invalid_request_error",
                "model_not_found",
            ),
        )


def _build_override(body: ChatCompletionRequest) -> Dict[str, Any]:
    o: Dict[str, Any] = {}
    if body.temperature        is not None: o["temperature"]        = body.temperature
    if body.top_p              is not None: o["top_p"]              = body.top_p
    if body.max_tokens         is not None: o["max_tokens"]         = body.max_tokens
    if body.max_completion_tokens is not None: o["max_tokens"]      = body.max_completion_tokens
    if body.presence_penalty   is not None: o["presence_penalty"]   = body.presence_penalty
    if body.frequency_penalty  is not None: o["frequency_penalty"]  = body.frequency_penalty
    if body.stop               is not None: o["stop"]               = body.stop
    if body.seed               is not None: o["seed"]               = body.seed
    if body.tools:
        o["tools"] = [t.model_dump() for t in body.tools]
    if body.tool_choice        is not None: o["tool_choice"]        = body.tool_choice
    if body.response_format    is not None: o["response_format"]    = body.response_format.model_dump()
    return o


def _normalise_message(m: ChatMessageRequest) -> Dict[str, Any]:
    """Convert Pydantic message to a plain dict, preserving multipart content."""
    d: Dict[str, Any] = {"role": m.role}
    if isinstance(m.content, list):
        d["content"] = [part.model_dump() for part in m.content]
    else:
        d["content"] = m.content or ""
    if m.name:            d["name"]          = m.name
    if m.tool_calls:      d["tool_calls"]    = m.tool_calls
    if m.tool_call_id:    d["tool_call_id"]  = m.tool_call_id
    return d


def _raise_if_error(state: dict) -> None:
    if state.get("status") == RequestStatus.BLOCKED:
        raise HTTPException(
            status_code=403,
            detail=_openai_error(state.get("error_message", "Blocked"), "invalid_request_error"),
        )
    if state.get("status") == RequestStatus.ERROR:
        raise HTTPException(
            status_code=502,
            detail=_openai_error(state.get("error_message", "Upstream LLM error"), "server_error"),
        )


def _openai_error(message: str, error_type: str, code: Optional[str] = None) -> Dict[str, Any]:
    """Format an error response exactly as OpenAI does."""
    err: Dict[str, Any] = {"message": message, "type": error_type, "param": None, "code": code}
    return {"error": err}


def _sse(chunk: ChatCompletionChunk) -> str:
    return f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"


def _sse_error(message: str) -> str:
    payload = json.dumps({"error": {"message": message, "type": "server_error"}})
    return f"data: {payload}\n\n"


def _client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return getattr(request.client, "host", None)
