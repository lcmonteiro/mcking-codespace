# Database Layer

Persistence layer for the LLM Proxy. Uses SQLite + aiosqlite (async).

## Files

- `models.py` — table definitions (SQLAlchemy declarative base)
- `session.py` — async session management for the database
