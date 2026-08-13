"""Tests for chatinho's connector concept.

Two independent connector types:

- ``HistoryConnector`` — loads past messages on startup, saves every
  message (sent or received) as it happens. Owns ``on_loaded``/
  ``on_saved`` hooks.
- ``TransportConnector`` — sends outgoing messages, delivers incoming
  ones into the running app. Owns ``on_started``/``on_stopped`` hooks.

Both attach via ``app.connect_history()`` / ``app.connect_transport()``
(decorator-compatible), or declaratively via the ``@connector(...)``
class decorator on a ``ChatApp`` subclass. A connector class doesn't
need to subclass the ABC explicitly — ``@history_connector`` /
``@transport_connector`` mark a plain class instead.
"""

import pytest

from chatinho import (
    CallbackTransportConnector,
    ChatApp,
    HistoryConnector,
    JsonlHistoryConnector,
    TransportConnector,
    connector,
    history_connector,
    transport_connector,
)


class MemoryHistory(HistoryConnector):
    """In-memory HistoryConnector for tests: records save()/hook calls."""

    def __init__(self, initial=None):
        self._initial = list(initial or [])
        self.saved = []
        self.loaded_calls = []
        self.saved_hook_calls = []

    def load(self):
        return list(self._initial)

    def save(self, message):
        self.saved.append(message)

    def on_loaded(self, messages):
        self.loaded_calls.append(messages)

    def on_saved(self, message):
        self.saved_hook_calls.append(message)


class MemoryTransport(TransportConnector):
    """In-memory TransportConnector for tests: records calls/hooks."""

    def __init__(self):
        self.sent = []
        self.events = []
        self._on_receive = None

    def start(self, on_receive):
        self._on_receive = on_receive
        self.events.append("started")

    def send(self, message):
        self.sent.append(message)

    def stop(self):
        self.events.append("stopped")

    def on_started(self):
        self.events.append("hook:started")

    def on_stopped(self):
        self.events.append("hook:stopped")

    def push(self, text, reply_to=None):
        assert self._on_receive is not None
        self._on_receive(text, reply_to)


# === HistoryConnector: wiring ======================================================


@pytest.mark.asyncio
async def test_connect_history_as_plain_call_loads_on_mount():
    history = MemoryHistory()
    app = ChatApp()
    app.connect_history(history)  # before mount: loaded during on_mount
    async with app.run_test():
        assert app.messages == []  # nothing to load, but no crash


@pytest.mark.asyncio
async def test_connect_history_loads_past_messages_into_app():
    seed = ChatApp()
    async with seed.run_test():
        original_id = seed.send_message("hi")
    # A fresh app, seeded with what the "previous session" sent.
    history = MemoryHistory(initial=list(seed.messages))

    app = ChatApp()
    app.connect_history(history)
    async with app.run_test():
        assert len(app.messages) == 1
        assert app.messages[0].text == "hi"
        assert app.messages[0].id == original_id


@pytest.mark.asyncio
async def test_loaded_history_is_not_re_saved():
    seed = ChatApp()
    async with seed.run_test():
        seed.send_message("hi")
    history = MemoryHistory(initial=list(seed.messages))

    app = ChatApp()
    app.connect_history(history)
    async with app.run_test():
        pass
    assert history.saved == []  # loading must not trigger save()


@pytest.mark.asyncio
async def test_send_and_receive_trigger_save():
    history = MemoryHistory()
    app = ChatApp()
    app.connect_history(history)
    async with app.run_test():
        app.send_message("outgoing")
        app.receive_message("incoming")
    assert [m.text for m in history.saved] == ["outgoing", "incoming"]


@pytest.mark.asyncio
async def test_new_ids_continue_after_loaded_history():
    seed = ChatApp()
    async with seed.run_test():
        seed.send_message("one")
        seed.send_message("two")
    history = MemoryHistory(initial=list(seed.messages))

    app = ChatApp()
    app.connect_history(history)
    async with app.run_test():
        new_id = app.send_message("three")
    assert new_id == "msg-3"


@pytest.mark.asyncio
async def test_connect_history_as_decorator_on_class():
    saved = []

    app = ChatApp()

    @app.connect_history
    class Recorder(HistoryConnector):
        def load(self):
            return []

        def save(self, message):
            saved.append(message.text)

    assert Recorder.__name__ == "Recorder"  # decorator returns the class unchanged
    async with app.run_test():
        app.send_message("via decorator class")
    assert saved == ["via decorator class"]


@pytest.mark.asyncio
async def test_late_history_attachment_after_mount_loads_immediately():
    history = MemoryHistory()
    app = ChatApp()
    async with app.run_test():
        app.connect_history(history)  # attached after mount
        app.send_message("late")
    assert [m.text for m in history.saved] == ["late"]


# === TransportConnector: wiring ====================================================


@pytest.mark.asyncio
async def test_connect_transport_starts_on_mount():
    transport = MemoryTransport()
    app = ChatApp()
    app.connect_transport(transport)
    async with app.run_test():
        assert "started" in transport.events


