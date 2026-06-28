# Runnables

LangGraph pipelines for inference orchestration in the LLM Proxy.

## Files

- `proxy_graph.py` — main proxy graph (input → auth → rate limit → model resolve → provider call → response)
- `model_resolve.py` — model-to-provider resolution node
- `budget_auth.py` — authentication and budget check node
- `budget_deduct.py` — cost deduction node after inference
