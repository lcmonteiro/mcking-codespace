# Source

Código fonte principal do LLM Proxy.

## Módulos

- `db/` — camada de base de dados (SQLite + aiosqlite)
- `middleware/` — middleware FastAPI (auth, rate limiting)
- `models/` — schemas e data models Pydantic
- `routes/` — endpoints da API
- `runnables/` — pipelines LangGraph (orquestração de inferência)
- `services/` — lógica de negócio (budget, model registry)
