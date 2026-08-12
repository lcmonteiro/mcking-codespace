"""Chatinho: a small chat client library built on Textual.

Send messages, send commands, receive messages and receive replies to
sent messages, with Markdown rendering and syntax highlighting for code
blocks.

Example:
    >>> from chatinho import ChatApp
    >>> app = ChatApp()
    >>> app.run()

Customise the theme programmatically:

    >>> from chatinho import ChatApp, ChatStyle
    >>> app = ChatApp(style=ChatStyle(accent="#ff5733"))

Persist history and hook up a live transport with connectors:

    >>> from chatinho import ChatApp, JsonlHistoryConnector
    >>> app = ChatApp()
    >>> app.connect_history(JsonlHistoryConnector("chat.jsonl"))
"""

from .chat_app import ChatApp, ChatMessage
from .chat_style import ChatStyle
from .connectors import (
    CallbackTransportConnector,
    HistoryConnector,
    JsonlHistoryConnector,
    TransportConnector,
)

__all__ = [
    "ChatApp",
    "ChatMessage",
    "ChatStyle",
    "HistoryConnector",
    "TransportConnector",
    "JsonlHistoryConnector",
    "CallbackTransportConnector",
]
