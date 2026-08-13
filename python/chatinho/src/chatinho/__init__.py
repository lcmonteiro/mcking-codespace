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

Persist history by declaring a connector on your subclass — instantiated
lazily, once per app instance:

    >>> from chatinho import ChatApp, JsonlHistoryConnector, connector
    >>> @connector(JsonlHistoryConnector, "chat.jsonl")
    ... class MyApp(ChatApp):
    ...     pass
"""

from .chat_app import ChatApp, ChatMessage
from .chat_style import ChatStyle
from .connectors import (
    CallbackTransportConnector,
    ConnectorArg,
    JsonlHistoryConnector,
    ReceiveCallback,
    connector,
    history_connector,
    is_history_connector,
    is_transport_connector,
    transport_connector,
)

__all__ = [
    "ChatApp",
    "ChatMessage",
    "ChatStyle",
    "ReceiveCallback",
    "ConnectorArg",
    "connector",
    "history_connector",
    "transport_connector",
    "is_history_connector",
    "is_transport_connector",
    "JsonlHistoryConnector",
    "CallbackTransportConnector",
]
