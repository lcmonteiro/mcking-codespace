# chatinho

A simple, extensible chat client library built on [Textual](https://textual.textualize.io/) for terminal-based chat applications.

## Features

- **Message Display**: Render messages with Markdown support and syntax highlighting for code blocks.
- **Command Handling**: Built-in support for commands prefixed with `/` (e.g., `/help`, `/code`).
- **Command Autocomplete**: Register known commands and get a dropdown of matching suggestions as the user types `/`; Tab/Enter completes, arrows navigate, Escape dismisses.
- **Reply Threading**: Click any message to set it as the reply target; outgoing messages can be tagged as replies.
- **In-Memory History**: Full message history retained; sliding window limits rendered messages for performance.
- **Transport Agnostic**: Library does not dictate how messages are sent/received—use `send_message`, `send_command`, and `receive_message` to hook into any backend (WebSocket, HTTP, custom protocols, etc.), or attach a `TransportConnector`/`HistoryConnector` (see [Connectors](#connectors)) to automate it.
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

The on-screen keyboard sometimes doesn't appear automatically when running
full-screen TUIs. There is no API command to force it (the old
`termux-keyboard` was never implemented in termux-api) — but these work:

- **Tap anywhere on the terminal screen** — Termux shows the keyboard on any
  tap (native gesture)
- **Navigation drawer**: swipe in from the left edge → press the `KEYBOARD`
  button → swipe back
- **Volume Down + Q** — toggles the keyboard, but only if "Volume keys" are
  enabled in Termux settings (it may not work with hardware keyboards)

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

### Command autocomplete

Pass a `commands` mapping (name → short description) to get a dropdown of
matching commands as the user types `/`:

```python
from chatinho import ChatApp

app = ChatApp(commands={
    "help": "Show available commands",
    "time": "Show the current time",
})
app.run()
```

- **Down/Up** move the highlight.
- **Tab** or **Enter** completes the input with the highlighted command (Enter does *not* submit while a suggestion is showing).
- **Escape** dismisses the popup without changing the input.
- Typing a command that isn't in `commands` still works as normal — the list is advisory only, it doesn't restrict what can be sent.

### Connectors

Connectors are pluggable backends, of two independent kinds:

- **`HistoryConnector`** — loads past messages when the app starts, and persists every message (sent or received) as it happens. Point it at a JSON file, a database, a REST API — whatever.
- **`TransportConnector`** — sends outgoing messages and delivers incoming ones into the running app. Point it at a WebSocket, MQTT, a message queue — whatever.

Each connector type owns its own lifecycle hooks — override them on your connector, not on `ChatApp`:

- `HistoryConnector.on_loaded(messages: List[ChatMessage]) -> None` — fires once, right after `load()` returns (even if it returned nothing).
- `HistoryConnector.on_saved(msg: ChatMessage) -> None` — fires after every message persisted via `save()` (not for messages loaded from history).
- `TransportConnector.on_started() -> None` — fires right after `start()`.
- `TransportConnector.on_stopped() -> None` — fires right after `stop()`.

Attach a connector to a running app with `app.connect_history(...)` / `app.connect_transport(...)` — works as a decorator on a zero-argument connector class, or as a plain call with an already-built instance:

```python
from chatinho import ChatApp, JsonlHistoryConnector, CallbackTransportConnector

app = ChatApp()

# HistoryConnector: a ready-to-use one is included (JSON Lines file).
app.connect_history(JsonlHistoryConnector("chat.jsonl"))

# TransportConnector: wrap your own send function; push() delivers
# incoming messages from wherever your network code receives them.
transport = CallbackTransportConnector(send_fn=lambda msg: my_socket.send(msg.text))
app.connect_transport(transport)

# ... from your own receive loop, whenever a message arrives:
# transport.push(incoming_text, reply_to=maybe_id)

app.run()
```

Or declare connectors up front with the `@connector(...)` class decorator on a `ChatApp` subclass — stack multiple applications, or pass several connectors to one call, to attach more than one:

```python
from chatinho import ChatApp, JsonlHistoryConnector, connector

@connector(JsonlHistoryConnector("chat.jsonl"))
class MyApp(ChatApp):
    pass

MyApp().run()  # history is attached to every instance automatically
```

A connector class doesn't need to subclass the ABC explicitly — mark a plain class with `@history_connector` / `@transport_connector` instead:

```python
from chatinho import HistoryConnector, history_connector

@history_connector
class Recorder:
    def load(self):
        return []  # e.g. query a database

    def save(self, message):
        print(f"[{message.id}] {message.text}")

    def on_loaded(self, messages):
        print(f"Loaded {len(messages)} past messages.")
```

`Recorder` above is a real `HistoryConnector` (`issubclass(Recorder, HistoryConnector)` is `True`) even though it never wrote `class Recorder(HistoryConnector):` — the decorator does that for you, so `on_loaded`/`on_saved` fall back to their no-op defaults if you don't override them.

- `HistoryConnector.load()` is called once, in `on_mount`, and its messages are inserted before anything is rendered — new ids keep counting up from the highest one seen, so sending a new message afterwards never collides.
- `HistoryConnector.save()` runs on the app's UI thread right after every message is added (sent or received) — keep it fast, or hand slow I/O off to a background thread/queue yourself.
- `TransportConnector.start()` is called in `on_mount` and `TransportConnector.stop()` in `on_unmount`; `send()` is called automatically for every message you send (not for ones you receive — no echo).
- Attaching a connector *after* the app is already mounted (e.g. from inside `on_mount` itself, or later) loads/starts it immediately instead of waiting.

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
    style: Optional[ChatStyle] = None,
    commands: Optional[Dict[str, str]] = None,
)
```

- `command_handler`: Optional function called when a command is received (if not overridden).
- `max_displayed`: Maximum number of messages to render in the viewport (older messages stay in history).
- `style`: Optional `ChatStyle` used to customise the theme programmatically (see [Customising the theme](#customising-the-theme)).
- `commands`: Optional mapping of command name (without `/`) to a short description, used to populate the autocomplete popup (see [Command autocomplete](#command-autocomplete)).

#### Lifecycle Hooks (Override in Subclass)

- `on_command(command: str) -> None`: Called when user sends a command (without the `/` prefix).
- `on_message_sent(msg: ChatMessage) -> None`: Called after sending a message (local echo).
- `on_message_received(msg: ChatMessage) -> None`: Called when a message is received from outside.

Connector lifecycle hooks (`on_loaded`, `on_saved`, `on_started`, `on_stopped`) belong to the connector classes themselves, not to `ChatApp` — see [Connectors](#connectors).

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

- `connect_history(connector: Union[HistoryConnector, Type[HistoryConnector]])`  
  Attaches a `HistoryConnector` (decorator-compatible; see [Connectors](#connectors)).

- `connect_transport(connector: Union[TransportConnector, Type[TransportConnector]])`  
  Attaches a `TransportConnector` (decorator-compatible; see [Connectors](#connectors)).

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
import json
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
            data = json.loads(message)
            self.receive_message(data["text"], reply_to=data.get("reply_to"))

    def on_message_sent(self, msg):
        # Outgoing: send to server
        payload = json.dumps({"text": msg.text, "reply_to": msg.reply_to})
        asyncio.create_task(self.websocket.send(payload))

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