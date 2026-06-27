# ====================================================================================================
# Model Registry
# ====================================================================================================

"""
Model Registry — shared utilities and internal ModelRegistry for admin compatibility.

LangChain Runnable is in src/services/runs/model_resolve.py.
"""

import logging
import random
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ModelAbstraction, ModelMapping, ProviderKey
from config.settings import settings

logger = logging.getLogger(__name__)


# ====================================================================================================
# Constants
# ====================================================================================================

_PROVIDER_CLASSES: Dict[str, type] = {
    "openai"    : ChatOpenAI,
    "anthropic" : ChatAnthropic,
}


# ====================================================================================================
# Private helpers
# ====================================================================================================


def _api_key_param(provider: str) -> str:
    """
    Map a provider name to its API key parameter name.

    Args:
        provider : Provider name ('openai', 'anthropic', 'google').

    Returns:
        API key parameter name expected by the LangChain constructor.
    """
    return {
        "openai"    : "openai_api_key",
        "anthropic" : "anthropic_api_key",
        "google"    : "google_api_key",
    }.get(provider, "api_key")


# ====================================================================================================
# Key rotation state
# ====================================================================================================


class _RoundRobinPool:
    """In-memory round-robin cursor pool for provider key rotation."""

    def __init__(self) -> None:
        """Initialize an empty cursor map."""
        self._cursors: Dict[str, int] = {}

    def next_index(self, pool_id: str, pool_size: int) -> int:
        """
        Get the next index for a given pool, cycling around.

        Args:
            pool_id   : Pool identifier (provider name).
            pool_size : Number of items in the pool.

        Returns:
            Next index in round-robin order.
        """
        idx = self._cursors.get(pool_id, 0) % pool_size
        self._cursors[pool_id] = idx + 1
        return idx


# Round-robin state (shared across runs)
_rr_pool = _RoundRobinPool()


# ====================================================================================================
# Internal ModelRegistry (admin compat)
# ====================================================================================================


class ModelRegistry:
    """
    Internal implementation for admin endpoints.

    Prefer ModelResolveRunnable for LangChain pipelines.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with a database session.

        Args:
            db : Async database session.
        """
        self._db = db

    async def resolve(
        self,
        abstraction     : ModelAbstraction,
        override_params : Optional[Dict[str, Any]] = None,
    ) -> Tuple[BaseChatModel, ModelMapping, ProviderKey]:
        """
        Resolve a model abstraction to a concrete ChatModel.

        Args:
            abstraction     : Requested model abstraction.
            override_params : Optional overrides for model constructor params.

        Returns:
            Tuple of (ChatModel, ModelMapping, ProviderKey).

        Raises:
            ValueError : If resolution fails.
        """
        from src.runnables.model_resolve import ModelResolveInput, ModelResolveRunnable
        runnable = ModelResolveRunnable()
        result = await runnable.ainvoke(ModelResolveInput(
            abstraction    = abstraction,
            override_params = override_params or {},
        ))
        if not result.success:
            raise ValueError(result.error_message or "Model resolution failed")
        return result.model, result.mapping, result.provider_key

    async def list_abstractions(self) -> List[Dict[str, Any]]:
        """
        List all configured model abstractions with providers and fallbacks.

        Returns:
            List of abstraction dicts with 'abstraction', 'primary_provider',
            'primary_model', and 'fallbacks'.
        """
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
                    "abstraction"     : key,
                    "primary_provider" : r.provider,
                    "primary_model"    : r.model_name,
                    "fallbacks"        : [],
                }
            else:
                seen[key]["fallbacks"].append(f"{r.provider}/{r.model_name}")
        return list(seen.values())
