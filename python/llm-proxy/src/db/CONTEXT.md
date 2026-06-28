# Database Layer

Camada de persistência do LLM Proxy. Usa SQLite + aiosqlite (async).

## Ficheiros

- `models.py` — definições das tabelas (SQLAlchemy declarative base)
- `session.py` — gestão de sessão async para a base de dados
