"""Deep Agent configuration for code development.

Loads a .clai.yml / .clai.toml from the project root to control
the model, filesystem permissions, allowed commands, excluded tools,
system prompt additions, and more.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

from clai.config import load_config, build_command_safety
from clai.models import resolve_model, check_api_key, format_provider_help
from clai.tools import (
    git_diff,
    git_log,
    git_status,
    list_directory,
    make_run_command,
    py_compile_check,
)

logger = logging.getLogger(__name__)

# ── Base system prompt ─────────────────────────────────────────────────────

CODE_DEV_INSTRUCTIONS = """You are an expert software engineer assistant.
Your job is to help develop, debug, refactor, and improve code in the given project directory.

## How you work

1. **Understand the project first** — read key files (README, pyproject.toml, Cargo.toml,
   package.json, etc.) to understand the tech stack before making changes.

2. **Plan before coding** — use `write_todos` to break down complex tasks into steps.
   Think about edge cases, existing patterns, and potential side effects.

3. **Read before writing** — always read a file before editing it. Understand what's there
   before changing it.

4. **Make focused changes** — keep diffs minimal. Don't refactor code you're not asked to touch.

5. **Test your work** — after making changes, run the relevant tests or at least do a
   syntax/compile check.

## Project filesystem

You have full access to the project directory via the built-in filesystem tools:
- `read_file` / `write_file` / `edit_file` — read and modify files
- `ls` — list directory contents
- `glob` / `grep` — find files and search within them
- `execute` — run shell commands

## Additional tools

- `run_command` — run arbitrary commands (build, test, lint, format, install)
- `git_status` / `git_diff` / `git_log` — inspect git state
- `list_directory` — get a recursive tree view of files
- `py_compile_check` — quick Python syntax verification

## Sub-agents

For complex multi-step tasks, you can delegate to sub-agents via the `task` tool.
This is useful for:
- Deep research into a specific subsystem
- Large refactoring that should be isolated
- Exploratory work with its own context budget
"""


# ── Default denied command prefixes (safety baseline) ──────────────────────

BASE_DENIED_COMMANDS = [
    "rm -rf /",
    "sudo ",
    "chmod ",
    "chown ",
    "dd ",
    "mkfs",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
]


def create_coding_agent(
    project_dir: str,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
):
    """Create a Deep Agent configured for code development in *project_dir*.

    Reads ``.clai.yml`` / ``.clai.toml`` from *project_dir* (if present) and
    applies:
    - Model provider config
    - Command allow/deny prefixes
    - System prompt additions
    - Tool exclusions
    - Max file size (injected into prompt)
    """
    # ── Load config & resolve model ─────────────────────────────────────
    cfg = load_config(project_dir)
    effective_model = resolve_model(
        cli_model=model,
        cfg_model=cfg.get("model"),
    )

    # Check API key before building agent (early feedback)
    key_warning = check_api_key(effective_model)
    if key_warning:
        logger.warning("API key check: %s", key_warning)

    perms = cfg.get("permissions", {})
    tools_cfg = cfg.get("tools", {})
    cmd_cfg = cfg.get("commands", {})

    excluded_tools: list[str] = tools_cfg.get("exclude", [])

    # ── Build tool list (respecting exclusions) ────────────────────────
    deny_prefixes = build_command_safety(cfg, BASE_DENIED_COMMANDS)

    tool_registry = {
        "run_command": make_run_command(
            deny_prefixes=deny_prefixes,
            allow_prefixes=cmd_cfg.get("allow_prefixes"),
        ),
        "git_status": git_status,
        "git_diff": git_diff,
        "git_log": git_log,
        "list_directory": list_directory,
        "py_compile_check": py_compile_check,
    }

    agent_tools = [
        fn for name, fn in tool_registry.items()
        if name not in excluded_tools
    ]

    # ── System prompt ──────────────────────────────────────────────────
    prompt_parts = [system_prompt or CODE_DEV_INSTRUCTIONS]

    additions = cfg.get("system_prompt_additions", "")
    if additions:
        prompt_parts.append(additions)

    # Inject max-file-size info if set
    max_kb = perms.get("max_file_size_kb", 0)
    if max_kb:
        prompt_parts.append(
            f"\n## File size limit\n"
            f"Files larger than {max_kb} KB should not be read in full — "
            f"use `grep` or `execute` with `head` / `tail` instead."
        )

    # Inject denied-path awareness
    denied_paths = perms.get("deny_paths", [])
    if denied_paths:
        prompt_parts.append(
            f"\n## Restricted paths\n"
            f"The following paths are blocked from read/write access: "
            f"{', '.join(denied_paths)}"
        )

    final_prompt = "\n\n".join(p for p in prompt_parts if p)

    # ── Backend ────────────────────────────────────────────────────────
    backend = FilesystemBackend(root_dir=project_dir)

    # ── Build agent ────────────────────────────────────────────────────
    logger.info(
        "Creating agent for %s (model=%s, excluded=%s, deny_cmds=%d)",
        project_dir, effective_model, excluded_tools, len(deny_prefixes),
    )

    agent = create_deep_agent(
        model=effective_model,
        system_prompt=final_prompt,
        tools=agent_tools,
        backend=backend,
        middleware=[],
    )

    # Attach metadata so the CLI can read them
    agent._clai_config = cfg           # type: ignore[attr-defined]
    agent._clai_model = effective_model  # type: ignore[attr-defined]

    return agent
