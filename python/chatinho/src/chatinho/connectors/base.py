"""Connector capability checks and attachment decorators.

No base class to subclass — a connector is any object with the right
methods:

- **History connector**: needs ``load()`` and ``save(message)``.
  Optional ``on_loaded(messages)`` / ``on_saved(message)`` hooks.
- **Transport connector**: needs ``start(on_receive)`` and
  ``send(message)``. Optional ``stop()`` / ``on_started()`` /
  ``on_stopped()`` hooks.

``@history_connector`` / ``@transport_connector`` validate a class has
the required methods, failing loudly at class-definition time if not.
``@connector(...)`` attaches a connector to a ``ChatApp`` subclass —
every instance gets it, automatically, before ``on_mount`` — running
the same capability check to decide whether it's a history or a
transport connector.
"""

from typing import TYPE_CHECKING, Any, Callable, Optional, Tuple, Type, TypeVar, Union

if TYPE_CHECKING:
    from ..chat_app import ChatApp

# Called by a transport connector for every message it receives from the
# outside world: (text, reply_to). Safe to call from any thread.
ReceiveCallback = Callable[[str, Optional[str]], None]

_AppT = TypeVar("_AppT", bound="ChatApp")

_HISTORY_METHODS: Tuple[str, ...] = ("load", "save")
_TRANSPORT_METHODS: Tuple[str, ...] = ("start", "send")


def _has_methods(obj: object, names: Tuple[str, ...]) -> bool:
    return all(callable(getattr(obj, name, None)) for name in names)


def is_history_connector(obj: object) -> bool:
    """Structural check: does *obj* have ``load()`` and ``save()``?"""
    return _has_methods(obj, _HISTORY_METHODS)


def is_transport_connector(obj: object) -> bool:
    """Structural check: does *obj* have ``start()`` and ``send()``?"""
    return _has_methods(obj, _TRANSPORT_METHODS)


def history_connector(cls: type) -> type:
    """Class decorator: validates *cls* is capable of being a history
    connector — has ``load()`` and ``save(message)`` — raising
    ``TypeError`` at class-definition time if not::

        @history_connector
        class Recorder:
            def load(self):
                return [...]

            def save(self, message):
                ...
    """
    if not is_history_connector(cls):
        raise TypeError(
            f"{cls.__name__} can't be a history connector: needs load() and save()"
        )
    return cls


def transport_connector(cls: type) -> type:
    """Class decorator: validates *cls* is capable of being a transport
    connector — has ``start(on_receive)`` and ``send(message)`` —
    raising ``TypeError`` at class-definition time if not.
    """
    if not is_transport_connector(cls):
        raise TypeError(
            f"{cls.__name__} can't be a transport connector: needs start() and send()"
        )
    return cls


ConnectorArg = Union[object, Type[object]]


def connector(
    target: ConnectorArg, *args: Any, **kwargs: Any
) -> Callable[[Type[_AppT]], Type[_AppT]]:
    """Class decorator for a ``ChatApp`` subclass: declares a connector to
    attach to every instance, automatically, before ``on_mount``.

    *target* may be a connector class — instantiated lazily, once per
    app instance, with *args*/*kwargs* passed to its constructor — or
    an already-built instance (shared across instances)::

        @connector(JsonlHistoryConnector, "chat.jsonl")   # lazy: built per instance
        class MyApp(ChatApp):
            ...

        @connector(my_transport)                           # already-built, shared
        class MyApp(ChatApp):
            ...

    Whether it's routed to history or transport is decided by the same
    capability check as :func:`history_connector`/:func:`transport_connector`.
    Stack multiple applications to attach more than one connector::

        @connector(MyHistory)
        @connector(MyTransport)
        class MyApp(ChatApp):
            ...
    """

    def decorate(app_cls: Type[_AppT]) -> Type[_AppT]:
        original_init: Callable[..., None] = app_cls.__init__

        def __init__(self: _AppT, *init_args: Any, **init_kwargs: Any) -> None:
            original_init(self, *init_args, **init_kwargs)
            instance = target(*args, **kwargs) if isinstance(target, type) else target
            if is_history_connector(instance):
                self._history = instance
            elif is_transport_connector(instance):
                self._transport = instance
            else:
                raise TypeError(
                    f"{instance!r} is not a valid connector: needs load()+save() "
                    "(history) or start()+send() (transport)"
                )

        app_cls.__init__ = __init__  # type: ignore[assignment]
        return app_cls

    return decorate
