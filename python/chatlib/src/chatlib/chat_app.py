"""ChatApp: a minimal chat interface built with Textual.

Features:
- Message display with Markdown rendering and syntax highlighting for code blocks.
- Input field for sending messages and commands (starting with '/').
- Ability to tag outgoing messages with an ID and match incoming replies.
- Simple in-memory message history.

The library is transport-agnostic: call ``receive_message`` from a worker,
thread, or network callback to inject incoming messages.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

from textual.app import App, ComposeResult
from textual.containers import Container, ScrollableContainer, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Input, Markdown, Static

logger = logging.getLogger(__name__)

COMMAND_PREFIX : str = "/"


@dataclass
class ChatMessage:
    """Representa uma mensagem de chat."""

    id          : str
    text        : str
    timestamp   : datetime = field(default_factory=datetime.now)
    is_command  : bool = False
    reply_to    : Optional[str] = None
    is_sent_by_me : bool = True


class ChatApp(App):
    """Aplicação de chat terminal construída com Textual.

    Usage:
        app = ChatApp(on_command=my_handler)
        app.run()
    """

    CSS = """
    Screen {
        layout: vertical;
    }
    #chat-log {
        height: 1fr;
        overflow-y: auto;
        padding: 1 2;
    }
    #input-line {
        height: 3;
        dock: bottom;
    }
    .message-container {
        layout: horizontal;
        width: 100%;
        padding: 1 0;
    }
    .message-container.sent {
        align: right top;
    }
    .message-container.received {
        align: left top;
    }
    .message-bubble {
        layout: vertical;
        max-width: 60%;
        padding: 1 2;
        border: round $primary;
        background: $surface;
        color: $text;
    }
    .message-container.sent .message-bubble {
        background: $accent;
        color: $text;
    }
    .message-container.received .message-bubble {
        background: $primary-darken-2;
        color: $text;
    }
    .message-header {
        color: $text-muted;
        text-style: italic;
        margin: 0;
    }
    .message-body {
        margin: 0;
    }
    .message-quote {
        color: $text-muted;
        background: $panel;
        border-left: thick $primary;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    """

    def __init__(self, on_command: Optional[Callable[[str], None]] = None) -> None:
        super().__init__()
        self.on_command : Optional[Callable[[str], None]] = on_command
        self.messages  : List[ChatMessage] = []
        self._next_id  : int = 1
        self._rendered : int = 0
        # Mapping from message id to list of reply ids (for threading)
        self._replies  : Dict[str, List[str]] = {}

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Container(
            ScrollableContainer(id="chat-log"),
            Input(placeholder="Type a message or /command", id="input-line"),
        )

    def on_mount(self) -> None:
        """Focus the input when the app starts."""
        self.query_one("#input-line", Input).focus()

    def on_input_submitted(self, message: Input.Submitted) -> None:
        """Handle user pressing Enter in the input field."""
        del message
        inp = self.query_one("#input-line", Input)
        text = inp.value.strip()
        if not text:
            return
        inp.value = ""  # clear input
        if text.startswith(COMMAND_PREFIX):
            self.send_command(text[1:].strip())
        else:
            self.send_message(text)

    # === Public API =================================================================

    def send_message(self, text: str, *, reply_to: Optional[str] = None) -> str:
        """Envia uma mensagem normal e devolve o seu id.

        Args:
        text : Conteúdo da mensagem.
        reply_to : Id da mensagem a que esta responde (opcional).
        """
        msg_id = self._add_message(
            ChatMessage(
                id=self._new_id(),
                text=text,
                is_command=False,
                is_sent_by_me=True,
                reply_to=reply_to,
            )
        )
        if reply_to is not None:
            self._replies.setdefault(reply_to, []).append(msg_id)
        return msg_id

    def send_command(self, command: str) -> str:
        """Envia um comando (sem o prefixo '/') e devolve o seu id."""
        logger.info("Command executed: %s", command)
        self._handle_command(command)
        return self._add_message(
            ChatMessage(
                id=self._new_id(),
                text=command,
                is_command=True,
                is_sent_by_me=True,
            )
        )

    def receive_message(
        self,
        text: str,
        *,
        reply_to: Optional[str] = None,
    ) -> str:
        """Recebe uma mensagem vinda de fora e devolve o seu id.

        Args:
        text : Conteúdo da mensagem.
        reply_to : Id de uma mensagem enviada a que esta responde (opcional).
        """
        msg_id = self._add_message(
            ChatMessage(
                id=self._new_id(),
                text=text,
                is_command=False,
                is_sent_by_me=False,
                reply_to=reply_to,
            )
        )
        if reply_to is not None:
            self._replies.setdefault(reply_to, []).append(msg_id)
        return msg_id

    def get_replies(self, msg_id: str) -> List[str]:
        """Devolve os ids das mensagens que respondem a *msg_id*."""
        return list(self._replies.get(msg_id, []))

    # === Hooks ======================================================================

    def _handle_command(self, command: str) -> None:
        """Hook para tratar comandos. Override para comportamento próprio.

        Por omissão delega no callback ``on_command`` passado no __init__.
        """
        if self.on_command is not None:
            self.on_command(command)

    # === Internals ==================================================================

    def _new_id(self) -> str:
        msg_id = f"msg-{self._next_id}"
        self._next_id += 1
        return msg_id

    def _add_message(self, msg: ChatMessage) -> str:
        """Adiciona uma mensagem ao histórico e re-renderiza o log."""
        self.messages.append(msg)
        self._refresh_chat_log()
        self._scroll_to_bottom()
        return msg.id

    def _refresh_chat_log(self) -> None:
        """Monta apenas as mensagens novas no log (renderização incremental)."""
        chat_log = self.query_one("#chat-log", ScrollableContainer)
        for msg in self.messages[self._rendered:]:
            chat_log.mount(self._render_message(msg))
        self._rendered = len(self.messages)

    def _render_message(self, msg: ChatMessage) -> Widget:
        """Render a message as a container with header and body."""
        sender = "You" if msg.is_sent_by_me else "Other"
        time_str = msg.timestamp.strftime("%H:%M")
        prefix = f"[{time_str}] {sender} · {msg.id}"
        if msg.reply_to is not None:
            prefix += " ↳ respondendo"

        header = Static(prefix, classes="message-header")
        parts: List[Widget] = [header]

        # Citação da mensagem original quando é uma resposta
        if msg.reply_to is not None:
            original = self._find_message(msg.reply_to)
            if original is not None:
                preview = " ".join(original.text.split())[:60]
                parts.append(
                    Static(f"↳ {original.id}: {preview}…", classes="message-quote")
                )

        parts.append(Markdown(msg.text, classes="message-body"))

        bubble = Vertical(*parts, classes="message-bubble")

        # Container to align left or right
        container = Horizontal(bubble, classes="message-container")
        if msg.is_sent_by_me:
            container.add_class("sent")
        else:
            container.add_class("received")

        return container

    def _find_message(self, msg_id: str) -> Optional[ChatMessage]:
        """Devolve a mensagem com o id dado, ou None."""
        for m in self.messages:
            if m.id == msg_id:
                return m
        return None

    def _scroll_to_bottom(self) -> None:
        """Scrolls the chat log to the bottom."""
        chat_log = self.query_one("#chat-log", ScrollableContainer)
        chat_log.scroll_end(animate=False)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ChatApp().run()
