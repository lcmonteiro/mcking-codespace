"""Connectors: pluggable backends for chatinho.

Two independent connector types, matching the two separate concerns of
a chat transport:

- ``HistoryConnector`` — loads past messages when the app starts, and
  persists every message (sent or received) as it happens. Point one
  at a JSON file, SQLite, a REST API, whatever.
- ``TransportConnector`` — sends outgoing messages and delivers
  incoming ones into the running app. Point one at a WebSocket, MQTT,
  a message queue, whatever.

Each connector type owns its own lifecycle hooks — override
``on_loaded``/``on_saved`` on a ``HistoryConnector`` subclass, or
``on_started``/``on_stopped`` on a ``TransportConnector`` subclass, to
react without polling.

Attach a connector to an app with ``app.connect_history(...)`` /
``app.connect_transport(...)``, or declare it upfront with the
``@connector(...)`` class decorator::

    @connector(JsonlHistoryConnector("chat.jsonl"))
    class MyApp(ChatApp):
        ...

A connector class doesn't need to subclass the ABC explicitly — decorate
it with ``@history_connector`` / ``@transport_connector`` instead::

    @history_connector
    class Recorder:
        def load(self):
            return [...]

        def save(self, message):
            ...

This package also ships one ready-to-use implementation of each type —
``JsonlHistoryConnector`` and ``CallbackTransportConnector``.
"""

from .base import (
    ConnectorArg,
    HistoryConnector,
    ReceiveCallback,
    TransportConnector,
    connector,
    history_connector,
    transport_connector,
)
from .callback_transport_connector import CallbackTransportConnector
from .json_history_connector import JsonlHistoryConnector

__all__ = [
    "HistoryConnector",
    "TransportConnector",
    "ReceiveCallback",
    "ConnectorArg",
    "connector",
    "history_connector",
    "transport_connector",
    "JsonlHistoryConnector",
    "CallbackTransportConnector",
]
