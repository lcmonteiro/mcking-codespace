"""
Local configuration for the apikey CLI.

Stored as a YAML file at ``~/.apikey/config.yaml`` with these fields:

- ``proxy_url`` — base URL of the LLM Proxy admin API
- ``admin_key`` — bearer token for admin endpoints
"""
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# ====================================================================================================
# Constants
# ====================================================================================================

CONFIG_DIR  : Path = Path.home() / ".apikey"
CONFIG_PATH : Path = CONFIG_DIR / "config.yaml"

DEFAULT_PROXY_URL : str = "http://localhost:8000"


# ====================================================================================================
# Helpers
# ====================================================================================================


def _ensure_dir(path: Path) -> None:
    """Create parent directory for *path* if it doesn't exist."""
    path.parent.mkdir(parents=True, exist_ok=True)


def _default_config() -> Dict[str, Any]:
    """
    Return the default configuration dictionary.

    Returns:
        Dict with ``proxy_url`` and ``admin_key``.
    """
    return {
        "proxy_url": DEFAULT_PROXY_URL,
        "admin_key": os.environ.get("ADMIN_API_KEY", ""),
    }


# ====================================================================================================
# Public API
# ====================================================================================================


def load() -> Dict[str, Any]:
    """
    Load configuration from disk, falling back to defaults.

    Returns:
        A mutable config dict.
    """
    cfg = _default_config()
    if CONFIG_PATH.exists():
        raw = CONFIG_PATH.read_text(encoding="utf-8")
        if raw.strip():
            merged = yaml.safe_load(raw)
            if isinstance(merged, dict):
                cfg.update(merged)
    return cfg


def save(cfg: Dict[str, Any]) -> None:
    """
    Persist configuration to disk.

    Args:
        cfg: Config dict to save.
    """
    _ensure_dir(CONFIG_PATH)
    CONFIG_PATH.write_text(yaml.dump(cfg, default_flow_style=False), encoding="utf-8")


def get(key: str, default: Any = None) -> Any:
    """
    Return a single config value.

    Args:
        key: Config key name.
        default: Fallback value.

    Returns:
        The config value.
    """
    return load().get(key, default)


def set_key(key: str, value: str) -> None:
    """
    Set a single config key and persist.

    Args:
        key: Config key name (e.g. ``proxy_url``, ``admin_key``).
        value: String value.
    """
    cfg = load()
    cfg[key] = value
    save(cfg)


def show() -> Dict[str, Any]:
    """
    Return the active configuration, masking the admin key.

    Returns:
        A safe-to-print config dict.
    """
    cfg = load()
    if cfg.get("admin_key"):
        raw = cfg["admin_key"]
        visible = raw[:6] + "…" + raw[-4:] if len(raw) > 12 else "…"
        cfg["admin_key"] = visible
    return cfg
