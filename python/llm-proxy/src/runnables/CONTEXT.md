# Runnables

Pipelines LangGraph para orquestração da inferência no LLM Proxy.

## Ficheiros

- `proxy_graph.py` — grafo principal de proxy (entrada → auth → rate limit → model resolve → provider call → response)
- `model_resolve.py` — nodo de resolução de modelo para provider
- `budget_auth.py` — nodo de autenticação e verificação de orçamento
- `budget_deduct.py` — nodo de dedução de custo após inferência
