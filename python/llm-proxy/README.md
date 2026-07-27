# LLM Proxy

A production-ready LLM proxy built on **FastAPI + LangChain**.

<img src="docs/architecture-overview.svg" alt="System Architecture" width="800"/>

<img src="docs/request-flow.svg" alt="Request Flow" width="880"/>

---

## 1. Use Cases

| Use Case | Description |
|---|---|
| **Multi-tenant API gateway** | Serve multiple teams/apps through a single endpoint with per-team budgets and usage tracking |
| **Provider failover** | Automatically rotate between OpenAI, Anthropic, etc. when a key is rate-limited or exhausted |
| **Cost control** | Enforce per-wallet token budgets (fixed or monthly-reset) to prevent runaway spend |
| **Model abstraction** | Clients reference `coding`, `chat`, `reasoning` — the proxy maps to real models without client changes |
| **Centralised audit** | Every request is logged with provider, model, token counts, and latency — one place to see all LLM usage |
| **Credit management** | Transfer provider credits to wallets — providers track spend against their budget, wallets accumulate from multiple sources |

---

## 2. Requirements

- **Python** ≥ 3.11
- **SQLite** (dev) or **PostgreSQL** (production) — async drivers via `aiosqlite` / `asyncpg`
- **LLM provider keys** — at least one OpenAI or Anthropic key registered

### Dependencies (core)

| Package | Purpose |
|---|---|
| FastAPI + uvicorn | HTTP server |
| LangChain / LangGraph | LLM integration + pipeline orchestration |
| SQLAlchemy 2.0 + Alembic | ORM + migrations |
| Pydantic Settings | Configuration via env / `.env` |
| structlog + prometheus-client | Observability |

### Configuration

Copy `.env.example` → `.env` and set:

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `change-me-in-production` | Signing key for tokens |
| `ADMIN_API_KEY` | `admin-secret-change-me` | Bearer key for `/admin/*` endpoints |
| `DATABASE_URL` | `sqlite+aiosqlite:///./llm_proxy.db` | Database connection string |
| `KEY_ROTATION_STRATEGY` | `round_robin` | `round_robin`, `priority`, or `random` |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Listen port |

---

## 3. Design

### Architecture overview

```
Client → /v1/chat/completions → ProxyRunnable (LangGraph)
  ├── BudgetAuthRunnable      → validate wallet token + check balance
  ├── ModelResolveRunnable    → abstraction → real model + pick provider key
  ├── Invoke LLM provider     → OpenAI / Anthropic / etc. via LangChain
  └── BudgetDeductRunnable    → deduct tokens + write audit log
```

### Core concepts

**Model abstractions** — clients never reference real model names:

| Abstraction | Default backing model |
|---|---|
| `coding` | `gpt-4o` (OpenAI), fallback: `claude-3-5-sonnet` |
| `chat` | `gpt-4o-mini` |
| `reasoning` | `o1-mini` |
| `vision` | `gpt-4o` |
| `embedding` | `text-embedding-3-small` |
| `summarize` | `claude-3-haiku` |

**Provider keys** — each registered with a credit model:

| Credit Model | Behaviour |
|---|---|
| `one_time` | Fixed budget that does not refresh — once depleted, it's gone |
| `monthly_reset` | Budget resets to the configured amount each month (non-cumulative) |

**Wallets** — hold accumulated credit from providers:

- Wallets are created with a label, owner, and optional scope (`allowed_models`, `valid_until`)
- Credit is transferred from provider keys to wallets via `/admin/wallets/{id}/providers`
- Wallet balance is cumulative — it never resets on its own
- The wallet's `token` (generated once at creation) is used as a Bearer token for inference requests

**Provider key rotation** — multiple keys per provider, rotated by strategy:

```
KEY_ROTATION_STRATEGY=round_robin   # even distribution
KEY_ROTATION_STRATEGY=priority      # highest priority key first
KEY_ROTATION_STRATEGY=random        # random each request
```

