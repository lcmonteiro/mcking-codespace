"""
llm-proxy — LLM Proxy administration CLI.

Usage::

    llm-proxy provider add openai sk-xxx --owner-label alice --priority 10
    llm-proxy provider list
    llm-proxy provider toggle <id>
    llm-proxy provider remove <id>

    llm-proxy token create my-token alice --budget-type fixed --token-budget 100000
    llm-proxy token list
    llm-proxy token get <id>
    llm-proxy token revoke <id>
    llm-proxy token budget <id> --token-budget 500000

    llm-proxy mapping add coding openai gpt-4o --priority 10
    llm-proxy mapping list
    llm-proxy mapping toggle <id>
    llm-proxy mapping remove <id>

    llm-proxy usage [--limit 20] [--abstraction coding]
    llm-proxy stats

    llm-proxy config set proxy_url http://localhost:8000
    llm-proxy config show

    llm-proxy serve status
    llm-proxy serve start [--port 8080] [--reload]
    llm-proxy serve stop
    llm-proxy serve restart
"""
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import click

from cli.client import AdminClient
from cli.config import set_key
from cli.config import show as cfg_show

# ====================================================================================================
# Helpers
# ====================================================================================================


def _client() -> AdminClient:
    """Return an ``AdminClient`` using local config."""
    return AdminClient()


def _fmt_table(headers: List[str], rows: List[List[str]]) -> str:
    """
    Format a simple aligned table.

    Args:
        headers: Column header strings.
        rows: List of cell-string rows.

    Returns:
        A monospaced table string.
    """
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    sep = "  "
    fmt = sep.join(f"{{:<{w}}}" for w in col_widths)

    lines: List[str] = []
    lines.append(fmt.format(*headers))
    lines.append(sep.join("-" * w for w in col_widths))
    for row in rows:
        lines.append(fmt.format(*row))
    return "\n".join(lines)


def _abort(msg: str, code: int = 1) -> None:
    """Print *msg* to stderr and exit with *code*."""
    click.echo(f"Error: {msg}", err=True)
    sys.exit(code)


# ====================================================================================================
# Config commands
# ====================================================================================================


@click.group()
def cli() -> None:
    """Manage the LLM Proxy — provider keys, access tokens, model mappings, and usage."""


