"""Connectors: pluggable backends for chatinho.

Two independent connector types, matching the two separate concerns of
a chat transport:

- ``HistoryConnector`` — loads past messages when the app starts, and
  persists every message (sent or received) as it happens. Point one
  at a JSON file, SQLite, a REST API, whatever.
- ``TransportConnector`` — sends outgoing messages and delivers
  incoming ones into the running app. Point one at a WebSocket, MQTT,
  a message queue, whatever.

Attach a connector with ``app.connect_history(...)`` /
``app.connect_transport(...)``. Both work either as a decorator on a
zero-argument connector class, or as a plain method call with an
already-built instance::

    @app.connect_history
    class History(JsonlHistoryConnector):
        def __init__(self):
            super().__init__("chat.jsonl")

    # or, when the connector needs constructor arguments:
    app.connect_history(JsonlHistoryConnector("chat.jsonl"))

This module also ships one ready-to-use implementation of each type —
``JsonlHistoryConnector`` and ``CallbackTransportConnector`` — that
double as reference implementations for your own connectors.
"""

import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable, List, Optional, Union

if TYPE_CHECKING:
    from .chat_app import ChatMessage

# Called by a TransportConnector for every message it receives from the
# outside world: (text, reply_to). Safe to call from any thread.
ReceiveCallback = Callable[[str, Optional[str]], None]


class HistoryConnector(ABC):
    """Loads past messages on startup and persists new ones as they happen."""

    @abstractmethod
    def load(self) -> List["ChatMessage"]:
        """Returns past messages, oldest first."""

    @abstractmethod
    def save(self, message: "ChatMessage") -> None:
        """Persists a single message (sent or received).

        Called synchronously on the app's UI thread right after the
        message is added — keep this fast, or hand slow I/O off to a
        background thread/queue yourself.
        """


class TransportConnector(ABC):
    """Sends outgoing messages and delivers incoming ones."""

    @abstractmethod
    def start(self, on_receive: ReceiveCallback) -> None:
        """Begin listening for incoming messages.

        Call ``on_receive(text, reply_to)`` for each one you get from
        the outside world — safe to call from any thread, it is
        marshalled onto the app's UI thread automatically.
        """

    @abstractmethod
    def send(self, message: "ChatMessage") -> None:
        """Send an outgoing message."""

    def stop(self) -> None:
        """Stop listening and release resources. Optional to override."""


class JsonlHistoryConnector(HistoryConnector):
    """Persists messages as JSON Lines (one JSON object per line) to a file.

    A minimal, dependency-free reference implementation — swap it for a
    database-backed connector if you need concurrent access or queries.
    """

    def __init__(self, path: Union[str, Path]) -> None:
        self._path = Path(path)

    def load(self) -> List["ChatMessage"]:
        from .chat_app import ChatMessage  # local import: chat_app -> connectors is the one-way edge

        if not self._path.exists():
            return []
        messages = []
        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                messages.append(
                    ChatMessage(
                        id=data["id"],
                        text=data["text"],
                        timestamp=datetime.fromisoformat(data["timestamp"]),
                        is_command=data["is_command"],
                        reply_to=data.get("reply_to"),
                        is_sent_by_me=data["is_sent_by_me"],
                    )
                )
        return messages

    def save(self, message: "ChatMessage") -> None:
        record = {
            "id": message.id,
            "text": message.text,
            "timestamp": message.timestamp.isoformat(),
            "is_command": message.is_command,
            "reply_to": message.reply_to,
            "is_sent_by_me": message.is_sent_by_me,
        }
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")


class CallbackTransportConnector(TransportConnector):
    """Transport backed by two plain callables — adapt this to any real
    backend (WebSocket, MQTT, a message queue, ...) without subclassing.

    Example::

        transport = CallbackTransportConnector(send_fn=lambda msg: ws.send(msg.text))
        app.connect_transport(transport)

        # From your own network callback, whenever a message arrives:
        transport.push("hello from the server")
    """

    def __init__(self, send_fn: Callable[["ChatMessage"], None]) -> None:
        self._send_fn = send_fn
        self._on_receive: Optional[ReceiveCallback] = None

    def start(self, on_receive: ReceiveCallback) -> None:
        self._on_receive = on_receive

    def send(self, message: "ChatMessage") -> None:
        self._send_fn(message)

    def push(self, text: str, reply_to: Optional[str] = None) -> None:
        """Delivers an incoming message into the app.

        Call this from your own network/callback code. Safe to call
        from any thread.
        """
        if self._on_receive is not None:
            self._on_receive(text, reply_to)

    def stop(self) -> None:
        self._on_receive = None
