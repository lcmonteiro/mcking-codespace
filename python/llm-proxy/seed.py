"""
Bootstrap script — seed the proxy with:

- Model mappings for all abstractions
- Example provider keys
- Two example access tokens (fixed + time-based budgets)

Usage::

    python seed.py

Configuration is loaded from ``seeds/model_mappings.yaml`` and
``seeds/provider_keys.yaml``.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import List

import yaml

from src.db.models import BudgetType, ModelAbstraction, ModelMapping, ProviderKey
from src.db.session import AsyncSessionLocal, init_db
from src.services.budget import BudgetService

logger = logging.getLogger(__name__)

# ====================================================================================================
# Paths
# ====================================================================================================

SEEDS_DIR = Path(__file__).parent / "seeds"


# ====================================================================================================
# Loaders
# ====================================================================================================


def _load_mappings(path: Path) -> List[tuple]:
    """
    Load model mappings from *path*.

    Returns:
        List of (abstraction, provider, model_name, priority) tuples.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    result: List[tuple] = []
    for entry in raw["mappings"]:
        result.append((
            ModelAbstraction(entry["abstraction"]),
            entry["provider"],
            entry["model"],
            entry["priority"],
        ))
    return result


def _load_provider_keys(path: Path) -> List[tuple]:
    """
    Load provider API-key references from *path*.

    Each entry may reference an environment variable; the env value is used
    when set, otherwise the YAML ``default`` field is used.

    Returns:
        List of (owner, provider, api_key, priority) tuples.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    result: List[tuple] = []
    for entry in raw["keys"]:
        api_key = os.getenv(entry["env_var"], entry["default"])
        result.append((
            entry["owner"],
            entry["provider"],
            api_key,
            entry["priority"],
        ))
    return result


# ====================================================================================================
# Seed
# ====================================================================================================


async def seed() -> None:
    """
    Seed the database with model mappings, provider keys, and access tokens.

    Prints the raw access tokens to stdout — save them immediately as they
    will not be shown again.
    """
    mappings_path  = SEEDS_DIR / "model_mappings.yaml"
    provider_path  = SEEDS_DIR / "provider_keys.yaml"
    local_provider_path = SEEDS_DIR / "provider_keys.local.yaml"

    MAPPINGS       = _load_mappings(mappings_path)
    PROVIDER_KEYS  = _load_provider_keys(
        local_provider_path if local_provider_path.exists() else provider_path
    )

    logger.info("Loaded %d model mappings  from %s", len(MAPPINGS), mappings_path)
    logger.info("Loaded %d provider keys  from %s", len(PROVIDER_KEYS),
                local_provider_path if local_provider_path.exists() else provider_path)

    logger.info("Initialising database\u2026")
    await init_db()

    async with AsyncSessionLocal() as db:
        # ── Model mappings ─────────────────────────────────────────────────────────────────────────
        logger.info("Seeding model mappings\u2026")
        for abstraction, provider, model_name, priority in MAPPINGS:
            mapping = ModelMapping(
                abstraction = abstraction,
                provider    = provider,
                model_name  = model_name,
                priority    = priority,
            )
            db.add(mapping)
            logger.info(
                "  %s \u2192 %s/%s  (priority=%d)",
                abstraction.value, provider, model_name, priority,
            )

        # ── Provider keys ──────────────────────────────────────────────────────────────────────────
        logger.info("Seeding provider keys\u2026")
        for owner, provider, api_key, priority in PROVIDER_KEYS:
            key = ProviderKey(
                owner_label = owner,
                provider    = provider,
                api_key     = api_key,
                priority    = priority,
            )
            db.add(key)
            logger.info("  %s \u2192 %s  (priority=%d)", owner, provider, priority)

        # ── Access tokens ──────────────────────────────────────────────────────────────────────────
        logger.info("Seeding access tokens\u2026")
        svc = BudgetService(db)

        raw1, t1 = await svc.create_token(
            label        = "demo-fixed",
            owner        = "demo-user",
            budget_type  = BudgetType.FIXED,
            token_budget = 100_000,
        )
        logger.info("  Fixed budget token  : %s", raw1)

        raw2, t2 = await svc.create_token(
            label           = "demo-monthly",
            owner           = "demo-user",
            budget_type     = BudgetType.TIME_BASED,
            token_budget    = 500_000,
            refresh_period  = "monthly",
            allowed_models  = ["chat", "coding"],
        )
        logger.info("  Monthly budget token: %s", raw2)

        raw3, t3 = await svc.create_token(
            label       = "internal-unlimited",
            owner       = "internal",
            budget_type = BudgetType.UNLIMITED,
        )
        logger.info("  Unlimited token     : %s", raw3)

        await db.commit()

    logger.info(
        "Seed complete. Save the raw tokens above \u2014 they won\u2019t be shown again."
    )


# ====================================================================================================
# Entry point
# ====================================================================================================


def main() -> None:
    """Run the seed script."""
    logging.basicConfig(
        level  = logging.INFO,
        format = "%(levelname)s %(message)s",
    )
    sys.path.insert(0, os.path.dirname(__file__))
    asyncio.run(seed())


if __name__ == "__main__":
    main()
