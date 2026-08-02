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

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container, ScrollableContainer, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Input, Markdown, Static

logger = logging.getLogger(__name__)

COMMAND_PREFIX : str = "/"


class TouchScrollableContainer(ScrollableContainer):
    """Scrollable container that supports mouse/touch drag scrolling."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._drag_start_y: int = 0
        self._scroll_start_y: int = 0

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """Record the start position when drag begins."""
        self._drag_start_y = event.y
        self._scroll_start_y = self.scroll_offset.y
        event.stop()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        """Handle drag to scroll vertically."""
        if not event.button:
            return
        delta_y = event.y - self._drag_start_y
        target_y = self._scroll_start_y - delta_y
        max_y = self.max_scroll_y
        if max_y > 0:
            target_y = max(0, min(target_y, max_y))
            self.scroll_to(y=target_y, animate=False)
        event.stop()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        """Handle drag end."""
        event.stop()


class _MessageContainer(Horizontal):
    """Container de mensagem clicável — seleciona a msg como alvo de reply."""

    def __init__(
        self,
        *children: Widget,
        msg_id: str,
        on_select: Callable[[str], None],
        **kwargs,
    ) -> None:
        super().__init__(*children, **kwargs)
        self.msg_id = msg_id
        self._on_select = on_select

    def on_click(self, event: events.Click) -> None:
        self._on_select(self.msg_id)


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
        background: $surface;
    }
    
    /* Make scrollbar more visible */
    .scrollbar {
        background: $surface-darken-1;
        color: $primary;
    }
    
    .scrollbar:hover {
        background: $surface-darken-2;
        color: $primary-darken-2;
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
    .message-container.reply-target .message-bubble {
        border: thick $accent;
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
        # Mensagem selecionada como alvo de resposta (via clique)
        self._reply_target : Optional[str] = None
        self._msg_widgets  : Dict[str, Widget] = {}
        self._input_placeholder = "Type a message or /command"

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Container(
            TouchScrollableContainer(id="chat-log"),
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
            if self._reply_target is not None:
                self.send_message(text, reply_to=self._reply_target)
                self._clear_reply_target()
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
        """Render a message as a clickable container with header and body."""
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

        # Container clicável — alinha à esquerda/direita e seleciona reply target
        container = _MessageContainer(
            bubble,
            msg_id=msg.id,
            on_select=self._on_message_clicked,
            classes="message-container",
        )
        if msg.is_sent_by_me:
            container.add_class("sent")
        else:
            container.add_class("received")

        self._msg_widgets[msg.id] = container
        return container

    # === Reply target (clique) ======================================================

    def _on_message_clicked(self, msg_id: str) -> None:
        """Seleciona/desseleciona uma mensagem como alvo de resposta."""
        if self._reply_target == msg_id:
            self._clear_reply_target()
        else:
            self._set_reply_target(msg_id)

    def _set_reply_target(self, msg_id: str) -> None:
        """Marca *msg_id* como alvo de resposta e atualiza o input."""
        self._reply_target = msg_id
        self._refresh_reply_target_ui()
        inp = self.query_one("#input-line", Input)
        inp.placeholder = f"Responder a {msg_id}…"

    def _clear_reply_target(self) -> None:
        """Limpa o alvo de resposta e restaura o input."""
        self._reply_target = None
        self._refresh_reply_target_ui()
        inp = self.query_one("#input-line", Input)
        inp.placeholder = self._input_placeholder

    def _refresh_reply_target_ui(self) -> None:
        """Atualiza o realce visual de todas as mensagens."""
        for msg_id, widget in self._msg_widgets.items():
            widget.set_class(msg_id == self._reply_target, "reply-target")

    def send_pending_reply(self, text: str) -> Optional[str]:
        """Envia *text* como resposta à mensagem selecionada (se houver).

        Limpa a seleção. Devolve o id da mensagem enviada, ou None se não
        houver alvo selecionado.
        """
        if self._reply_target is None:
            return None
        target = self._reply_target
        self._clear_reply_target()
        return self.send_message(text, reply_to=target)

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
