"""Connectors: pluggable backends for chatinho.

No base class to subclass — a connector is any object with the right
methods, matching one of two roles:

- **History connector** — ``load()`` returns past messages when the
  app starts, ``save(message)`` persists every message (sent or
  received) as it happens. Point one at a JSON file, SQLite, a REST
  API, whatever. Optional ``on_loaded(messages)`` / ``on_saved(message)``
  hooks.
- **Transport connector** — ``start(on_receive)`` begins listening,
  ``send(message)`` sends outgoing messages. Point one at a WebSocket,
  MQTT, a message queue, whatever. Optional ``stop()`` /
  ``on_started()`` / ``on_stopped()`` hooks.

Declare a connector on a ``ChatApp`` subclass with the ``@connector(...)``
class decorator — every instance gets it, automatically, before
``on_mount``::

    @connector(JsonlHistoryConnector, "chat.jsonl")  # lazy: built per instance
    class MyApp(ChatApp):
        ...

Validate a plain class is capable of the role you intend with
``@history_connector`` / ``@transport_connector`` — they check for the
required methods and raise ``TypeError`` at class-definition time if
missing::

    @history_connector
    class Recorder:
        def load(self):
            return [...]

        def save(self, message):
            ...

This package also ships one ready-to-use implementation of each role —
``JsonlHistoryConnector`` and ``CallbackTransportConnector``.
"""

from .base import (
    ConnectorArg,
    ReceiveCallback,
    connector,
    history_connector,
    is_history_connector,
    is_transport_connector,
    transport_connector,
)
from .callback_transport_connector import CallbackTransportConnector
from .json_history_connector import JsonlHistoryConnector

__all__ = [
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
