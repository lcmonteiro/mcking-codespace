"""CLI entry point for *clai* — the code development agent."""

import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from clai.agent import create_coding_agent
from clai.models import format_provider_help, check_api_key

console = Console()
err_console = Console(stderr=True)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument(
    "directory",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True),
    default=".",
)
@click.option(
    "-m", "--model",
    default="anthropic:claude-sonnet-4-6",
    show_default=True,
    help="Model in 'provider:model' format (e.g. openai:gpt-5.5, google_genai:gemini-3.6-flash, ollama:llama3.1)\n"
         "Use 'clai --model-help' to see all supported providers.",
)
@click.option(
    "--model-help",
    is_flag=True,
    help="Show supported model providers and exit",
)
@click.option(
    "-t", "--task",
    default=None,
    help="One-shot task prompt (omit for interactive session)",
)
@click.option(
    "--max-turns",
    default=50,
    show_default=True,
    help="Max agent turns (interactive mode)",
    type=int,
)
def main(directory: str, model: str, model_help: bool, task: str | None, max_turns: int):
    """CLAI — Code development agent powered by LangGraph Deep Agents.

    Point it at a project directory and get an AI pair-programmer that can
    read, write, edit, search, run commands, and delegate sub-tasks.
    """
    if model_help:
        console.print(format_provider_help())
        sys.exit(0)

    project_dir = str(Path(directory).resolve())

    # ── Welcome ────────────────────────────────────────────────────────
    logo = """
╔════════════════════════════════════════╗
║   ██████╗██╗      █████╗ ██╗          ║
║  ██╔════╝██║     ██╔══██╗██║          ║
║  ██║     ██║     ███████║██║          ║
║  ██║     ██║     ██╔══██║██║          ║
║  ╚██████╗███████╗██║  ██║██║          ║
║   ╚═════╝╚══════╝╚═╝  ╚═╝╚═╝          ║
╚════════════════════════════════════════╝
    """
    console.print(logo, style="bold cyan")

    # Check API key early — warn but don't block
    key_warning = check_api_key(model)
    if key_warning:
        console.print(key_warning)

    console.print(Panel(
        f"[bold]Project:[/] {project_dir}\n"
        f"[bold]Model:[/]   {model}\n"
        f"[bold]Mode:[/]    {'one-shot' if task else 'interactive'}",
        title="clai",
        border_style="cyan",
    ))

    # ── Build agent ────────────────────────────────────────────────────
    console.print("\n[dim]Building agent...[/]")
    try:
        agent = create_coding_agent(
            project_dir=project_dir,
            model=model,
        )
    except Exception as e:
        err_console.print(f"[red]Failed to create agent:[/] {e}")
        sys.exit(1)

    if task:
        _run_one_shot(agent, task)
    else:
        _run_interactive(agent, project_dir, max_turns)


# ── One-shot mode ───────────────────────────────────────────────────────────

def _run_one_shot(agent, task: str):
    console.print(f"\n[bold yellow]Task:[/] {task}\n")
    try:
        result = agent.invoke({"messages": [{"role": "user", "content": task}]})
        final = result["messages"][-1].content
        if final:
            console.print(Markdown(final))
    except KeyboardInterrupt:
        err_console.print("\n[yellow]Interrupted.[/]")
        sys.exit(130)
    except Exception as e:
        err_console.print(f"[red]Agent error:[/] {e}")
        sys.exit(1)


# ── Interactive mode ────────────────────────────────────────────────────────

def _run_interactive(agent, project_dir: str, max_turns: int):
    """Simple read-eval-loop that streams agent responses turn by turn."""
    import readline  # noqa: F401 — better line editing

    history_file = os.path.expanduser("~/.clai_history")
    try:
        readline.read_history_file(history_file)
    except FileNotFoundError:
        pass

    readline.set_history_length(100)

    console.print(
        "\n[bold]Interactive mode.[/] Type your requests or "
        "[dim]/quit[/] to exit.\n"
    )

    messages: list = []
    turn = 0

    try:
        while turn < max_turns:
            try:
                prompt = input(f"\n[cyan]clai>[/] " if sys.stdout.isatty() else "")
            except EOFError:
                break

            if not prompt:
                continue
            cleaned = prompt.strip()
            if cleaned.lower() in ("/quit", "/exit", ":q"):
                break
            if cleaned.lower() == "/help":
                _show_help()
                continue
            if cleaned.startswith("/"):
                err_console.print(f"[yellow]Unknown command:[/] {cleaned}")
                continue

            readline.append_history_file(1, history_file)
            messages.append({"role": "user", "content": cleaned})

            try:
                result = agent.invoke({"messages": messages})
                # Update our message list from the agent's state
                messages = result["messages"]
                final = result["messages"][-1].content
                if final:
                    console.print()
                    console.print(Markdown(final))
            except Exception as e:
                err_console.print(f"\n[red]Agent error:[/] {e}")
                break

            turn += 1

        if turn >= max_turns:
            console.print(f"\n[dim]Reached max turns ({max_turns}). Exiting.[/]")

    except KeyboardInterrupt:
        console.print("\n[yellow]👋[/]")

    # Save history
    try:
        readline.write_history_file(history_file)
    except OSError:
        pass


def _show_help():
    """Print interactive-mode help."""
    console.print(Panel(
        "[bold]Commands[/]\n"
        "  /quit, /exit, :q   — Exit\n"
        "  /help              — This help\n"
        "\n"
        "[bold]Tips[/]\n"
        "  • Ask for specific changes: \"Add error handling to main.py\"\n"
        "  • Ask questions: \"What does this module do?\"\n"
        "  • Request refactoring: \"Extract the database layer\"\n"
        "  • Ask for tests: \"Write unit tests for src/parser.py\"\n"
        "  • Debug: \"Why is this test failing?\"\n"
        "\n"
        "[bold]Agent capabilities[/]\n"
        "  • Read / Write / Edit files\n"
        "  • Search (glob, grep)\n"
        "  • Run shell commands (build, test, lint)\n"
        "  • Git operations (status, diff, log)\n"
        "  • Delegate sub-tasks to sub-agents\n"
        "  • Todo-list planning\n",
        title="clai Help",
        border_style="green",
    ))


if __name__ == "__main__":
    main()
