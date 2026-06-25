"""
Model Registry — resolves virtual model abstractions to LangChain ChatModel instances.

Flow:
  1. Look up ModelMappings for the requested abstraction (sorted by priority desc).
  2. For the winning provider, fetch an active ProviderKey (rotation strategy applied).
  3. Instantiate the appropriate LangChain ChatModel with the resolved key.
  4. Return the model + metadata for downstream use.
"""
from __future__ import annotations

import random
from itertools import cycle
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ModelAbstraction, ModelMapping, ProviderKey
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


# ── ModelRegistry ─────────────────────────────────────────────────────────────

class ModelRegistry:
    """
    Resolves a ModelAbstraction to a ready-to-use LangChain chat model.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Public API ────────────────────────────────────────────────────────────

    async def resolve(
        self,
        abstraction: ModelAbstraction,
        override_params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[BaseChatModel, ModelMapping, ProviderKey]:
        """
        Returns (chat_model, mapping, provider_key) for the given abstraction.
        Raises ValueError if no active mapping / key is found.
        """
        mapping = await self._get_best_mapping(abstraction)
        key     = await self._pick_provider_key(mapping.provider)
        model   = self._instantiate(mapping, key, override_params or {})
        return model, mapping, key

    async def list_abstractions(self) -> List[Dict[str, Any]]:
        """Return all active abstractions with their backing model info."""
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

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _get_best_mapping(self, abstraction: ModelAbstraction) -> ModelMapping:
        result = await self._db.execute(
            select(ModelMapping)
            .where(
                ModelMapping.abstraction == abstraction,
                ModelMapping.is_active == True,
            )
            .order_by(ModelMapping.priority.desc())
        )
        mapping = result.scalars().first()
        if not mapping:
            raise ValueError(
                f"No active model mapping found for abstraction '{abstraction.value}'. "
                "Configure one via POST /admin/model-mappings."
            )
        return mapping

    async def _pick_provider_key(self, provider: str) -> ProviderKey:
        result = await self._db.execute(
            select(ProviderKey)
            .where(ProviderKey.provider == provider, ProviderKey.is_active == True)
            .order_by(ProviderKey.priority.desc())
        )
        keys: List[ProviderKey] = result.scalars().all()
        if not keys:
            raise ValueError(
                f"No active API key registered for provider '{provider}'. "
                "Add one via POST /admin/provider-keys."
            )

        strategy = settings.KEY_ROTATION_STRATEGY
        if strategy == "round_robin":
            idx = _rr_pool.next_index(provider, len(keys))
            return keys[idx]
        elif strategy == "random":
            return random.choice(keys)
        else:  # priority (default: first = highest priority)
            return keys[0]

    def _instantiate(
        self,
        mapping: ModelMapping,
        key: ProviderKey,
        override_params: Dict[str, Any],
    ) -> BaseChatModel:
        cls = _PROVIDER_CLASSES.get(mapping.provider)
        if cls is None:
            raise ValueError(f"Unsupported provider: '{mapping.provider}'")

        base_params: Dict[str, Any] = {
            "model": mapping.model_name,
            **(mapping.extra_params or {}),
        }
        if mapping.max_tokens is not None:
            base_params["max_tokens"] = mapping.max_tokens
        if mapping.temperature is not None:
            base_params["temperature"] = mapping.temperature

        base_params.update(override_params)

        # Inject the API key — each provider class uses a different param name
        key_param = _api_key_param(mapping.provider)
        base_params[key_param] = key.api_key

        return cls(**base_params)


def _api_key_param(provider: str) -> str:
    return {
        "openai":    "openai_api_key",
        "anthropic": "anthropic_api_key",
        "google":    "google_api_key",
    }.get(provider, "api_key")
