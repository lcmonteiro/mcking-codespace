# clai — CLI AI: Code Development Agent

**clai** (pronounced "clay") is a CLI tool that turns any project directory into an
AI-powered coding assistant. It uses **LangGraph Deep Agents** under the hood.

## Quick start

```bash
# Install
cd clai
uv sync

# Interactive mode — cd into a project and run:
clai /path/to/project

# One-shot mode — run a single task:
clai /path/to/project --task "Add type hints to src/"
```

## Features

- **Interactive REPL** — chat with the agent about your codebase
- **Filesystem access** — read, write, edit files in the project
- **Shell commands** — run build, test, lint from inside the agent
- **Git awareness** — status, diff, log tools
- **Sub-agents** — delegate complex sub-tasks automatically
- **Todo planning** — agent breaks down multi-step tasks

## Usage

```
Usage: clai [OPTIONS] [DIRECTORY]

Options:
  -m, --model TEXT   Model in 'provider:model' format  [default: anthropic:claude-sonnet-4-6]
  -t, --task TEXT    One-shot task prompt (omit for interactive session)
  --max-turns INT    Max agent turns (interactive mode)  [default: 50]
  -h, --help         Show this help
```

## Supported models

Any model that supports tool calling:

| Provider        | Example string                          |
|-----------------|-----------------------------------------|
| Anthropic       | `anthropic:claude-sonnet-4-6`           |
| OpenAI          | `openai:gpt-5.5`                        |
| Google          | `google_genai:gemini-3.6-flash`         |
| OpenRouter      | `openrouter:z-ai/glm-5.2`               |
| Ollama (local)  | `ollama:qwen2.5-coder`                  |

## Architecture

```
clai/
├── pyproject.toml       — Python project + entry point
└── src/clai/
    ├── __init__.py
    ├── cli.py           — Click CLI (interactive + one-shot)
    ├── agent.py         — Deep Agent factory (create_coding_agent)
    └── tools.py         — Custom code-dev tools (git, run, lint, ls)
```

The agent uses:
- `FilesystemBackend` pointed at the target directory
- Built-in filesystem tools (read, write, edit, ls, glob, grep, execute)
- `TodoListMiddleware` for planning
- `SubAgentMiddleware` for task delegation
