"""
llm-proxy — LLM Proxy administration CLI.

Usage::

    # --- Provider keys (with budget) ---
    llm-proxy provider add openai sk-xxx --owner-label alice --priority 10 \
        --budget-type monthly --budget 1000000
    llm-proxy provider budget <provider-id> --budget 2000000
    llm-proxy provider budget <provider-id> --budget-type one_time
    llm-proxy provider list
    llm-proxy provider toggle <id>
    llm-proxy provider remove <id>

    # --- Wallets (no direct budget — balance comes from linked providers) ---
    llm-proxy wallet create my-wallet alice --valid-until 2027-01-01
        --allowed-models coding,chat
    llm-proxy wallet list
    llm-proxy wallet get <id>
    llm-proxy wallet revoke <id>
    llm-proxy wallet add-provider <wallet-id> --provider <provider-id> --credit 500000
    llm-proxy wallet remove-provider <wallet-id> --provider <provider-id>
    llm-proxy wallet list-providers <wallet-id>

    # --- Deprecated token aliases ---
    llm-proxy token create ...   # → wallet create (ignores budget options)
    llm-proxy token list ...     # → wallet list
    llm-proxy token get ...      # → wallet get
    llm-proxy token revoke ...   # → wallet revoke
    # token budget is GONE (error with explanation)

    # --- Model mappings ---
    llm-proxy mapping add coding openai gpt-4o --priority 10
    llm-proxy mapping list
    llm-proxy mapping toggle <id>
    llm-proxy mapping remove <id>

    # --- Usage & stats ---
    llm-proxy usage [--limit 20] [--wallet-id <id>] [--abstraction coding]
    llm-proxy stats

    # --- Config ---
    llm-proxy config set proxy_url http://localhost:8000
    llm-proxy config show

    # --- Serve ---
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


def _deprecated(use_instead: str) -> None:
    """Print a deprecation warning to stderr."""
    click.echo(f"Warning: 'token' is deprecated, use '{use_instead}' instead.", err=True)


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
@click.option("--budget-type", type=click.Choice(["one_time", "monthly"]), required=True, help="Credit type: one_time (fixed) or monthly (resets each cycle)")
@click.option("--budget", type=int, required=True, help="Credit amount for this provider")
def provider_add(provider_name: str, api_key: str, owner_label: str, priority: int, budget_type: str, budget: int) -> None:
    """Register a new provider API key with budget configuration."""
    try:
        result = _client().provider_add(provider_name, api_key, owner_label=owner_label, priority=priority, budget_type=budget_type, budget_amount=budget)
    except Exception as exc:
        _abort(str(exc))
    click.echo(f"✓ Provider key registered:")
    click.echo(f"  ID           : {result['id']}")
    click.echo(f"  Provider     : {result['provider']}")
    click.echo(f"  Owner label  : {result['owner_label']}")
    click.echo(f"  Priority     : {result['priority']}")
    click.echo(f"  Budget type  : {result.get('budget_type', '—')}")
    click.echo(f"  Budget       : {result.get('budget_amount', '—'):,}")
    click.echo(f"  Active       : {result['is_active']}")


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


@provider.command("budget")
@click.argument("provider_id")
@click.option("--budget", type=int, help="New budget amount")
@click.option("--budget-type", type=click.Choice(["one_time", "monthly"]), help="New budget type")
def provider_budget(provider_id: str, budget: Optional[int], budget_type: Optional[str]) -> None:
    """Update provider budget configuration (amount or type)."""
    if budget is None and budget_type is None:
        _abort("Either --budget or --budget-type must be specified")
    try:
        result = _client().provider_budget(provider_id, budget_amount=budget, budget_type=budget_type)
    except Exception as exc:
        _abort(str(exc))
    click.echo(f"✓ Provider {provider_id[:8]} updated:")
    if budget is not None:
        click.echo(f"  Budget amount: {result.get('budget_amount', '—'):,}")
    if budget_type is not None:
        click.echo(f"  Budget type  : {result.get('budget_type', '—')}")


# ====================================================================================================
# Wallet commands (formerly access tokens)
# ====================================================================================================


@cli.group()
def wallet() -> None:
    """Manage wallets (formerly access tokens)."""


@wallet.command("create")
@click.argument("label")
@click.argument("owner")
@click.option("--valid-until", help="Expiry date (ISO-8601, e.g. 2026-12-31)")
@click.option("--allowed-models", help="Comma-separated abstractions (e.g. coding,chat)")
def wallet_create(
    label: str,
    owner: str,
    valid_until: Optional[str],
    allowed_models: Optional[str],
) -> None:
    """Create a new wallet."""
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
        result = _client().wallet_create(
            label=label,
            owner=owner,
            valid_until=parsed_until,
            allowed_models=parsed_models,
        )
    except Exception as exc:
        _abort(str(exc))

    click.echo("✓ Wallet created!")
    click.echo(f"  ID         : {result['wallet_id']}")
    click.echo(f"  Label      : {result['label']}")
    click.echo(f"  Owner      : {result['owner']}")
    click.echo(f"  Expiry     : {result.get('valid_until', 'never')}")
    click.echo(f"  Allowed    : {', '.join(result['allowed_models']) if result.get('allowed_models') else 'all'}")
    click.echo(f"  Status     : {result['status']}")
    click.echo(f"  Created    : {result['created_at']}")
    click.echo(f"  Balance    : {result.get('balance', 0):,} tokens")


@wallet.command("list")
@click.option("--owner", help="Filter by owner")
def wallet_list(owner: Optional[str]) -> None:
    """List wallets."""
    try:
        wallets = _client().wallet_list(owner=owner)
    except Exception as exc:
        _abort(str(exc))
    if not wallets:
        click.echo("No wallets.")
        return
    rows = []
    for w in wallets:
        rows.append([
            w["id"][:8],
            w["label"],
            w["owner"],
            f'{w.get("balance", 0):,}',
            w["status"],
        ])
    click.echo(_fmt_table(
        ["ID", "Label", "Owner", "Balance", "Status"],
        rows,
    ))


@wallet.command("get")
@click.argument("wallet_id")
def wallet_get(wallet_id: str) -> None:
    """Show details for a single wallet."""
    try:
        w = _client().wallet_get(wallet_id)
    except Exception as exc:
        _abort(str(exc))
    click.echo(f"  ID           : {w['id']}")
    click.echo(f"  Label        : {w['label']}")
    click.echo(f"  Owner        : {w['owner']}")
    click.echo(f"  Expiry       : {w.get('valid_until', 'never')}")
    click.echo(f"  Allowed      : {', '.join(w['allowed_models']) if w.get('allowed_models') else 'all'}")
    click.echo(f"  Status       : {w['status']}")
    click.echo(f"  Created      : {w['created_at']}")
    click.echo(f"  Balance      : {w.get('balance', 0):,} tokens")


@wallet.command("revoke")
@click.argument("wallet_id")
def wallet_revoke(wallet_id: str) -> None:
    """Revoke a wallet."""
    try:
        _client().wallet_revoke(wallet_id)
    except Exception as exc:
        _abort(str(exc))
    click.echo(f"✓ Wallet {wallet_id[:8]} revoked.")


@wallet.command("add-provider")
@click.argument("wallet_id")
@click.option("--provider", required=True, help="Provider ID")
@click.option("--credit", required=True, type=int, help="Credit amount to add from provider")
def wallet_add_provider(wallet_id: str, provider: str, credit: int) -> None:
    """Link a provider to wallet and transfer credit."""
    try:
        result = _client().wallet_add_provider(wallet_id, provider_id=provider, credit_amount=credit)
    except Exception as exc:
        _abort(str(exc))
    click.echo(f"✓ Added provider {provider[:8]} to wallet {wallet_id[:8]}:")
    click.echo(f"  Credit transferred: {credit:,} tokens")
    click.echo(f"  Wallet new balance: {result.get('new_balance', 0):,} tokens")
    click.echo(f"  Provider remaining: {result.get('provider_remaining', 0):,} tokens")


@wallet.command("remove-provider")
@click.argument("wallet_id")
@click.option("--provider", required=True, help="Provider ID")
def wallet_remove_provider(wallet_id: str, provider: str) -> None:
    """Unlink a provider from wallet (does not refund credit)."""
    try:
        _client().wallet_remove_provider(wallet_id, provider_id=provider)
    except Exception as exc:
        _abort(str(exc))
    click.echo(f"✓ Removed provider {provider[:8]} from wallet {wallet_id[:8]} (credit not refunded).")


@wallet.command("list-providers")
@click.argument("wallet_id")
def wallet_list_providers(wallet_id: str) -> None:
    """List providers linked to a wallet."""
    try:
        links = _client().wallet_list_providers(wallet_id)
    except Exception as exc:
        _abort(str(exc))
    if not links:
        click.echo("No providers linked to this wallet.")
        return
    rows = []
    for l in links:
        rows.append([
            l["provider_id"][:8],
            l["provider_name"],
            f'{l["credited_amount"]:,}',
            l["linked_at"],
        ])
    click.echo(_fmt_table(
        ["Provider ID", "Provider", "Credited", "Linked At"],
        rows,
    ))


# ====================================================================================================
# Deprecated token commands (aliases for wallet)
# ====================================================================================================


@cli.group()
def token() -> None:
    """Manage proxy access tokens (DEPRECATED — use wallet)."""


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
    """Create a new access token (DEPRECATED)."""
    _deprecated("wallet create")
    # Note: Budget options are ignored in wallet model
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
        result = _client().wallet_create(
            label=label,
            owner=owner,
            valid_until=parsed_until,
            allowed_models=parsed_models,
        )
    except Exception as exc:
        _abort(str(exc))

    click.echo("✓ Access token created (via wallet)!")
    click.echo(f"  Raw token  : {result.get('raw_token', 'N/A — wallet does not expose raw token')}")
    click.echo(f"  ID         : {result['wallet_id']}")
    click.echo(f"  Label      : {result['label']}")
    click.echo(f"  Owner      : {result['owner']}")
    click.echo(f"  Expiry     : {result.get('valid_until', 'never')}")
    click.echo(f"  Allowed    : {', '.join(result['allowed_models']) if result.get('allowed_models') else 'all'}")
    click.echo(f"  Status     : {result['status']}")
    click.echo(f"  Created    : {result['created_at']}")
    click.echo(f"  Balance    : {result.get('balance', 0):,} tokens")


@token.command("list")
@click.option("--owner", help="Filter by owner")
def token_list(owner: Optional[str]) -> None:
    """List access tokens (DEPRECATED)."""
    _deprecated("wallet list")
    try:
        wallets = _client().wallet_list(owner=owner)
    except Exception as exc:
        _abort(str(exc))
    if not wallets:
        click.echo("No access tokens.")
        return
    rows = []
    for w in wallets:
        rows.append([
            w["id"][:8],
            w["label"],
            w["owner"],
            f'{w.get("balance", 0):,}',
            w["status"],
        ])
    click.echo(_fmt_table(
        ["ID", "Label", "Owner", "Balance", "Status"],
        rows,
    ))


@token.command("get")
@click.argument("token_id")
def token_get(token_id: str) -> None:
    """Show details for a single access token (DEPRECATED)."""
    _deprecated("wallet get")
    try:
        w = _client().wallet_get(token_id)
    except Exception as exc:
        _abort(str(exc))
    click.echo(f"  ID           : {w['id']}")
    click.echo(f"  Label        : {w['label']}")
    click.echo(f"  Owner        : {w['owner']}")
    click.echo(f"  Expiry       : {w.get('valid_until', 'never')}")
    click.echo(f"  Allowed      : {', '.join(w['allowed_models']) if w.get('allowed_models') else 'all'}")
    click.echo(f"  Status       : {w['status']}")
    click.echo(f"  Created      : {w['created_at']}")
    click.echo(f"  Balance      : {w.get('balance', 0):,} tokens")


@token.command("revoke")
@click.argument("token_id")
def token_revoke(token_id: str) -> None:
    """Revoke an access token (DEPRECATED)."""
    _deprecated("wallet revoke")
    try:
        _client().wallet_revoke(token_id)
    except Exception as exc:
        _abort(str(exc))
    click.echo(f"✓ Token {token_id[:8]} revoked (via wallet).")


@token.command("budget")
@click.argument("token_id")
@click.option("--token-budget", required=True, type=int, help="New token budget")
def token_budget_cmd(token_id: str, token_budget: int) -> None:
    """Update the token budget (DEPRECATED — wallets derive balance from providers)."""
    _deprecated("wallet model does not support direct budget updates")
    _abort("Error: token budget command is removed. Wallet balance is derived from linked providers. Use 'wallet add-provider' to increase balance.")


# ====================================================================================================
# Model mapping commands
# ====================================================================================================


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
@click.option("--wallet-id", help="Filter by wallet ID")
@click.option("--provider", "provider_filter", help="Filter by provider")
@click.option("--abstraction", help="Filter by abstraction")
@click.option("--limit", default=20, type=int, help="Max entries (max 500)")
def usage(wallet_id: Optional[str], provider_filter: Optional[str], abstraction: Optional[str], limit: int) -> None:
    """Query the usage / audit log."""
    try:
        entries = _client().usage(wallet_id=wallet_id, provider=provider_filter, abstraction=abstraction, limit=limit)
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
