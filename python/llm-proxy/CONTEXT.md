# LLM Proxy

Proxy para LLM providers com rate limiting, rotação de chaves, autenticação e observabilidade.

## Stack

- **FastAPI** — servidor HTTP assíncrono
- **SQLite + aiosqlite** — persistência (rate limits, tokens, usage)
- **Pydantic Settings** — configuração via env/.env
- **LangGraph** — pipeline de inferência (runnables)

## Estrutura

```
config/     — configuração (Pydantic Settings)
seeds/      — dados iniciais (model mappings, provider keys)
src/        — código fonte
  db/         — camada de base de dados
  middleware/ — auth, rate limiting
  models/     — data models / schemas
  routes/     — API endpoints
  runnables/  — LangGraph pipelines
  services/   — lógica de negócio
tests/      — testes
```
