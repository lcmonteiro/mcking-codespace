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

from .chat_style import ChatStyle

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
    """Clickable message container — selects the msg as a reply target."""

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
    """Represents a chat message."""

    id          : str
    text        : str
    timestamp   : datetime = field(default_factory=datetime.now)
    is_command  : bool = False
    reply_to    : Optional[str] = None
    is_sent_by_me : bool = True


class ChatApp(App):
    """Terminal chat application built with Textual.

    Usage:
        app = ChatApp(command_handler=my_handler, max_displayed=100)
        app.run()

    ``max_displayed`` limits how many messages are rendered in the
    terminal (sliding window). The full history is always kept in
    ``app.messages`` — older messages only leave the screen, not memory.

    The theme is built from a :class:`~chatinho.chat_style.ChatStyle`;
    pass one to ``style=`` to customise colours programmatically.
    """

    # Default stylesheet, rendered from ChatStyle() at class definition time.
    CSS = ChatStyle().to_css()

    def __init__(
        self,
        command_handler: Optional[Callable[[str], None]] = None,
        max_displayed: int = 100,
        style: Optional[ChatStyle] = None,
    ) -> None:
        super().__init__()
        if style is not None:
            # Instance-level override: Textual reads ``self.CSS`` at mount.
            self.CSS = style.to_css()
        self.command_handler : Optional[Callable[[str], None]] = command_handler
        self.messages  : List[ChatMessage] = []
        self._next_id  : int = 1
        self._rendered : int = 0
        # Mapping from message id to list of reply ids (for threading)
        self._replies  : Dict[str, List[str]] = {}
        # Message selected as reply target (via click)
        self._reply_target : Optional[str] = None
        self._msg_widgets  : Dict[str, Widget] = {}
        self._input_placeholder = "Type a message or /command"
        # Max number of messages rendered in the terminal (history stays complete in ``messages``)
        self.max_displayed: int = max_displayed
        # IDs of the messages currently rendered, in order
        self._rendered_msg_ids: List[str] = []

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
        """Sends a normal message and returns its id.

        Args:
        text : Message content.
        reply_to : Id of the message this one replies to (optional).
        """
        msg = ChatMessage(
            id=self._new_id(),
            text=text,
            is_command=False,
            is_sent_by_me=True,
            reply_to=reply_to,
        )
        self._add_message(msg)
        if reply_to is not None:
            self._replies.setdefault(reply_to, []).append(msg_id := msg.id)
        self.on_message_sent(msg)
        return msg.id

    def send_command(self, command: str) -> str:
        """Sends a command (without the '/' prefix) and returns its id."""
        logger.info("Command executed: %s", command)
        msg = ChatMessage(
            id=self._new_id(),
            text=command,
            is_command=True,
            is_sent_by_me=True,
        )
        self._add_message(msg)
        self.on_command(command)
        self.on_message_sent(msg)
        return msg.id

    def receive_message(
        self,
        text: str,
        *,
        reply_to: Optional[str] = None,
    ) -> str:
        """Receives a message from outside and returns its id.

        Args:
        text : Message content.
        reply_to : Id of a sent message this one replies to (optional).
        """
        msg = ChatMessage(
            id=self._new_id(),
            text=text,
            is_command=False,
            is_sent_by_me=False,
            reply_to=reply_to,
        )
        self._add_message(msg)
        if reply_to is not None:
            self._replies.setdefault(reply_to, []).append(msg.id)
        self.on_message_received(msg)
        return msg.id

    def get_replies(self, msg_id: str) -> List[str]:
        """Returns the ids of the messages that reply to *msg_id*."""
        return list(self._replies.get(msg_id, []))

    # === Hooks (callbacks — all start with ``on_``) ==============================

    def on_command(self, command: str) -> None:
        """Called when the user sends a command (without the '/' prefix).

        Override for custom behavior; by default it delegates to the
        ``command_handler`` callback passed in __init__.
        """
        if self.command_handler is not None:
            self.command_handler(command)

    def on_message_sent(self, msg: ChatMessage) -> None:
        """Called after sending a message (normal or command).

        Useful for hooking the send to a transport (WebSocket, API, …).
        """

    def on_message_received(self, msg: ChatMessage) -> None:
        """Called after receiving a message from outside."""

    # === Internals ==================================================================

    def _new_id(self) -> str:
        msg_id = f"msg-{self._next_id}"
        self._next_id += 1
        return msg_id

    def _add_message(self, msg: ChatMessage) -> str:
        """Adds a message to the history and re-renders the log."""
        chat_log = self.query_one("#chat-log", ScrollableContainer)
        # Only auto-scrolls if the user is already at the bottom (otherwise they lose their reading position)
        was_at_bottom = chat_log.scroll_offset.y >= (chat_log.max_scroll_y - 1)
        self.messages.append(msg)
        self._refresh_chat_log()
        if was_at_bottom:
            self._scroll_to_bottom()
        return msg.id

    def _refresh_chat_log(self) -> None:
        """Renders only the last ``max_displayed`` messages (sliding window).

        Mounts the new ones and unmounts the old ones that left the window,
        to limit the number of widgets in the terminal.
        """
        chat_log = self.query_one("#chat-log", ScrollableContainer)

        # Desired window: the last max_displayed messages
        total = len(self.messages)
        start = max(0, total - self.max_displayed)
        desired_ids = [m.id for m in self.messages[start:]]

        current = set(self._rendered_msg_ids)
        desired = set(desired_ids)

        # Unmount messages that left the window
        for msg_id in self._rendered_msg_ids:
            if msg_id not in desired:
                widget = self._msg_widgets.pop(msg_id, None)
                if widget is not None:
                    widget.remove()

        # Mount the new ones, in the correct order
        for msg_id in desired_ids:
            if msg_id not in current:
                msg = self._find_message(msg_id)
                if msg is not None:
                    chat_log.mount(self._render_message(msg))

        self._rendered_msg_ids = desired_ids
        self._rendered = total

    def _render_message(self, msg: ChatMessage) -> Widget:
        """Render a message as a clickable container with header and body."""
        sender = "You" if msg.is_sent_by_me else "Other"
        time_str = msg.timestamp.strftime("%H:%M")
        prefix = f"[{time_str}] {sender} · {msg.id}"
        if msg.reply_to is not None:
            prefix += " ↳ replying"

        header = Static(prefix, classes="message-header")
        parts: List[Widget] = [header]

        # Quote of the original message when this is a reply
        if msg.reply_to is not None:
            original = self._find_message(msg.reply_to)
            if original is not None:
                preview = " ".join(original.text.split())[:60]
                parts.append(
                    Static(f"↳ {original.id}: {preview}…", classes="message-quote")
                )

        parts.append(Markdown(msg.text, classes="message-body"))

        bubble = Vertical(*parts, classes="message-bubble")

        # Clickable container — aligns left/right and selects the reply target
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

    # === Reply target (click) ======================================================

    def _on_message_clicked(self, msg_id: str) -> None:
        """Selects/deselects a message as the reply target."""
        if self._reply_target == msg_id:
            self._clear_reply_target()
        else:
            self._set_reply_target(msg_id)

    def _set_reply_target(self, msg_id: str) -> None:
        """Marks *msg_id* as the reply target and updates the input."""
        self._reply_target = msg_id
        self._refresh_reply_target_ui()
        inp = self.query_one("#input-line", Input)
        inp.placeholder = f"Reply to {msg_id}…"

    def _clear_reply_target(self) -> None:
        """Clears the reply target and restores the input."""
        self._reply_target = None
        self._refresh_reply_target_ui()
        inp = self.query_one("#input-line", Input)
        inp.placeholder = self._input_placeholder

    def _refresh_reply_target_ui(self) -> None:
        """Updates the visual highlight of all messages."""
        for msg_id, widget in self._msg_widgets.items():
            widget.set_class(msg_id == self._reply_target, "reply-target")

    def send_pending_reply(self, text: str) -> Optional[str]:
        """Sends *text* as a reply to the selected message (if any).

        Clears the selection. Returns the id of the sent message, or None
        if there is no selected target.
        """
        if self._reply_target is None:
            return None
        target = self._reply_target
        self._clear_reply_target()
        return self.send_message(text, reply_to=target)

    def _find_message(self, msg_id: str) -> Optional[ChatMessage]:
        """Returns the message with the given id, or None."""
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