@pytest.mark.asyncio
async def test_sending_calls_transport_send():
    sent = []
    transport = CallbackTransportConnector(send_fn=lambda msg: sent.append(msg.text))
    app = ChatApp()
    app.connect_transport(transport)
    async with app.run_test():
        app.send_message("hello transport")
    assert sent == ["hello transport"]


@pytest.mark.asyncio
async def test_transport_push_delivers_incoming_message():
    transport = CallbackTransportConnector(send_fn=lambda msg: None)
    app = ChatApp()
    app.connect_transport(transport)
    async with app.run_test():
        transport.push("from the wire", reply_to=None)
        assert len(app.messages) == 1
        assert app.messages[0].text == "from the wire"
        assert app.messages[0].is_sent_by_me is False


@pytest.mark.asyncio
async def test_received_messages_are_not_sent_back_through_transport():
    sent = []
    transport = CallbackTransportConnector(send_fn=lambda msg: sent.append(msg.text))
    app = ChatApp()
    app.connect_transport(transport)
    async with app.run_test():
        transport.push("incoming, should not echo")
    assert sent == []


@pytest.mark.asyncio
async def test_connect_transport_as_decorator_on_class():
    events = []

    app = ChatApp()

    @app.connect_transport
    class Recorder(TransportConnector):
        def start(self, on_receive):
            events.append("started")

        def send(self, message):
            events.append(f"sent:{message.text}")

        def stop(self):
            events.append("stopped")

    async with app.run_test():
        assert events == ["started"]
        app.send_message("ping")
    assert events == ["started", "sent:ping", "stopped"]


@pytest.mark.asyncio
async def test_late_transport_attachment_after_mount_starts_immediately():
    transport = MemoryTransport()
    app = ChatApp()
    async with app.run_test():
        app.connect_transport(transport)  # after mount
    assert "started" in transport.events


@pytest.mark.asyncio
async def test_transport_stop_called_on_unmount():
    transport = MemoryTransport()
    app = ChatApp()
    app.connect_transport(transport)
    async with app.run_test():
        pass
    assert transport.events == ["started", "hook:started", "stopped", "hook:stopped"]


# === Connector-owned lifecycle hooks (on_loaded/on_saved/on_started/on_stopped) =====
# The hooks belong to the connector, not to ChatApp — a plain ChatApp subclass with
# no connector-related overrides never sees them.


@pytest.mark.asyncio
async def test_on_loaded_fires_on_the_history_connector_with_loaded_messages():
    seed = ChatApp()
    async with seed.run_test():
        seed.send_message("hi")
    history = MemoryHistory(initial=list(seed.messages))

    app = ChatApp()
    app.connect_history(history)
    async with app.run_test():
        pass
    assert len(history.loaded_calls) == 1
    assert [m.text for m in history.loaded_calls[0]] == ["hi"]


@pytest.mark.asyncio
async def test_on_loaded_fires_even_with_no_past_messages():
    history = MemoryHistory()
    app = ChatApp()
    app.connect_history(history)
    async with app.run_test():
        pass
    assert history.loaded_calls == [[]]


@pytest.mark.asyncio
async def test_on_saved_fires_on_the_history_connector_not_for_loaded():
    seed = ChatApp()
    async with seed.run_test():
        seed.send_message("old one")
    history = MemoryHistory(initial=list(seed.messages))

    app = ChatApp()
    app.connect_history(history)
    async with app.run_test():
        app.send_message("new one")
        app.receive_message("incoming")
    assert [m.text for m in history.saved_hook_calls] == ["new one", "incoming"]


@pytest.mark.asyncio
async def test_on_started_fires_on_the_transport_connector():
    transport = MemoryTransport()
    app = ChatApp()
    app.connect_transport(transport)
    async with app.run_test():
        assert transport.events.count("hook:started") == 1


@pytest.mark.asyncio
async def test_bare_chat_app_subclass_never_sees_connector_hooks():
    """Without connect_history/connect_transport, a subclass is unaffected."""

    class PlainApp(ChatApp):
        pass

    app = PlainApp()
    async with app.run_test():
        app.send_message("hi")  # must not raise (no connector attached)


# === history_connector / transport_connector: duck-typed connector classes =========


@pytest.mark.asyncio
async def test_history_connector_decorator_makes_plain_class_a_history_connector():
    saved = []

    @history_connector
    class Recorder:  # no explicit base class
        def load(self):
            return []

        def save(self, message):
            saved.append(message.text)

    assert issubclass(Recorder, HistoryConnector)
    app = ChatApp()
    app.connect_history(Recorder())
    async with app.run_test():
        app.send_message("hi")
    assert saved == ["hi"]


def test_history_connector_decorator_is_a_noop_for_real_subclasses():
    class Already(HistoryConnector):
        def load(self):
            return []

        def save(self, message):
            pass

    assert history_connector(Already) is Already


