"""Custom code-development tools for the clai agent."""

import os
import subprocess
from pathlib import Path
from typing import Optional


def run_command(
    command: str,
    cwd: Optional[str] = None,
    timeout: int = 60,
) -> str:
    """Run a shell command in the project directory and return stdout + stderr.

    Use this for running linters, tests, builds, git operations, or any
    command-line tool relevant to the project.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd or os.getcwd(),
            timeout=timeout,
        )
        output = result.stdout
        if result.stderr:
            output += f"\n--- stderr ---\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n--- exit code: {result.returncode} ---"
        return output
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s: {command}"
    except Exception as e:
        return f"Error running command: {e}"


def make_run_command(
    deny_prefixes: Optional[list[str]] = None,
    allow_prefixes: Optional[list[str]] = None,
) -> callable:
    """Factory: return a *run_command* variant that checks command safety.

    Parameters
    ----------
    deny_prefixes :
        Commands starting with any of these strings are blocked.
    allow_prefixes :
        If non-empty, *only* commands starting with one of these are allowed
        (overrides deny_prefixes).
    """
    denied = deny_prefixes or []
    allowed = allow_prefixes or []

    def safe_run_command(
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 60,
    ) -> str:
        cmd_stripped = command.strip()

        # Allowlist takes precedence
        if allowed:
            if not any(cmd_stripped.startswith(p) for p in allowed):
                return (
                    f"[BLOCKED] Command not in allowlist.\n"
                    f"  command: {cmd_stripped}\n"
                    f"  allowed prefixes: {allowed}"
                )
        else:
            # Denylist check
            for prefix in denied:
                if cmd_stripped.startswith(prefix):
                    return (
                        f"[BLOCKED] Command matches denied prefix.\n"
                        f"  command: {cmd_stripped}\n"
                        f"  denied prefix: {prefix!r}"
                    )

        return run_command(command, cwd=cwd, timeout=timeout)

    safe_run_command.__name__ = "run_command"
    safe_run_command.__doc__ = run_command.__doc__
    return safe_run_command


def git_status(cwd: Optional[str] = None) -> str:
    """Show the current git status — changed, staged, untracked files."""
    return run_command("git status --short", cwd)


def git_diff(cwd: Optional[str] = None) -> str:
    """Show unstaged diff of all changed files."""
    return run_command("git diff", cwd)


def git_log(limit: int = 10, cwd: Optional[str] = None) -> str:
    """Show recent commit history."""
    return run_command(f"git log --oneline --max-count={limit}", cwd)


def list_directory(path: str = ".", cwd: Optional[str] = None) -> str:
    """List files and directories recursively with size info.

    Shows a tree-like view of the project structure.
    """
    base = Path(cwd or os.getcwd()) / path
    if not base.exists():
        return f"Path does not exist: {base}"
    if base.is_file():
        size = base.stat().st_size
        return f"{base.name} ({size:,} bytes)"

    lines = []
    for p in sorted(base.rglob("*")):
        if any(part.startswith(".") for part in p.parts):
            continue
        if p.name.startswith("__pycache__"):
            continue
        rel = p.relative_to(base)
        if p.is_dir():
            lines.append(f"  {rel}/")
        else:
            size = p.stat().st_size
            lines.append(f"  {rel}  ({size:,} bytes)")
    return "\n".join(lines) if lines else "(empty directory)"


def py_compile_check(cwd: Optional[str] = None) -> str:
    """Run py_compile on all .py files to catch syntax errors quickly."""
    import py_compile as pyc

    base = Path(cwd or os.getcwd())
    errors = []
    for pyfile in base.rglob("*.py"):
        if any(part.startswith(".") for part in pyfile.parts):
            continue
        if "venv" in pyfile.parts or ".venv" in pyfile.parts or "__pycache__" in pyfile.parts:
            continue
        try:
            pyc.compile(str(pyfile), doraise=True)
        except pyc.PyCompileError as e:
            errors.append(f"  {pyfile.relative_to(base)}: {e}")
    if errors:
        return "Syntax errors:\n" + "\n".join(errors)
    return "All Python files compile OK."
