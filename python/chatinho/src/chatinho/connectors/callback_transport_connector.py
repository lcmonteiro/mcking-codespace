"""CallbackTransportConnector: a ready-to-use transport connector."""

from typing import TYPE_CHECKING, Callable, Optional

from .base import ReceiveCallback, transport_connector

if TYPE_CHECKING:
    from ..chat_app import ChatMessage


@transport_connector
class CallbackTransportConnector:
    """Transport backed by two plain callables — adapt this to any real
    backend (WebSocket, MQTT, a message queue, ...) without subclassing.

    Example::

        transport = CallbackTransportConnector(send_fn=lambda msg: ws.send(msg.text))

        @connector(transport)
        class MyApp(ChatApp):
            ...

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