### Database tables

| Table | Purpose |
|---|---|
| `provider_keys` | Provider API keys with credit model, budget, and owner |
| `model_mappings` | Abstraction → provider/model mappings with priority |
| `wallets` | Consumer wallets holding accumulated credit |
| `wallet_provider_links` | Links provider keys to wallets with credited amounts |
| `access_tokens` | Legacy tokens (kept for backward compatibility, not used in wallet flow) |
| `usage_logs` | Immutable audit log of every request |

---

## 4. Basic Usage

### Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env: set SECRET_KEY and ADMIN_API_KEY

# 3. Seed the database (creates tables + example config)
python seed.py

# 4. Start the server
uvicorn main:app --reload
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) for interactive Swagger docs.

### End-to-end flow

```bash
# 1. Register a provider key (OpenAI) with a monthly-reset budget
curl -X POST http://localhost:8000/admin/provider-keys \
  -H "Authorization: Bearer admin-secret-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "owner_label": "alice",
    "provider": "openai",
    "api_key": "sk-...",
    "priority": 10,
    "credit_model": "monthly_reset",
    "budget_amount": 1000000
  }'
# → returns provider key ID, e.g. "a1b2c3d4-..."

# 2. Create a wallet for the frontend team
curl -X POST http://localhost:8000/admin/wallets \
  -H "Authorization: Bearer admin-secret-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "label": "frontend-team",
    "owner": "frontend",
    "allowed_models": ["chat", "coding"],
    "valid_until": "2027-01-01"
  }'
# → returns wallet_id + wallet token (save this!)

# 3. Transfer credit from provider to wallet
curl -X POST http://localhost:8000/admin/wallets/<WALLET_ID>/providers \
  -H "Authorization: Bearer admin-secret-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "provider_id": "<PROVIDER_KEY_ID>",
    "credit_amount": 500000
  }'
# → wallet now has 500,000 tokens available

# 4. Make an inference request using the wallet token
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer <WALLET_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "coding",
    "messages": [
      {"role": "user", "content": "Write a Python quicksort."}
    ]
  }'
```

---

## 5. API & Commands Reference

### Inference endpoints (Bearer `<wallet_token>`)

```
POST /v1/chat/completions    OpenAI-compatible chat
POST /v1/complete            Simplified single-turn
GET  /v1/models              List available abstractions
```

### Admin endpoints (Bearer `<ADMIN_API_KEY>`)

#### Wallets

```
POST   /admin/wallets                        Create a wallet
GET    /admin/wallets                        List wallets (filter by owner)
GET    /admin/wallets/{id}                   Get wallet details
PATCH  /admin/wallets/{id}/revoke            Revoke a wallet
GET    /admin/wallets/{id}/providers         List linked providers
POST   /admin/wallets/{id}/providers         Transfer credit from provider to wallet
DELETE /admin/wallets/{id}/providers/{pid}   Unlink a provider (no refund)
```

#### Provider keys

```
POST   /admin/provider-keys                  Register a key (with credit model + budget)
GET    /admin/provider-keys                  List keys (filter by provider)
PATCH  /admin/provider-keys/{id}/budget      Update budget (amount and/or credit model)
PATCH  /admin/provider-keys/{id}/toggle      Enable/disable a key
DELETE /admin/provider-keys/{id}             Delete a key
```

#### Model mappings

```
POST   /admin/model-mappings                 Create a mapping
GET    /admin/model-mappings                 List mappings
PATCH  /admin/model-mappings/{id}/toggle     Enable/disable
DELETE /admin/model-mappings/{id}            Delete a mapping
```

#### Usage / audit

```
GET    /admin/usage                          Audit log (filterable by wallet, provider, abstraction)
GET    /admin/usage/stats                    Aggregate stats per abstraction/provider
```

### CLI commands

The CLI (`llm-proxy`) provides the same admin operations from the terminal:

```bash
# Provider keys
llm-proxy provider add openai sk-xxx --owner-label alice --priority 10 \
    --budget-type monthly --budget 1000000
llm-proxy provider list
llm-proxy provider budget <id> --budget 2000000
llm-proxy provider budget <id> --budget-type one_time
llm-proxy provider toggle <id>
llm-proxy provider remove <id>

# Wallets
llm-proxy wallet create frontend-team frontend --valid-until 2027-01-01 \
    --allowed-models coding,chat
llm-proxy wallet list
llm-proxy wallet get <id>
llm-proxy wallet revoke <id>
llm-proxy wallet add-provider <wallet-id> --provider <provider-id> --credit 500000
llm-proxy wallet remove-provider <wallet-id> --provider <provider-id>
llm-proxy wallet list-providers <wallet-id>

# Model mappings
llm-proxy mapping add coding openai gpt-4o --priority 10
llm-proxy mapping list
llm-proxy mapping toggle <id>
llm-proxy mapping remove <id>

# Usage & stats
llm-proxy usage --limit 20 --abstraction coding
llm-proxy stats

# Server management
llm-proxy serve status
llm-proxy serve start [--port 8080] [--reload]
llm-proxy serve stop
llm-proxy serve restart

# Config
llm-proxy config set proxy_url http://localhost:8000
llm-proxy config show
```

### Adding a new provider

1. Install the LangChain provider package (e.g. `langchain-mistralai`)
2. Add it to `_PROVIDER_CLASSES` in `src/services/model_registry.py`
3. Add the key param name in `_api_key_param()`
4. Register a provider key via `/admin/provider-keys`
5. Create a model mapping via `/admin/model-mappings`

---

## Architecture

```
llm-proxy/
├── main.py                        FastAPI app + lifespan
├── seed.py                        DB bootstrap
├── requirements.txt
├── .env.example
├── docs/
│   ├── architecture-overview.svg  System architecture diagram
│   └── request-flow.svg           Request pipeline flow diagram
├── config/
│   └── settings.py                Pydantic-settings config
├── seeds/
│   ├── model_mappings.yaml        Default abstraction → model mappings
│   └── provider_keys.yaml         Default provider key config
├── cli/
│   └── src/cli/
│       ├── main.py                Click CLI (llm-proxy command)
│       ├── client.py              HTTP client for admin API
│       └── config.py              Local config (~/.llm-proxy/config.toml)
└── src/
    ├── db/
    │   ├── models.py              SQLAlchemy ORM (Wallet, ProviderKey, ModelMapping, …)
    │   └── session.py             Engine, session factory
    ├── runnables/
    │   ├── proxy_graph.py         Orchestrator (ProxyRunnable — 4-step pipeline)
    │   ├── budget_auth.py         BudgetAuthRunnable — wallet auth + balance check
    │   ├── budget_deduct.py       BudgetDeductRunnable — deduct + audit log
    │   └── model_resolve.py       ModelResolveRunnable — resolve abstraction
    ├── services/
    │   ├── model_registry.py      ModelRegistry + key rotation
    │   ├── budget.py              BudgetService + token hash utils
    │   └── credit_models.py       Credit model strategies (one_time, monthly_reset)
    ├── routes/
    │   ├── inference.py           /v1/* endpoints
    │   └── admin.py               /admin/* endpoints (wallets, keys, mappings, usage)
    └── guards/
        └── auth.py                Bearer token extraction
```

---

## Production checklist

- [ ] Switch `DATABASE_URL` to PostgreSQL
- [ ] Set strong `SECRET_KEY` and `ADMIN_API_KEY`
- [ ] Encrypt API keys at rest (wrap `ProviderKey.api_key` with Fernet)
- [ ] Enable `REDIS_URL` for distributed rate limiting
- [ ] Put behind a reverse proxy (nginx / Caddy) with TLS
- [ ] Set `CORS_ORIGINS` to your actual frontend domains
- [ ] Add Prometheus scraping (`/metrics` via `prometheus-fastapi-instrumentator`)
