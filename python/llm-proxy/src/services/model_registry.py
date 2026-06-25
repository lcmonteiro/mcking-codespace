"""
Model Registry — resolves virtual model abstractions to LangChain ChatModel instances.

Flow:
  1. Look up ModelMappings for the requested abstraction (sorted by priority desc).
  2. For the winning provider, fetch an active ProviderKey (rotation strategy applied).
  3. Instantiate the appropriate LangChain ChatModel with the resolved key.
  4. Return the model + metadata for downstream use.

LangChain Runnables exposed:
  - ModelResolveRunnable  : resolve abstraction → (ChatModel, mapping, key)
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ModelAbstraction, ModelMapping, ProviderKey
from src.db.session import AsyncSessionLocal
from config.settings import settings


# ── Provider → LangChain class mapping ────────────────────────────────────────

_PROVIDER_CLASSES: Dict[str, type] = {
    "openai":    ChatOpenAI,
    "anthropic": ChatAnthropic,
}


# ── Key rotation state (in-memory round-robin cursors) ────────────────────────

class _RoundRobinPool:
    """Thread-safe(-ish) round-robin index over a list."""
    def __init__(self) -> None:
        self._cursors: Dict[str, int] = {}

    def next_index(self, pool_id: str, pool_size: int) -> int:
        idx = self._cursors.get(pool_id, 0) % pool_size
        self._cursors[pool_id] = idx + 1
        return idx


_rr_pool = _RoundRobinPool()


# ─── Pydantic schemas for Runnable I/O ────────────────────────────────────────

class ModelResolveInput(BaseModel):
    """Input schema for ModelResolveRunnable."""
    abstraction:     ModelAbstraction
    override_params: Dict[str, Any] = {}


class ModelResolveOutput(BaseModel):
    """Output schema for ModelResolveRunnable."""
    success:      bool = False
    model:        Optional[Any] = None
    mapping:      Optional[Any] = None
    provider_key: Optional[Any] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


# ─── Runnable: ModelResolveRunnable ───────────────────────────────────────────

class ModelResolveRunnable(Runnable[ModelResolveInput, ModelResolveOutput]):
    """
    LangChain Runnable that resolves a model abstraction to a concrete
    LangChain ChatModel instance with provider key rotation.

    Usage:
        result = await runnable.ainvoke(ModelResolveInput(abstraction=ModelAbstraction.CODING))
        if result.success:
            chat_model = result.model
    """

    async def ainvoke(
        self,
        input: ModelResolveInput,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> ModelResolveOutput:
        async with AsyncSessionLocal() as db:
            # 1. Get the best mapping
            result = await db.execute(
                select(ModelMapping)
                .where(
                    ModelMapping.abstraction == input.abstraction,
                    ModelMapping.is_active == True,
                )
                .order_by(ModelMapping.priority.desc())
            )
            mapping: Optional[ModelMapping] = result.scalars().first()
            if not mapping:
                return ModelResolveOutput(
                    success=False,
                    error_message=(
                        f"No active model mapping found for abstraction '{input.abstraction.value}'. "
                        "Configure one via POST /admin/model-mappings."
                    ),
                )

            # 2. Pick a provider key (rotation)
            key_result = await db.execute(
                select(ProviderKey)
                .where(ProviderKey.provider == mapping.provider, ProviderKey.is_active == True)
                .order_by(ProviderKey.priority.desc())
            )
            keys: List[ProviderKey] = key_result.scalars().all()
            if not keys:
                return ModelResolveOutput(
                    success=False,
                    error_message=(
                        f"No active API key registered for provider '{mapping.provider}'. "
                        "Add one via POST /admin/provider-keys."
                    ),
                )

            strategy = settings.KEY_ROTATION_STRATEGY
            if strategy == "round_robin":
                idx = _rr_pool.next_index(mapping.provider, len(keys))
                key = keys[idx]
            elif strategy == "random":
                key = random.choice(keys)
            else:
                key = keys[0]

            # 3. Instantiate the ChatModel
            cls = _PROVIDER_CLASSES.get(mapping.provider)
            if cls is None:
                return ModelResolveOutput(
                    success=False,
                    error_message=f"Unsupported provider: '{mapping.provider}'",
                )

            base_params: Dict[str, Any] = {
                "model": mapping.model_name,
                **(mapping.extra_params or {}),
            }
            if mapping.max_tokens is not None:
                base_params["max_tokens"] = mapping.max_tokens
            if mapping.temperature is not None:
                base_params["temperature"] = mapping.temperature
            base_params.update(input.override_params)

            key_param = _api_key_param(mapping.provider)
            base_params[key_param] = key.api_key

            try:
                model = cls(**base_params)
                return ModelResolveOutput(
                    success=True,
                    model=model,
                    mapping=mapping,
                    provider_key=key,
                )
            except Exception as exc:
                return ModelResolveOutput(
                    success=False,
                    error_message=f"Failed to instantiate model: {exc}",
                )


# ── Internal ModelRegistry (kept for admin/list compatibility) ────────────────

class ModelRegistry:
    """
    Internal implementation. Prefer using ModelResolveRunnable when composing
    LangChain pipelines.
    """
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def resolve(
        self,
        abstraction: ModelAbstraction,
        override_params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[BaseChatModel, ModelMapping, ProviderKey]:
        runnable = ModelResolveRunnable()
        result = await runnable.ainvoke(ModelResolveInput(
            abstraction=abstraction,
            override_params=override_params or {},
        ))
        if not result.success:
            raise ValueError(result.error_message or "Model resolution failed")
        return result.model, result.mapping, result.provider_key

    async def list_abstractions(self) -> List[Dict[str, Any]]:
        result = await self._db.execute(
            select(ModelMapping)
            .where(ModelMapping.is_active == True)
            .order_by(ModelMapping.abstraction, ModelMapping.priority.desc())
        )
        rows = result.scalars().all()
        seen: Dict[str, Dict] = {}
        for r in rows:
            key = r.abstraction.value
            if key not in seen:
                seen[key] = {
                    "abstraction": key,
                    "primary_provider": r.provider,
                    "primary_model": r.model_name,
                    "fallbacks": [],
                }
            else:
                seen[key]["fallbacks"].append(f"{r.provider}/{r.model_name}")
        return list(seen.values())


# ── Private helpers ───────────────────────────────────────────────────────────

def _api_key_param(provider: str) -> str:
    return {
        "openai":    "openai_api_key",
        "anthropic": "anthropic_api_key",
        "google":    "google_api_key",
    }.get(provider, "api_key")
