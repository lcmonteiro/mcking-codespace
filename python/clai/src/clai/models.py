"""Model resolution: provider validation, env-var checks, and config merging."""

from __future__ import annotations

import os
import sys
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Provider metadata ──────────────────────────────────────────────────────

Provider = dict[str, str | list[str] | None]

PROVIDERS: dict[str, Provider] = {
    "anthropic": {
        "env_var": "ANTHROPIC_API_KEY",
        "label": "Anthropic",
        "default_model": "anthropic:claude-sonnet-4-6",
        "examples": [
            "claude-sonnet-4-6",
            "claude-opus-4-5",
            "claude-haiku-3-5",
        ],
        "doc_url": "https://docs.anthropic.com/en/docs/api/getting-started",
    },
    "openai": {
        "env_var": "OPENAI_API_KEY",
        "label": "OpenAI",
        "default_model": "openai:gpt-5.5",
        "examples": [
            "gpt-5.5",
            "gpt-4o",
            "o4-mini",
        ],
        "doc_url": "https://platform.openai.com/api-keys",
    },
    "google_genai": {
        "env_var": "GOOGLE_API_KEY",
        "label": "Google Gemini",
        "default_model": "google_genai:gemini-3.6-flash",
        "examples": [
            "gemini-3.6-flash",
            "gemini-3.6-pro",
        ],
        "doc_url": "https://aistudio.google.com/apikey",
    },
    "ollama": {
        "env_var": None,
        "label": "Ollama (local)",
        "default_model": "ollama:qwen2.5-coder",
        "examples": [
            "qwen2.5-coder",
            "llama3.1",
            "codestral",
        ],
        "doc_url": "https://ollama.com/download",
        "note": "Run 'ollama pull <model>' first. No API key needed.",
    },
    "openrouter": {
        "env_var": "OPENROUTER_API_KEY",
        "label": "OpenRouter",
        "default_model": "openrouter:z-ai/glm-5.2",
        "examples": [
            "z-ai/glm-5.2",
            "openai/gpt-5.5",
            "anthropic/claude-sonnet-4",
        ],
        "doc_url": "https://openrouter.ai/keys",
    },
    "deepseek": {
        "env_var": "DEEPSEEK_API_KEY",
        "label": "DeepSeek",
        "default_model": "deepseek:deepseek-coder-v3",
        "examples": [
            "deepseek-coder-v3",
        ],
        "doc_url": "https://platform.deepseek.com/",
    },
    "mistralai": {
        "env_var": "MISTRAL_API_KEY",
        "label": "Mistral AI",
        "default_model": "mistralai:codestral-latest",
        "examples": [
            "codestral-latest",
            "mistral-large-latest",
        ],
        "doc_url": "https://console.mistral.ai/api-keys/",
    },
    "groq": {
        "env_var": "GROQ_API_KEY",
        "label": "Groq",
        "default_model": "groq:qwen-2.5-coder-32b",
        "examples": [
            "qwen-2.5-coder-32b",
            "llama-3.3-70b-versatile",
        ],
        "doc_url": "https://console.groq.com/keys",
    },
}


# ── Model resolution ───────────────────────────────────────────────────────

DEFAULT_MODEL = "anthropic:claude-sonnet-4-6"


def resolve_model(cli_model: Optional[str], cfg_model: Optional[str] = None) -> str:
    """Pick the effective model string: CLI flag > config > default."""
    if cli_model:
        return cli_model
    if cfg_model:
        return cfg_model
    return DEFAULT_MODEL


def provider_from_model(model: str) -> str:
    """Extract the provider prefix from a 'provider:model' string.

    If there's no colon, returns the string as-is (assumes it's a provider)
    so we can still check its env var.
    """
    if ":" in model:
        return model.split(":", 1)[0]
    return model


def model_name_from_model(model: str) -> str:
    """Extract the model name (after the colon)."""
    if ":" in model:
        return model.split(":", 1)[1]
    return model


def check_api_key(model: str) -> Optional[str]:
    """Check if the required env var for *model* is set.

    Returns *None* if OK, or an error message string if the env var is
    missing.
    """
    provider = provider_from_model(model)
    info = PROVIDERS.get(provider)

    if info is None:
        # Unknown provider — don't block, might be a user-defined one
        return None

    env_var = info["env_var"]
    if env_var is None:
        return None  # No env var required (e.g. Ollama)

    if not os.environ.get(env_var):
        examples = info.get("examples", [])
        label = info.get("label", provider)
        ex_str = ", ".join(examples[:3]) if examples else ""
        msg = (
            f"[yellow]⚠  {label} needs {env_var} environment variable.[/]\n"
            f"   Export it or use a different model.\n"
        )
        if ex_str:
            msg += f"   Examples: {ex_str}\n"
        doc = info.get("doc_url")
        if doc:
            msg += f"   Get a key at: {doc}\n"
        return msg

    return None


def format_provider_help() -> str:
    """Build a help table of supported providers."""
    lines = ["[bold]Supported model providers[/]"]
    lines.append("  Format:  [cyan]<provider>:<model>[/]")
    lines.append("")
    for key, info in PROVIDERS.items():
        label = info["label"]
        env = info.get("env_var", "—") or "—"
        examples = info.get("examples", [])
        ex_str = ", ".join(examples[:2]) if examples else ""
        note = info.get("note", "")
        note_str = f"  [dim]{note}[/]" if note else ""
        lines.append(f"  [bold]{key}[/]  → {label}  [dim]({env})[/]")
        if ex_str:
            lines.append(f"     eg: {ex_str}")
        if note_str:
            lines.append(note_str)
        lines.append("")
    return "\n".join(lines)


__all__ = [
    "PROVIDERS",
    "DEFAULT_MODEL",
    "resolve_model",
    "provider_from_model",
    "model_name_from_model",
    "check_api_key",
    "format_provider_help",
]
