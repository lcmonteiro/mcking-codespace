"""Connector base classes, lifecycle hooks, and attachment decorators.

Two independent connector types:

- ``HistoryConnector`` — loads past messages when the app starts, and
  persists every message (sent or received) as it happens.
- ``TransportConnector`` — sends outgoing messages and delivers
  incoming ones into the running app.

Each connector type owns its own lifecycle hooks (``on_loaded``/
``on_saved`` for history, ``on_started``/``on_stopped`` for transport)
— override them on your connector subclass, not on ``ChatApp``.

Three decorators tie connectors to an app:

- ``history_connector`` / ``transport_connector`` — mark a plain class
  as a connector without subclassing the ABC explicitly.
- ``connector`` — a class decorator for a ``ChatApp`` subclass that
  declares connectors to attach to every instance automatically,
  before ``on_mount``. Stack multiple applications, or pass several
  connectors to one call, to attach more than one.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Type, TypeVar, Union, cast

if TYPE_CHECKING:
    from ..chat_app import ChatApp, ChatMessage

# Called by a TransportConnector for every message it receives from the
# outside world: (text, reply_to). Safe to call from any thread.
ReceiveCallback = Callable[[str, Optional[str]], None]

_AppT = TypeVar("_AppT", bound="ChatApp")


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

    def on_loaded(self, messages: List["ChatMessage"]) -> None:
        """Optional hook: called once, right after :meth:`load` returns.

        ``messages`` is exactly what :meth:`load` returned (may be
        empty). Override to react — e.g. log how much history came
        back, or show a "loaded N messages" notice.
        """

    def on_saved(self, message: "ChatMessage") -> None:
        """Optional hook: called right after :meth:`save` persists a message."""


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

    def on_started(self) -> None:
        """Optional hook: called right after :meth:`start`."""

    def on_stopped(self) -> None:
        """Optional hook: called right after :meth:`stop`."""


def history_connector(cls: type) -> Type[HistoryConnector]:
    """Class decorator: makes *cls* a :class:`HistoryConnector` without
    requiring explicit inheritance::

        @history_connector
        class Recorder:
            def load(self):
                return [...]

            def save(self, message):
                ...

    A no-op if *cls* already subclasses ``HistoryConnector``.
    """
    if issubclass(cls, HistoryConnector):
        return cls
    merged = type(cls.__name__, (cls, HistoryConnector), {})
    merged.__module__ = cls.__module__
    merged.__qualname__ = cls.__qualname__
    return cast(Type[HistoryConnector], merged)


def transport_connector(cls: type) -> Type[TransportConnector]:
    """Class decorator: makes *cls* a :class:`TransportConnector` without
    requiring explicit inheritance (see :func:`history_connector` for
    the same pattern).
    """
    if issubclass(cls, TransportConnector):
        return cls
    merged = type(cls.__name__, (cls, TransportConnector), {})
    merged.__module__ = cls.__module__
    merged.__qualname__ = cls.__qualname__
    return cast(Type[TransportConnector], merged)


ConnectorArg = Union[
    HistoryConnector,
    TransportConnector,
    Type[HistoryConnector],
    Type[TransportConnector],
]


def connector(*connectors: ConnectorArg) -> Callable[[Type[_AppT]], Type[_AppT]]:
    """Class decorator for a ``ChatApp`` subclass: declares connectors to
    attach to every instance, automatically, before ``on_mount``::

        @connector(MyHistory)
        @connector(MyTransport)
        class MyApp(ChatApp):
            ...

        # or, several at once:
        @connector(MyHistory, MyTransport)
        class MyApp(ChatApp):
            ...

    Each connector may be a zero-argument class (instantiated for you)
    or an already-built instance, and is routed to
    :meth:`~chatinho.chat_app.ChatApp.connect_history` /
    :meth:`~chatinho.chat_app.ChatApp.connect_transport` based on its
    type.
    """

    def decorate(app_cls: Type[_AppT]) -> Type[_AppT]:
        original_init: Callable[..., None] = app_cls.__init__

        def __init__(self: _AppT, *args: Any, **kwargs: Any) -> None:
            original_init(self, *args, **kwargs)
            for conn in connectors:
                instance = conn() if isinstance(conn, type) else conn
                if isinstance(instance, HistoryConnector):
                    self.connect_history(instance)
                elif isinstance(instance, TransportConnector):
                    self.connect_transport(instance)
                else:
                    raise TypeError(
                        f"{instance!r} is not a HistoryConnector or TransportConnector"
                    )

        app_cls.__init__ = __init__  # type: ignore[assignment]
        return app_cls

    return decorate
