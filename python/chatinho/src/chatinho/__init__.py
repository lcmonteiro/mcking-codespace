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
"""

from .chat_app import ChatApp, ChatMessage
from .chat_style import ChatStyle

__all__ = ["ChatApp", "ChatMessage", "ChatStyle"]
