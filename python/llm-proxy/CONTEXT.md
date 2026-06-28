# LLM Proxy

Proxy for LLM providers with rate limiting, key rotation, authentication, and observability.

## Stack

- **FastAPI** — async HTTP server
- **SQLite + aiosqlite** — persistence (rate limits, tokens, usage)
- **Pydantic Settings** — configuration via env/.env
- **LangGraph** — inference pipeline (runnables)

## Structure

```
config/     — configuration (Pydantic Settings)
seeds/      — initial data (model mappings, provider keys)
src/        — source code
  db/         — database layer
  middleware/ — auth, rate limiting
  models/     — data models / schemas
  routes/     — API endpoints
  runnables/  — LangGraph pipelines
  services/   — business logic
tests/      — tests
```
