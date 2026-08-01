# chatlib

A simple chat client library built on [Textual](https://textual.textualize.io/).

## Features

- Send messages and commands (starting with `/`)
- Receive messages and link replies to sent messages
- Render Markdown with syntax highlighting for code blocks
- Simple in‑memory message history

## Installation

```bash
uv pip install -e .
```

or from PyPI (if published):

```bash
uv add chatlib
```

## Usage

```python
from chatlib import ChatApp

app = ChatApp()
app.run()
```

See `chatlib/chat_app.py` for the full API.

## License

MIT