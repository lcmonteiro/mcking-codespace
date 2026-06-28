# Source

Main source code for the LLM Proxy.

## Modules

- `db/` — database layer (SQLite + aiosqlite)
- `guards/` — guard functions (auth, rate limiting)
- `models/` — Pydantic schemas and data models
- `routes/` — API endpoints
- `runnables/` — LangGraph pipelines (inference orchestration)
- `services/` — business logic (budget, model registry)
