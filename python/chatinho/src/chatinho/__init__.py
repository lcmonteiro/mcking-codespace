"""ChatLib: a small chat client library built on Textual.

Send messages, send commands, receive messages and receive replies to
sent messages, with Markdown rendering and syntax highlighting for code
blocks.

Example:
    >>> from chatinho import ChatApp
    >>> app = ChatApp()
    >>> app.run()
"""

from .chat_app import ChatApp, ChatMessage

__all__ = ["ChatApp", "ChatMessage"]