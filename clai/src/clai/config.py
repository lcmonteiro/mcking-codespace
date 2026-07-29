"""Config parser for .clai.yml / .clai.toml project config.

Looks for a config file in the project root and returns a normalized dict
that controls agent permissions, tools, and behaviour.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

try:
    import tomllib  # Python >=3.11
except ImportError:
    tomllib = None  # type: ignore[assignment]


# ── Schema defaults ────────────────────────────────────────────────────────

DEFAULT_CONFIG: dict[str, Any] = {
    "model": None,  # "anthropic:..." or "openai:..." or "ollama:..."
    "permissions": {
        "allow_paths": ["."],
        "deny_paths": [
            ".git/",
            ".venv/",
            "venv/",
            "node_modules/",
            "__pycache__/",
            ".env",
            ".env.*",
        ],
        "max_file_size_kb": 512,
    },
    "commands": {
        "allow_prefixes": [],  # empty = all allowed
        "deny_prefixes": [
            "rm -rf /",
            "sudo ",
            "chmod ",
            "chown ",
            "dd ",
            "mkfs",
            "shutdown",
            "reboot",
            "halt",
        ],
    },
    "tools": {
        "exclude": [],
    },
    "system_prompt_additions": "",
    "max_turns": 50,
}


def find_config(project_dir: str) -> Optional[Path]:
    """Look for a .clai config file in *project_dir*.

    Priority: .clai.yml > .clai.yaml > .clai.toml > clai.yml > clai.toml
    Returns the first that exists, or *None*.
    """
    candidates = [
        ".clai.yml",
        ".clai.yaml",
        ".clai.toml",
        "clai.yml",
        "clai.toml",
    ]
    for name in candidates:
        p = Path(project_dir) / name
        if p.is_file():
            return p
    return None


def load_config(project_dir: str) -> dict[str, Any]:
    """Load and merge the project config (if any) with defaults."""
    cfg = DEFAULT_CONFIG.copy()
    path = find_config(project_dir)
    if path is None:
        return cfg

    raw: dict[str, Any] = {}
    suffix = path.suffix.lower()
    try:
        if suffix in (".yml", ".yaml"):
            if yaml is None:
                raise RuntimeError(
                    "PyYAML is required for .clai.yml — run: pip install pyyaml"
                )
            with open(path, "r") as fh:
                raw = yaml.safe_load(fh) or {}
        elif suffix == ".toml":
            if tomllib is None:
                raise RuntimeError(
                    "tomllib not available — use Python >=3.11 or install tomli"
                )
            with open(path, "rb") as fh:
                raw = tomllib.load(fh) or {}
    except Exception as exc:
        raise RuntimeError(f"Failed to parse {path}: {exc}") from exc

    # Deep-merge raw into defaults
    _deep_merge(cfg, raw)
    return cfg


def _deep_merge(base: dict, overrides: dict) -> None:
    """Recursively merge *overrides* into *base* (in-place)."""
    for key, val in overrides.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val


# ── Apply config to agent params ───────────────────────────────────────────


def build_filesystem_permissions(cfg: dict[str, Any]) -> list[dict]:
    """Translate the config permissions section into Deep Agents permission entries."""
    perms = cfg.get("permissions", {})
    entries: list[dict] = []

    allow = perms.get("allow_paths", ["."])
    deny = perms.get("deny_paths", [])

    if deny:
        entries.append({"path": ..., "type": "deny", "patterns": deny})

    if allow and allow != ["."]:
        entries.append({"path": ..., "type": "allow", "patterns": allow})

    return entries


def build_command_safety(cfg: dict[str, Any], default_exclusions: list[str]) -> list[str]:
    """Return a combined, deduplicated list of denied command prefixes."""
    cmd = cfg.get("commands", {})
    denied = list(default_exclusions)
    denied.extend(cmd.get("deny_prefixes", []))
    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for item in denied:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


__all__ = [
    "DEFAULT_CONFIG",
    "find_config",
    "load_config",
    "build_filesystem_permissions",
    "build_command_safety",
]
