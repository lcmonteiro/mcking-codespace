# ====================================================================================================
# ModelResolveRunnable
# ====================================================================================================

"""
ModelResolveRunnable — resolves a model abstraction to a concrete LangChain ChatModel.

LangChain Runnable with typed Pydantic I/O.
"""

import logging
import random
from typing import Any, Dict, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable, RunnableConfig
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from src.db.models import ModelAbstraction, ModelMapping, ProviderKey
from src.db.session import db_contex
from config.settings import settings
from src.services.model_registry import _PROVIDER_CLASSES, _RoundRobinPool, _api_key_param

logger = logging.getLogger(__name__)


# ====================================================================================================
# Module state
# ====================================================================================================

# Round-robin state (shared across runs)
_rr_pool = _RoundRobinPool()


# ====================================================================================================
# I/O Schemas
# ====================================================================================================


class ModelResolveInput(BaseModel):
    """Input schema for model resolution."""

    abstraction     : ModelAbstraction
    override_params : Dict[str, Any] = {}


class ModelResolveOutput(BaseModel):
    """Output schema for model resolution."""

    success       : bool           = False
    model         : Optional[Any]  = None
    mapping       : Optional[Any]  = None
    provider_key  : Optional[Any]  = None
    error_message : Optional[str]  = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


# ====================================================================================================
# Runnable
# ====================================================================================================


class ModelResolveRunnable(Runnable[ModelResolveInput, ModelResolveOutput]):
    """
    Resolve a model abstraction to a concrete LangChain ChatModel with
    provider key rotation.

    Usage:
        result = await ModelResolveRunnable().ainvoke(
            ModelResolveInput(abstraction=ModelAbstraction.CODING)
        )
        if result.success:
            chat_model = result.model  # BaseChatModel instance
    """

    async def ainvoke(
        self,
        input    : ModelResolveInput,
        config   : Optional[RunnableConfig] = None,
        **kwargs : Any,
    ) -> ModelResolveOutput:
        async with db_contex() as db:
            # 1. Best mapping
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
                    success      = False,
                    error_message = (
                        f"No active model mapping found for abstraction "
                        f"'{input.abstraction.value}'. Configure one via "
                        "POST /admin/model-mappings."
                    ),
                )

            # 2. Pick a provider key with rotation
            key_result = await db.execute(
                select(ProviderKey)
                .where(
                    ProviderKey.provider == mapping.provider,
                    ProviderKey.is_active == True,
                )
                .order_by(ProviderKey.priority.desc())
            )
            keys: List[ProviderKey] = key_result.scalars().all()
            if not keys:
                return ModelResolveOutput(
                    success      = False,
                    error_message = (
                        f"No active API key registered for provider "
                        f"'{mapping.provider}'. Add one via POST /admin/provider-keys."
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

            # 3. Instantiate model
            cls = _PROVIDER_CLASSES.get(mapping.provider)
            if cls is None:
                return ModelResolveOutput(
                    success      = False,
                    error_message = f"Unsupported provider: '{mapping.provider}'",
                )

            base_params: Dict[str, Any] = {
                "model"    : mapping.model_name,
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
                    success      = True,
                    model        = model,
                    mapping      = mapping,
                    provider_key = key,
                )
            except Exception as exc:
                return ModelResolveOutput(
                    success       = False,
                    error_message = f"Failed to instantiate model: {exc}",
                )