@cli.group()
def config() -> None:
    """View or change local CLI configuration."""


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set a config value (proxy_url, admin_key)."""
    valid_keys = {"proxy_url", "admin_key"}
    if key not in valid_keys:
        _abort(f"Unknown config key '{key}'. Valid keys: {', '.join(sorted(valid_keys))}")
    set_key(key, value)
    click.echo(f"✓ {key} updated.")


@config.command("show")
def config_show() -> None:
    """Show current configuration."""
    data = cfg_show()
    for key, value in data.items():
        click.echo(f"{key}: {value}")


# ====================================================================================================
# Provider key commands
# ====================================================================================================


@cli.group()
def provider() -> None:
    """Manage provider API keys."""


@provider.command("add")
@click.argument("provider_name", metavar="PROVIDER")
@click.argument("api_key")
@click.option("--owner-label", default="default", help="Owner label (e.g. alice, team-ai)")
@click.option("--priority", default=0, type=int, help="Key priority (higher = preferred)")
def provider_add(provider_name: str, api_key: str, owner_label: str, priority: int) -> None:
    """Register a new provider API key."""
    try:
        result = _client().provider_add(provider_name, api_key, owner_label=owner_label, priority=priority)
    except Exception as exc:
        _abort(str(exc))
    click.echo(f"✓ Provider key registered:")
    click.echo(f"  ID          : {result['id']}")
    click.echo(f"  Provider    : {result['provider']}")
    click.echo(f"  Owner label : {result['owner_label']}")
    click.echo(f"  Priority    : {result['priority']}")
    click.echo(f"  Active      : {result['is_active']}")


@provider.command("list")
@click.option("--provider", "provider_filter", help="Filter by provider name")
def provider_list(provider_filter: Optional[str]) -> None:
    """List registered provider keys."""
    try:
        keys = _client().provider_list(provider=provider_filter)
    except Exception as exc:
        _abort(str(exc))
    if not keys:
        click.echo("No provider keys registered.")
        return
    rows = []
    for k in keys:
        active  = "✓" if k["is_active"] else "✗"
        monthly = f"{k['monthly_limit']:,}" if k.get("monthly_limit") else "—"
        rows.append([
            k["id"][:8],
            k["provider"],
            k["owner_label"],
            str(k["priority"]),
            active,
            f'{k["tokens_used"]:,}',
            monthly,
        ])
    click.echo(_fmt_table(
        ["ID", "Provider", "Owner", "Pri", "Active", "Tokens", "Monthly"],
        rows,
    ))


@provider.command("toggle")
@click.argument("key_id")
def provider_toggle(key_id: str) -> None:
    """Toggle a provider key on/off."""
    try:
        result = _client().provider_toggle(key_id)
    except Exception as exc:
        _abort(str(exc))
    state = "active" if result["is_active"] else "inactive"
    click.echo(f"✓ Provider key {key_id[:8]} is now {state}.")


@provider.command("remove")
@click.argument("key_id")
def provider_remove(key_id: str) -> None:
    """Delete a provider key."""
    try:
        _client().provider_remove(key_id)
    except Exception as exc:
        _abort(str(exc))
    click.echo(f"✓ Provider key {key_id[:8]} removed.")


# ====================================================================================================
# Access token commands
# ====================================================================================================


@cli.group()
def token() -> None:
    """Manage proxy access tokens."""


@token.command("create")
@click.argument("label")
@click.argument("owner")
@click.option("--budget-type", type=click.Choice(["fixed", "time_based", "unlimited"]), default="fixed")
@click.option("--token-budget", type=int, help="Max tokens (None = unlimited for fixed/unlimited)")
@click.option("--valid-until", help="Expiry date (ISO-8601, e.g. 2026-12-31)")
@click.option("--allowed-models", help="Comma-separated abstractions (e.g. coding,chat)")
@click.option("--refresh-period", type=click.Choice(["daily", "weekly", "monthly"]), help="Budget refresh schedule")
def token_create(
    label: str,
    owner: str,
    budget_type: str,
    token_budget: Optional[int],
    valid_until: Optional[str],
    allowed_models: Optional[str],
    refresh_period: Optional[str],
) -> None:
    """Create a new access token."""
    parsed_until: Optional[datetime] = None
    if valid_until:
        try:
            parsed_until = datetime.fromisoformat(valid_until)
        except ValueError:
            _abort(f"Invalid ISO-8601 date: {valid_until}")

    parsed_models: Optional[List[str]] = None
    if allowed_models:
        parsed_models = [m.strip() for m in allowed_models.split(",")]

    try:
        result = _client().token_create(
            label=label,
            owner=owner,
            budget_type=budget_type,
            token_budget=token_budget,
            valid_until=parsed_until,
            allowed_models=parsed_models,
            refresh_period=refresh_period,
        )
    except Exception as exc:
        _abort(str(exc))

    click.echo("✓ Access token created!")
    click.echo(f"  Raw token  : {result['raw_token']}")
    click.echo(f"  ID         : {result['token_id']}")
    click.echo(f"  Label      : {result['label']}")
    click.echo(f"  Owner      : {result['owner']}")
    click.echo(f"  Budget     : {result.get('budget_type', '—')} "
               f"({result.get('token_budget', 'unlimited')})")
    click.echo(f"  Expiry     : {result.get('valid_until', 'never')}")
    click.secho("  ⚠ Save the raw token now — it won't be shown again!", fg="yellow")


@token.command("list")
@click.option("--owner", help="Filter by owner")
def token_list(owner: Optional[str]) -> None:
    """List access tokens."""
    try:
        tokens = _client().token_list(owner=owner)
    except Exception as exc:
        _abort(str(exc))
    if not tokens:
        click.echo("No access tokens.")
        return
    rows = []
    for t in tokens:
        budget = f'{t["token_budget"]:,}' if t.get("token_budget") else "∞"
        rows.append([
            t["id"][:8],
            t["label"],
            t["owner"],
            t["budget_type"],
            budget,
            f'{t["tokens_used"]:,}',
            t["status"],
        ])
    click.echo(_fmt_table(
        ["ID", "Label", "Owner", "Type", "Budget", "Used", "Status"],
        rows,
    ))


@token.command("get")
@click.argument("token_id")
def token_get(token_id: str) -> None:
    """Show details for a single access token."""
    try:
        t = _client().token_get(token_id)
    except Exception as exc:
        _abort(str(exc))
    click.echo(f"  ID           : {t['id']}")
    click.echo(f"  Label        : {t['label']}")
    click.echo(f"  Owner        : {t['owner']}")
    click.echo(f"  Budget type  : {t['budget_type']}")
    click.echo(f"  Token budget : {t.get('token_budget', 'unlimited')}")
    click.echo(f"  Tokens used  : {t['tokens_used']:,}")
    click.echo(f"  Allowed      : {', '.join(t['allowed_models']) if t.get('allowed_models') else 'all'}")
    click.echo(f"  Status       : {t['status']}")
    click.echo(f"  Expires      : {t.get('valid_until', 'never')}")
    click.echo(f"  Refresh      : {t.get('refresh_period', '—')}")
    click.echo(f"  Created      : {t['created_at']}")


@token.command("revoke")
@click.argument("token_id")
def token_revoke(token_id: str) -> None:
    """Revoke an access token."""
    try:
        _client().token_revoke(token_id)
    except Exception as exc:
        _abort(str(exc))
    click.echo(f"✓ Token {token_id[:8]} revoked.")


@token.command("budget")
@click.argument("token_id")
@click.option("--token-budget", required=True, type=int, help="New token budget")
def token_budget_cmd(token_id: str, token_budget: int) -> None:
    """Update the token budget (reactivates if exhausted)."""
    try:
        result = _client().token_budget(token_id, token_budget)
    except Exception as exc:
        _abort(str(exc))
    click.echo(f"✓ Token {token_id[:8]} budget updated to {result['new_budget']:,}.")


# ====================================================================================================
# Model mapping commands
# ====================================================================================================


@cli.group()
def mapping() -> None:
    """Manage abstraction-to-model mappings."""


@mapping.command("add")
@click.argument("abstraction")
@click.argument("provider_name", metavar="PROVIDER")
@click.argument("model_name")
@click.option("--priority", default=0, type=int, help="Higher = tried first")
def mapping_add(abstraction: str, provider_name: str, model_name: str, priority: int) -> None:
    """Create a new abstraction-to-model mapping."""
    try:
        result = _client().mapping_add(abstraction, provider_name, model_name, priority=priority)
    except Exception as exc:
        _abort(str(exc))
    click.echo(f"✓ Mapping created:")
    click.echo(f"  ID          : {result['id']}")
    click.echo(f"  Abstraction : {result['abstraction']}")
    click.echo(f"  Provider    : {result['provider']}")
    click.echo(f"  Model       : {result['model_name']}")
    click.echo(f"  Priority    : {result['priority']}")


@mapping.command("list")
def mapping_list() -> None:
    """List all model mappings."""
    try:
        mappings = _client().mapping_list()
    except Exception as exc:
        _abort(str(exc))
    if not mappings:
        click.echo("No model mappings.")
        return
    rows = []
    for m in mappings:
        active = "✓" if m["is_active"] else "✗"
        rows.append([
            m["id"][:8],
            m["abstraction"],
            m["provider"],
            m["model_name"],
            str(m["priority"]),
            active,
        ])
    click.echo(_fmt_table(
        ["ID", "Abstraction", "Provider", "Model", "Pri", "Active"],
        rows,
    ))


@mapping.command("toggle")
@click.argument("mapping_id")
def mapping_toggle(mapping_id: str) -> None:
    """Toggle a mapping on/off."""
    try:
        result = _client().mapping_toggle(mapping_id)
    except Exception as exc:
        _abort(str(exc))
    state = "active" if result["is_active"] else "inactive"
    click.echo(f"✓ Mapping {mapping_id[:8]} is now {state}.")


@mapping.command("remove")
@click.argument("mapping_id")
def mapping_remove(mapping_id: str) -> None:
    """Delete a model mapping."""
    try:
        _client().mapping_remove(mapping_id)
    except Exception as exc:
        _abort(str(exc))
    click.echo(f"✓ Mapping {mapping_id[:8]} removed.")


# ====================================================================================================
# Usage commands
# ====================================================================================================


@cli.command()
@click.option("--token-id", help="Filter by access token ID")
@click.option("--provider", "provider_filter", help="Filter by provider")
@click.option("--abstraction", help="Filter by abstraction")
@click.option("--limit", default=20, type=int, help="Max entries (max 500)")
def usage(token_id: Optional[str], provider_filter: Optional[str], abstraction: Optional[str], limit: int) -> None:
    """Query the usage / audit log."""
    try:
        entries = _client().usage(token_id=token_id, provider=provider_filter, abstraction=abstraction, limit=limit)
    except Exception as exc:
        _abort(str(exc))
    if not entries:
        click.echo("No usage data yet.")
        return
    rows = []
    for e in entries:
        rows.append([
            e["id"][:8],
            e.get("abstraction", "—"),
            e.get("provider", "—"),
            e.get("model_name", "—")[:20],
            f'{e["total_tokens"]:,}',
            f'{e.get("latency_ms", "—")}ms' if e.get("latency_ms") else "—",
            e["status"],
        ])
    click.echo(_fmt_table(
        ["ID", "Abstraction", "Provider", "Model", "Tokens", "Latency", "Status"],
        rows,
    ))


@cli.command()
def stats() -> None:
    """Show aggregated usage per abstraction and provider."""
    try:
        data = _client().stats()
    except Exception as exc:
        _abort(str(exc))
    stats_list = data.get("stats", [])
    if not stats_list:
        click.echo("No stats yet.")
        return
    rows = []
    for s in stats_list:
        rows.append([
            s.get("abstraction", "—"),
            s.get("provider", "—"),
            str(s.get("requests", 0)),
            f'{s.get("total_tokens", 0):,}',
            f'{s.get("avg_latency_ms", 0):.0f}ms' if s.get("avg_latency_ms") else "—",
        ])
    click.echo(_fmt_table(
        ["Abstraction", "Provider", "Requests", "Tokens", "Avg Latency"],
        rows,
    ))


# ====================================================================================================
# Serve commands (manage the uvicorn process)
# ====================================================================================================


PROXY_DIR : Path = Path(__file__).resolve().parents[3]  # llm-proxy/
PID_DIR   : Path = Path.home() / ".llm-proxy"
PID_PATH  : Path = PID_DIR / "serve.pid"


@cli.group()
def serve() -> None:
    """Start, stop, or restart the LLM Proxy server."""


def _read_pid() -> Optional[int]:
    """
    Read the PID from the PID file.

    Returns:
        PID as int, or None if the file doesn't exist or is unparseable.
    """
    if not PID_PATH.exists():
        return None
    try:
        return int(PID_PATH.read_text().strip())
    except (ValueError, OSError):
        return None


def _write_pid(pid: int) -> None:
    """Write *pid* to the PID file, creating the directory if needed."""
    PID_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(pid))


def _remove_pid() -> None:
    """Remove the PID file if it exists."""
    if PID_PATH.exists():
        PID_PATH.unlink()


def _is_running(pid: int) -> bool:
    """
    Check whether a process with *pid* is alive.

    Args:
        pid: Process ID to check.

    Returns:
        True if the process exists, False otherwise.
    """
    try:
        os.kill(pid, 0)  # POSIX + Windows (no-op signal)
        return True
    except (OSError, PermissionError):
        return False


def _find_port() -> str:
    """Read the configured port from settings (or default to 8000)."""
    from cli.config import get as cfg_get

    url = cfg_get("proxy_url", "http://localhost:8000")
    # naive port extraction
    if ":" in url.split("://", 1)[-1]:
        return url.rsplit(":", 1)[-1].rstrip("/")
    return "8000"


@serve.command()
def status() -> None:
    """Show whether the proxy server is running."""
    pid = _read_pid()
    if pid is None or not _is_running(pid):
        click.echo("Proxy server is STOPPED.")
        return
    port = _find_port()
    click.echo(f"Proxy server is RUNNING (PID {pid}, port {port}).")


@serve.command()
@click.option("--port", default=None, type=int, help="Override the configured port")
@click.option("--reload/--no-reload", default=False, help="Enable hot-reload (dev mode)")
def start(port: Optional[int], reload: bool) -> None:
    """Start the LLM Proxy server (uvicorn) in the background."""
    pid = _read_pid()
    if pid is not None and _is_running(pid):
        click.echo(f"Proxy is already running (PID {pid}). Use 'llm-proxy serve restart'.")
        return

    click.echo("Starting LLM Proxy…")

    cmd = [sys.executable, "-m", "uvicorn", "main:app"]
    cmd += ["--host", "0.0.0.0"]
    cmd += ["--port", str(port)] if port else []
    if reload:
        cmd.append("--reload")

    kwargs: Dict[str, Any] = {
        "cwd": str(PROXY_DIR),
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(cmd, **kwargs)
    _write_pid(proc.pid)

    # brief wait to catch immediate failures
    time.sleep(1.0)
    if proc.poll() is not None:
        _remove_pid()
        _abort("Server exited immediately. Check the logs at the proxy directory.")

    click.echo(f"✓ Proxy started (PID {proc.pid}).")


@serve.command()
def stop() -> None:
    """Stop the running proxy server."""
    pid = _read_pid()
    if pid is None or not _is_running(pid):
        click.echo("Proxy is not running.")
        _remove_pid()
        return

    click.echo(f"Stopping proxy (PID {pid})…")
    try:
        os.kill(pid, signal.SIGTERM)
        # give it up to 5 seconds to shut down gracefully
        for _ in range(10):
            if not _is_running(pid):
                break
            time.sleep(0.5)
        else:
            os.kill(pid, signal.SIGKILL if hasattr(signal, "SIGKILL") else signal.SIGTERM)
    except (OSError, PermissionError) as exc:
        _abort(f"Failed to stop process {pid}: {exc}")

    _remove_pid()
    click.echo("✓ Proxy stopped.")


@serve.command()
@click.option("--port", default=None, type=int)
@click.option("--reload/--no-reload", default=False)
def restart(port: Optional[int], reload: bool) -> None:
    """Restart the proxy server (stop + start)."""
    # call stop logic inline (avoid duplicating the message)
    pid = _read_pid()
    if pid is not None and _is_running(pid):
        click.echo(f"Stopping proxy (PID {pid})…")
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(10):
                if not _is_running(pid):
                    break
                time.sleep(0.5)
        except (OSError, PermissionError):
            pass
        _remove_pid()
        click.echo("✓ Proxy stopped.")

    click.echo("Starting LLM Proxy…")
    cmd = [sys.executable, "-m", "uvicorn", "main:app"]
    cmd += ["--host", "0.0.0.0"]
    cmd += ["--port", str(port)] if port else []
    if reload:
        cmd.append("--reload")

    kwargs: Dict[str, Any] = {
        "cwd": str(PROXY_DIR),
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(cmd, **kwargs)
    _write_pid(proc.pid)
    time.sleep(1.0)
    if proc.poll() is not None:
        _remove_pid()
        _abort("Server exited immediately. Check the logs.")

    click.echo(f"✓ Proxy restarted (PID {proc.pid}).")