@pytest.mark.asyncio
async def test_transport_connector_decorator_makes_plain_class_a_transport_connector():
    events = []

    @transport_connector
    class Recorder:  # no explicit base class
        def start(self, on_receive):
            events.append("started")

        def send(self, message):
            events.append(f"sent:{message.text}")

    assert issubclass(Recorder, TransportConnector)
    app = ChatApp()
    app.connect_transport(Recorder())
    async with app.run_test():
        app.send_message("hi")
    assert events == ["started", "sent:hi"]


def test_transport_connector_decorator_is_a_noop_for_real_subclasses():
    class Already(TransportConnector):
        def start(self, on_receive):
            pass

        def send(self, message):
            pass

    assert transport_connector(Already) is Already


# === connector(...): declarative class decorator on a ChatApp subclass =============


@pytest.mark.asyncio
async def test_connector_decorator_attaches_history_class():
    saved = []

    @history_connector
    class Recorder:
        def load(self):
            return []

        def save(self, message):
            saved.append(message.text)

    @connector(Recorder)
    class MyApp(ChatApp):
        pass

    app = MyApp()
    async with app.run_test():
        app.send_message("hi")
    assert saved == ["hi"]


@pytest.mark.asyncio
async def test_connector_decorator_accepts_an_instance():
    history = MemoryHistory()

    @connector(history)
    class MyApp(ChatApp):
        pass

    app = MyApp()
    async with app.run_test():
        app.send_message("hi")
    assert [m.text for m in history.saved] == ["hi"]


@pytest.mark.asyncio
async def test_connector_decorator_stacks_history_and_transport():
    history_saved = []
    transport_sent = []

    @history_connector
    class H:
        def load(self):
            return []

        def save(self, message):
            history_saved.append(message.text)

    @transport_connector
    class T:
        def start(self, on_receive):
            pass

        def send(self, message):
            transport_sent.append(message.text)

    @connector(H)
    @connector(T)
    class MyApp(ChatApp):
        pass

    app = MyApp()
    async with app.run_test():
        app.send_message("hi")
    assert history_saved == ["hi"]
    assert transport_sent == ["hi"]


@pytest.mark.asyncio
async def test_connector_decorator_accepts_multiple_connectors_at_once():
    history_saved = []
    transport_sent = []

    @history_connector
    class H:
        def load(self):
            return []

        def save(self, message):
            history_saved.append(message.text)

    @transport_connector
    class T:
        def start(self, on_receive):
            pass

        def send(self, message):
            transport_sent.append(message.text)

    @connector(H, T)
    class MyApp(ChatApp):
        pass

    app = MyApp()
    async with app.run_test():
        app.send_message("hi")
    assert history_saved == ["hi"]
    assert transport_sent == ["hi"]


@pytest.mark.asyncio
async def test_connector_decorator_preserves_constructor_arguments():
    """@connector-decorated apps still accept ChatApp's normal constructor args."""
    commands_seen = []

    @connector(MemoryHistory())
    class MyApp(ChatApp):
        pass

    app = MyApp(command_handler=commands_seen.append, max_displayed=5)
    async with app.run_test():
        app.send_command("stats")
    assert commands_seen == ["stats"]
    assert app.max_displayed == 5


def test_connector_decorator_rejects_unrelated_object():
    @connector(object())  # not a HistoryConnector or TransportConnector
    class MyApp(ChatApp):
        pass

    with pytest.raises(TypeError):
        MyApp()


# === JsonlHistoryConnector (reference implementation) ==============================


@pytest.mark.asyncio
async def test_jsonl_history_round_trips_messages(tmp_path):
    path = tmp_path / "chat.jsonl"
    app1 = ChatApp()
    app1.connect_history(JsonlHistoryConnector(path))
    async with app1.run_test():
        app1.send_message("hello")
        app1.receive_message("hi there", reply_to="msg-1")

    app2 = ChatApp()
    app2.connect_history(JsonlHistoryConnector(path))
    async with app2.run_test():
        assert [(m.id, m.text, m.is_sent_by_me) for m in app2.messages] == [
            ("msg-1", "hello", True),
            ("msg-2", "hi there", False),
        ]
        assert app2.get_replies("msg-1") == ["msg-2"]


def test_jsonl_history_load_on_missing_file_returns_empty(tmp_path):
    conn = JsonlHistoryConnector(tmp_path / "does-not-exist.jsonl")
    assert conn.load() == []


# === CallbackTransportConnector (reference implementation) =========================


def test_callback_transport_push_without_start_is_a_noop():
    """push() before start() (no on_receive registered yet) must not raise."""
    transport = CallbackTransportConnector(send_fn=lambda msg: None)
    transport.push("nobody is listening")  # should not raise


def test_callback_transport_stop_clears_receiver():
    received = []
    transport = CallbackTransportConnector(send_fn=lambda msg: None)
    transport.start(lambda text, reply_to: received.append(text))
    transport.push("one")
    transport.stop()
    transport.push("two")
    assert received == ["one"]
