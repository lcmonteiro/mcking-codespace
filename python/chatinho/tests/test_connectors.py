"""Tests for chatinho's connector concept.

No base class to subclass — a connector is any object with the right
methods:

- History connector: needs ``load()`` and ``save(message)``. Owns
  optional ``on_loaded``/``on_saved`` hooks — these mark a milestone
  the connector can't see on its own (ChatApp applying loaded messages
  / recording a saved one), so they earn their keep.
- Transport connector: needs ``start(on_receive)`` and ``send(message)``.
  Owns an optional ``stop()`` only — there's no ``on_started``/
  ``on_stopped``, since those would fire with nothing happening in
  between "start()/stop() ran" and "the hook fires": a connector
  author can just put that reaction directly in start()/stop().

Attach one to a ``ChatApp`` subclass with the ``@connector(...)`` class
decorator — every instance gets it, automatically, before ``on_mount``.
``@history_connector`` / ``@transport_connector`` validate a plain class
has the required methods, raising ``TypeError`` at class-definition
time if not.
"""

import pytest

from chatinho import (
    CallbackTransportConnector,
    ChatApp,
    ChatMessage,
    JsonlHistoryConnector,
    connector,
    history_connector,
    is_history_connector,
    is_transport_connector,
    transport_connector,
)


@history_connector
class MemoryHistory:
    """In-memory history connector for tests: records save()/hook calls."""

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


@transport_connector
class MemoryTransport:
    """In-memory transport connector for tests: records calls/hooks."""

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

    def push(self, text, reply_to=None):
        assert self._on_receive is not None
        self._on_receive(text, reply_to)


# === History connector: wiring via @connector ======================================


@pytest.mark.asyncio
async def test_connector_loads_history_on_mount():
    history = MemoryHistory()

    @connector(history)
    class App(ChatApp):
        pass

    async with App().run_test():
        assert history.loaded_calls == [[]]  # load() ran, nothing to load


@pytest.mark.asyncio
async def test_connector_loads_past_messages_into_app():
    seed = ChatApp()
    async with seed.run_test():
        original_id = seed.send_message("hi")
    history = MemoryHistory(initial=list(seed.messages))

    @connector(history)
    class App(ChatApp):
        pass

    async with App().run_test() as pilot:
        app = pilot.app
        assert len(app.messages) == 1
        assert app.messages[0].text == "hi"
        assert app.messages[0].id == original_id


@pytest.mark.asyncio
async def test_loaded_history_is_not_re_saved():
    seed = ChatApp()
    async with seed.run_test():
        seed.send_message("hi")
    history = MemoryHistory(initial=list(seed.messages))

    @connector(history)
    class App(ChatApp):
        pass

    async with App().run_test():
        pass
    assert history.saved == []


@pytest.mark.asyncio
async def test_send_and_receive_trigger_save():
    history = MemoryHistory()

    @connector(history)
    class App(ChatApp):
        pass

    async with App().run_test() as pilot:
        app = pilot.app
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

    @connector(history)
    class App(ChatApp):
        pass

    async with App().run_test() as pilot:
        new_id = pilot.app.send_message("three")
    assert new_id == "msg-3"


@pytest.mark.asyncio
async def test_non_standard_history_ids_are_ignored_for_id_continuation():
    """A connector backed by e.g. a database may hand back non-'msg-N' ids."""
    foreign = ChatMessage(id="uuid-abc-123", text="from elsewhere")
    history = MemoryHistory(initial=[foreign])

    @connector(history)
    class App(ChatApp):
        pass

    async with App().run_test() as pilot:
        app = pilot.app
        assert app.messages[0].id == "uuid-abc-123"  # preserved as-is
        new_id = app.send_message("hi")
    assert new_id == "msg-1"  # foreign id didn't perturb the counter


@pytest.mark.asyncio
async def test_id_continuation_survives_a_mix_of_standard_and_foreign_ids():
    mixed = [
        ChatMessage(id="msg-5", text="a"),
        ChatMessage(id="uuid-xyz", text="b"),
        ChatMessage(id="msg-2", text="c"),  # lower than msg-5: must not regress the counter
    ]
    history = MemoryHistory(initial=mixed)

    @connector(history)
    class App(ChatApp):
        pass

    async with App().run_test() as pilot:
        new_id = pilot.app.send_message("hi")
    assert new_id == "msg-6"


