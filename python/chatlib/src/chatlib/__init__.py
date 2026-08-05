"""ChatLib: a small chat client library built on Textual.

Enviar mensagens, enviar comandos, receber mensagens e receber respostas
(replies) a mensagens enviadas, com renderização de Markdown e syntax
highlighting para blocos de código.

Example:
    >>> from chatlib import ChatApp
    >>> app = ChatApp()
    >>> app.run()
"""

from .chat_app import ChatApp, ChatMessage

__all__ = ["ChatApp", "ChatMessage"]