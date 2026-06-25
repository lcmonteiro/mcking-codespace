"""
Bootstrap script — seed the proxy with:
  - Model mappings for all abstractions
  - Example provider keys
  - Two example access tokens (fixed + time-based budgets)

Usage:
    python seed.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from src.db.models import BudgetType, ModelAbstraction, ModelMapping, ProviderKey
from src.db.session import AsyncSessionLocal, init_db
from src.services.budget import BudgetService


# ── Adjust these to your real API keys ───────────────────────────────────────

OPENAI_KEY_ALICE  = os.getenv("OPENAI_API_KEY_ALICE",  "sk-alice-openai-key")
OPENAI_KEY_BOB    = os.getenv("OPENAI_API_KEY_BOB",    "sk-bob-openai-key")
ANTHROPIC_KEY     = os.getenv("ANTHROPIC_API_KEY",     "sk-ant-your-key")


MAPPINGS = [
    # abstraction      provider     model                     priority
    (ModelAbstraction.CODING,    "openai",    "gpt-4o",                    10),
    (ModelAbstraction.CODING,    "anthropic", "claude-3-5-sonnet-20241022",  5),  # fallback
    (ModelAbstraction.CHAT,      "openai",    "gpt-4o-mini",               10),
    (ModelAbstraction.REASONING, "openai",    "o1-mini",                   10),
    (ModelAbstraction.VISION,    "openai",    "gpt-4o",                    10),
    (ModelAbstraction.EMBEDDING, "openai",    "text-embedding-3-small",    10),
    (ModelAbstraction.SUMMARIZE, "anthropic", "claude-3-haiku-20240307",   10),
]

PROVIDER_KEYS = [
    # owner       provider     key                  priority
    ("alice",    "openai",    OPENAI_KEY_ALICE,     10),
    ("bob",      "openai",    OPENAI_KEY_BOB,        5),
    ("company",  "anthropic", ANTHROPIC_KEY,        10),
]


async def seed():
    print("Initialising database…")
    await init_db()

    async with AsyncSessionLocal() as db:
        # ── Model mappings ────────────────────────────────────────────────────
        print("\nSeeding model mappings…")
        for abstraction, provider, model_name, priority in MAPPINGS:
            mapping = ModelMapping(
                abstraction=abstraction,
                provider=provider,
                model_name=model_name,
                priority=priority,
            )
            db.add(mapping)
            print(f"  {abstraction.value:12s} → {provider}/{model_name}  (priority={priority})")

        # ── Provider keys ─────────────────────────────────────────────────────
        print("\nSeeding provider keys…")
        for owner, provider, api_key, priority in PROVIDER_KEYS:
            key = ProviderKey(
                owner_label=owner,
                provider=provider,
                api_key=api_key,
                priority=priority,
            )
            db.add(key)
            print(f"  {owner:10s} → {provider}  (priority={priority})")

        # ── Access tokens ─────────────────────────────────────────────────────
        print("\nSeeding access tokens…")
        svc = BudgetService(db)

        raw1, t1 = await svc.create_token(
            label="demo-fixed",
            owner="demo-user",
            budget_type=BudgetType.FIXED,
            token_budget=100_000,
        )
        print(f"  Fixed budget token  : {raw1}")

        raw2, t2 = await svc.create_token(
            label="demo-monthly",
            owner="demo-user",
            budget_type=BudgetType.TIME_BASED,
            token_budget=500_000,
            refresh_period="monthly",
            allowed_models=["chat", "coding"],
        )
        print(f"  Monthly budget token: {raw2}")

        raw3, t3 = await svc.create_token(
            label="internal-unlimited",
            owner="internal",
            budget_type=BudgetType.UNLIMITED,
        )
        print(f"  Unlimited token     : {raw3}")

        await db.commit()

    print("\n✓ Seed complete. Save the raw tokens above — they won't be shown again.")


if __name__ == "__main__":
    asyncio.run(seed())