# === Transport connector: wiring via @connector =====================================


@pytest.mark.asyncio
async def test_connector_starts_transport_on_mount():
    transport = MemoryTransport()

    @connector(transport)
    class App(ChatApp):
        pass

    async with App().run_test():
        assert "started" in transport.events


@pytest.mark.asyncio
async def test_sending_calls_transport_send():
    sent = []
    transport = CallbackTransportConnector(send_fn=lambda msg: sent.append(msg.text))

    @connector(transport)
    class App(ChatApp):
        pass

    async with App().run_test() as pilot:
        pilot.app.send_message("hello transport")
    assert sent == ["hello transport"]


@pytest.mark.asyncio
async def test_transport_push_delivers_incoming_message():
    transport = CallbackTransportConnector(send_fn=lambda msg: None)

    @connector(transport)
    class App(ChatApp):
        pass

    async with App().run_test() as pilot:
        app = pilot.app
        transport.push("from the wire", reply_to=None)
        assert len(app.messages) == 1
        assert app.messages[0].text == "from the wire"
        assert app.messages[0].is_sent_by_me is False


@pytest.mark.asyncio
async def test_received_messages_are_not_sent_back_through_transport():
    sent = []
    transport = CallbackTransportConnector(send_fn=lambda msg: sent.append(msg.text))

    @connector(transport)
    class App(ChatApp):
        pass

    async with App().run_test():
        transport.push("incoming, should not echo")
    assert sent == []


@pytest.mark.asyncio
async def test_transport_stopped_on_unmount():
    transport = MemoryTransport()

    @connector(transport)
    class App(ChatApp):
        pass

    async with App().run_test():
        pass
    assert transport.events == ["started", "stopped"]


@pytest.mark.asyncio
async def test_transport_stop_is_optional():
    """A transport connector with no stop() must not crash on_unmount."""

    @transport_connector
    class NoStop:
        def start(self, on_receive):
            pass

        def send(self, message):
            pass

    @connector(NoStop)
    class App(ChatApp):
        pass

    async with App().run_test():
        pass  # unmounting must not raise


@pytest.mark.asyncio
async def test_on_started_and_on_stopped_are_never_called():
    """There's no on_started/on_stopped hook — start()/stop() are the whole story."""
    calls = []

    @transport_connector
    class Recorder:
        def start(self, on_receive):
            calls.append("start")

        def send(self, message):
            pass

        def stop(self):
            calls.append("stop")

        def on_started(self):
            calls.append("on_started")  # defined, but ChatApp must never call it

        def on_stopped(self):
            calls.append("on_stopped")  # defined, but ChatApp must never call it

    @connector(Recorder)
    class App(ChatApp):
        pass

    async with App().run_test():
        pass
    assert calls == ["start", "stop"]


@pytest.mark.asyncio
async def test_bare_chat_app_subclass_is_unaffected():
    """No connector attached: sending/receiving never touches connector plumbing."""

    class PlainApp(ChatApp):
        pass

    async with PlainApp().run_test() as pilot:
        pilot.app.send_message("hi")  # must not raise


# === history_connector / transport_connector: capability validation ================


def test_history_connector_accepts_class_with_load_and_save():
    @history_connector
    class Recorder:
        def load(self):
            return []

        def save(self, message):
            pass

    assert is_history_connector(Recorder())


def test_history_connector_rejects_class_missing_save():
    with pytest.raises(TypeError, match="load\\(\\) and save\\(\\)"):

        @history_connector
        class Recorder:
            def load(self):
                return []


def test_history_connector_rejects_class_missing_load():
    with pytest.raises(TypeError):

        @history_connector
        class Recorder:
            def save(self, message):
                pass


def test_transport_connector_accepts_class_with_start_and_send():
    @transport_connector
    class Recorder:
        def start(self, on_receive):
            pass

        def send(self, message):
            pass

    assert is_transport_connector(Recorder())


