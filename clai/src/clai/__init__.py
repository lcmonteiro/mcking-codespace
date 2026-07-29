"""
clai — CLI AI: Code development agent powered by LangGraph Deep Agents.

Usage:
    clai <directory> [--model MODEL] [--task TASK]
    clai <directory>                        # interactive session
    clai <directory> --task "add tests"     # one-shot task
"""

from clai.cli import main

__all__ = ["main"]
