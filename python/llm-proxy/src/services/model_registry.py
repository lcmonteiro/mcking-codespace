"""
Model Registry — shared utilities and internal ModelRegistry for admin compatibility.
LangChain Runnable is in src/services/runs/model_resolve.py.
"""
from __future__ import annotations

import random
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
    def __init__(self) -> None:
        self._cursors: Dict[str, int] = {}

    def next_index(self, pool_id: str, pool_size: int) -> int:
        idx = self._cursors.get(pool_id, 0) % pool_size
        self._cursors[pool_id] = idx + 1
        return idx


_rr_pool = _RoundRobinPool()


# ── Internal ModelRegistry (admin compat) ─────────────────────────────────────

class ModelRegistry:
    """
    Internal implementation for admin endpoints.
    Prefer ModelResolveRunnable for LangChain pipelines.
    """
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def resolve(
        self,
        abstraction: ModelAbstraction,
        override_params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[BaseChatModel, ModelMapping, ProviderKey]:
        from src.runnables.model_resolve import ModelResolveInput, ModelResolveRunnable
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
