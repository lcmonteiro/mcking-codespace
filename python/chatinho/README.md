# chatinho

A simple, extensible chat client library built on [Textual](https://textual.textualize.io/) for terminal-based chat applications.

## Features

- **Message Display**: Render messages with Markdown support and syntax highlighting for code blocks.
- **Command Handling**: Built-in support for commands prefixed with `/` (e.g., `/help`, `/code`).
- **Reply Threading**: Click any message to set it as the reply target; outgoing messages can be tagged as replies.
- **In-Memory History**: Full message history retained; sliding window limits rendered messages for performance.
- **Transport Agnostic**: Library does not dictate how messages are sent/received—use `send_message`, `send_command`, and `receive_message` to hook into any backend (WebSocket, HTTP, custom protocols, etc.).
- **Customizable UI**: Clean, readable theme with clear visual distinction between sent and received messages.
- **Extensible Design**: Override lifecycle hooks (`on_command`, `on_message_sent`, `on_message_received`) to inject custom logic.

## Installation

### Prerequisites

- Python 3.12 or higher
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### From Source (Development)

```bash
# Clone the repository
git clone https://github.com/lcmonteiro/mcking-codespace.git
cd mcking-codespace/python/chatinho

# Setup virtual environment and install dependencies
bash setup.sh   # creates .venv and installs textual, etc.

# Activate if desired
source .venv/bin/activate
```

### Using uv (Recommended)

```bash
uv pip install -e .
```

### Using pip

```bash
pip install -e .
```

## Quick Start

Run the demo to see chatinho in action:

```bash
bash run.sh
```

Or directly:

```bash
python examples/demo.py
```

More demos live in the [`examples/`](examples/) folder.

### Running on Termux (Android)

If the on-screen keyboard doesn't appear when tapping the input box:

- **Volume Down + Q** — shows/hides the virtual keyboard inside any TUI
- Tapping the terminal screen also usually pops it up
- Make sure you have a hardware keyboard button mapped in Termux settings
  (`Volume Down` as the default key works best with TUIs)

### Customising the theme

You can create a custom :class:`~chatinho.chat_style.ChatStyle` and pass it to ``ChatApp``:

```python
from chatinho import ChatApp, ChatStyle

# Example: a greenish theme
custom_style = ChatStyle(
    accent="#00ff88",
    sent_bubble_bg="#004422",
    received_header="#88ffcc",
)

class MyChatApp(ChatApp):
    def on_command(self, command: str) -> None:
        if command == "hello":
            self.receive_message("Hello from the bot!")
        else:
            self.receive_message(f"Unknown command: {command}")

if __name__ == "__main__":
    MyChatApp(style=custom_style).run()
```

### Embedding in Your Own Application

```python
from chatinho import ChatApp

class MyChatApp(ChatApp):
    def on_command(self, command: str) -> None:
        # Handle custom commands
        if command == "hello":
            self.receive_message("Hello from the bot!")
        elif command == "time":
            from datetime import datetime
            self.receive_message(f"Current time: {datetime.now().strftime('%H:%M:%S')}")
        else:
            self.receive_message(f"Unknown command: {command}")

    def on_message_sent(self, msg) -> None:
        # Example: send message to a webhook or websocket
        print(f"[OUT] {msg.text}")

    def on_message_received(self, msg) -> None:
        # Example: log incoming messages
        print(f"[IN]  {msg.text}")

if __name__ == "__main__":
    MyChatApp().run()
```

## API Reference

### `ChatApp`

Main application class. Subclass to customize behavior.

#### Constructor

```python
ChatApp(
    command_handler: Optional[Callable[[str], None]] = None,
    max_displayed: int = 100,
)
```

- `command_handler`: Optional function called when a command is received (if not overridden).
- `max_displayed`: Maximum number of messages to render in the viewport (older messages stay in history).

#### Lifecycle Hooks (Override in Subclass)

- `on_command(command: str) -> None`: Called when user sends a command (without the `/` prefix).
- `on_message_sent(msg: ChatMessage) -> None`: Called after sending a message (local echo).
- `on_message_received(msg: ChatMessage) -> None`: Called when a message is received from outside.

#### Public Methods

- `send_message(text: str, *, reply_to: Optional[str] = None) -> str`  
  Send a normal message. Returns the message ID. If `reply_to` is provided, the message is tagged as a reply.

- `send_command(command: str) -> str`  
  Send a command (without the leading `/`). Returns the message ID.

- `receive_message(text: str, *, reply_to: Optional[str] = None) -> str`  
  Inject an incoming message (e.g., from a network callback). Returns the message ID.

- `get_replies(msg_id: str) -> List[str]`  
  Get list of message IDs that reply to the given message.

- `send_pending_reply(text: str) -> Optional[str]`  
  Send `text` as a reply to the currently selected message (via click). Clears the selection. Returns the sent message ID, or `None` if no target selected.

#### Internal Details

Messages are stored as `ChatMessage` dataclass instances:

```python
@dataclass
class ChatMessage:
    id: str
    text: str
    timestamp: datetime = field(default_factory=datetime.now)
    is_command: bool = False
    reply_to: Optional[str] = None
    is_sent_by_me: bool = True
```

## How It Works

1. **UI Layer**: Built with Textual, providing a responsive terminal interface.
2. **Message Flow**:  
   - User types and presses Enter → `on_input_submitted` → either `send_message` or `send_command`.
   - Outgoing messages are added to history and rendered via `_add_message` → `_refresh_chat_log`.
   - Incoming messages are injected via `receive_message` (e.g., from a background thread handling WebSocket events).
3. **Reply Threading**: Clicking a message sets `_reply_target`. Subsequent `send_message` uses that target unless cleared.
4. **Performance**: Only the last `max_displayed` messages are rendered as widgets; older messages remain in `self.messages` for history and threading.

## Example: Connecting to a WebSocket

```python
import asyncio
import websockets
from chatinho import ChatApp

class WSChatApp(ChatApp):
    async def on_mount(self) -> None:
        await super().on_mount()
        self.websocket = await websockets.connect("ws://example.com/chat")
        self.run_worker(self._listen_ws)

    async def _listen_ws(self):
        async for message in self.websocket:
            # Assume incoming JSON: {"text": "...", "reply_to": "msg-123"}
            data = eval(message)  # In production, use json.loads safely
            self.receive_message(data["text"], reply_to=data.get("reply_to"))

    def on_message_sent(self, msg):
        # Outgoing: send to server
        asyncio.create_task(self.websocket.send(
            f'{{"text": "{msg.text}", "reply_to": {msg.reply_to or "null"}}'
        ))

if __name__ == "__main__":
    WSChatApp().run()
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Textual](https://textual.textualize.io/) for the excellent TUI framework.
- Built as part of the [mcking-codespace](https://github.com/lcmonteiro/mcking-codespace) collection.

---
*Happy chatting!*