def test_transport_connector_rejects_class_missing_send():
    with pytest.raises(TypeError, match="start\\(\\) and send\\(\\)"):

        @transport_connector
        class Recorder:
            def start(self, on_receive):
                pass


def test_is_history_connector_false_for_unrelated_object():
    assert is_history_connector(object()) is False


def test_is_transport_connector_false_for_unrelated_object():
    assert is_transport_connector(object()) is False


# === connector(...): declarative attachment on a ChatApp subclass ==================


@pytest.mark.asyncio
async def test_connector_lazily_instantiates_class_with_args():
    seen = []

    @history_connector
    class Recorder:
        def __init__(self, tag):
            self.tag = tag

        def load(self):
            return []

        def save(self, message):
            seen.append((self.tag, message.text))

    @connector(Recorder, "tagged")
    class App(ChatApp):
        pass

    async with App().run_test() as pilot:
        pilot.app.send_message("hi")
    assert seen == [("tagged", "hi")]


@pytest.mark.asyncio
async def test_connector_lazy_instantiation_is_per_app_instance():
    """Each App() gets its own connector instance, not a shared one."""

    @history_connector
    class Recorder:
        def load(self):
            return []

        def save(self, message):
            pass

    @connector(Recorder)
    class App(ChatApp):
        pass

    async with App().run_test() as pilot_a, App().run_test() as pilot_b:
        assert pilot_a.app._history is not pilot_b.app._history


@pytest.mark.asyncio
async def test_connector_accepts_an_already_built_instance():
    history = MemoryHistory()

    @connector(history)
    class App(ChatApp):
        pass

    async with App().run_test() as pilot:
        pilot.app.send_message("hi")
    assert [m.text for m in history.saved] == ["hi"]


@pytest.mark.asyncio
async def test_connector_stacks_history_and_transport():
    history = MemoryHistory()
    transport = MemoryTransport()

    @connector(history)
    @connector(transport)
    class App(ChatApp):
        pass

    async with App().run_test() as pilot:
        pilot.app.send_message("hi")
    assert [m.text for m in history.saved] == ["hi"]
    assert [m.text for m in transport.sent] == ["hi"]


@pytest.mark.asyncio
async def test_connector_preserves_constructor_arguments():
    """@connector-decorated apps still accept ChatApp's normal constructor args."""
    commands_seen = []
    history = MemoryHistory()

    @connector(history)
    class App(ChatApp):
        pass

    app = App(command_handler=commands_seen.append, max_displayed=5)
    async with app.run_test():
        app.send_command("stats")
    assert commands_seen == ["stats"]
    assert app.max_displayed == 5


def test_connector_rejects_unrelated_object():
    @connector(object())  # neither a history nor a transport connector
    class App(ChatApp):
        pass

    with pytest.raises(TypeError):
        App()


# === JsonlHistoryConnector (reference implementation) ==============================


@pytest.mark.asyncio
async def test_jsonl_history_round_trips_messages(tmp_path):
    path = tmp_path / "chat.jsonl"

    @connector(JsonlHistoryConnector, path)
    class App1(ChatApp):
        pass

    async with App1().run_test() as pilot:
        app = pilot.app
        app.send_message("hello")
        app.receive_message("hi there", reply_to="msg-1")

    @connector(JsonlHistoryConnector, path)
    class App2(ChatApp):
        pass

    async with App2().run_test() as pilot:
        app = pilot.app
        assert [(m.id, m.text, m.is_sent_by_me) for m in app.messages] == [
            ("msg-1", "hello", True),
            ("msg-2", "hi there", False),
        ]
        assert app.get_replies("msg-1") == ["msg-2"]


def test_jsonl_history_load_on_missing_file_returns_empty(tmp_path):
    conn = JsonlHistoryConnector(tmp_path / "does-not-exist.jsonl")
    assert conn.load() == []


def test_jsonl_history_connector_passes_capability_check():
    assert is_history_connector(JsonlHistoryConnector("unused.jsonl"))


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


def test_callback_transport_connector_passes_capability_check():
    assert is_transport_connector(CallbackTransportConnector(send_fn=lambda msg: None))
