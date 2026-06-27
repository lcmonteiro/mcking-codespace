"""
Bootstrap script — seed the proxy with:

- Model mappings for all abstractions
- Example provider keys
- Two example access tokens (fixed + time-based budgets)

Usage::

    python seed.py
"""
import asyncio
import logging
import os
import sys

from src.db.models import BudgetType, ModelAbstraction, ModelMapping, ProviderKey
from src.db.session import AsyncSessionLocal, init_db
from src.services.budget import BudgetService

logger = logging.getLogger(__name__)


# ====================================================================================================
# Constants — adjust to your real API keys
# ====================================================================================================

OPENAI_KEY_ALICE : str = os.getenv("OPENAI_API_KEY_ALICE", "sk-alice-openai-key")
OPENAI_KEY_BOB   : str = os.getenv("OPENAI_API_KEY_BOB",   "sk-bob-openai-key")
ANTHROPIC_KEY    : str = os.getenv("ANTHROPIC_API_KEY",    "sk-ant-your-key")

# abstraction      provider     model_name                      priority
MAPPINGS = [
    (ModelAbstraction.CODING,    "openai",    "gpt-4o",                       10),
    (ModelAbstraction.CODING,    "anthropic", "claude-3-5-sonnet-20241022",    5),  # fallback
    (ModelAbstraction.CHAT,      "openai",    "gpt-4o-mini",                  10),
    (ModelAbstraction.REASONING, "openai",    "o1-mini",                      10),
    (ModelAbstraction.VISION,    "openai",    "gpt-4o",                       10),
    (ModelAbstraction.EMBEDDING, "openai",    "text-embedding-3-small",       10),
    (ModelAbstraction.SUMMARIZE, "anthropic", "claude-3-haiku-20240307",      10),
]

# owner       provider     key                  priority
PROVIDER_KEYS = [
    ("alice",    "openai",    OPENAI_KEY_ALICE,     10),
    ("bob",      "openai",    OPENAI_KEY_BOB,        5),
    ("company",  "anthropic", ANTHROPIC_KEY,        10),
]


# ====================================================================================================
# Seed
# ====================================================================================================


async def seed() -> None:
    """
    Seed the database with model mappings, provider keys, and access tokens.

    Prints the raw access tokens to stdout — save them immediately as they
    will not be shown again.
    """
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
