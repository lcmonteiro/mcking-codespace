"""Tests for chatinho's connector concept.

Two independent connector types:

- ``HistoryConnector`` — loads past messages on startup, saves every
  message (sent or received) as it happens.
- ``TransportConnector`` — sends outgoing messages, delivers incoming
  ones into the running app.

Both attach via ``app.connect_history()`` / ``app.connect_transport()``,
usable either as a decorator on a zero-argument connector class or as a
plain call with an already-built instance.
"""

import pytest

from chatinho import (
    CallbackTransportConnector,
    ChatApp,
    HistoryConnector,
    JsonlHistoryConnector,
    TransportConnector,
)


class MemoryHistory(HistoryConnector):
    """In-memory HistoryConnector for tests: records every save() call."""

    def __init__(self, initial=None):
        self._initial = list(initial or [])
        self.saved = []

    def load(self):
        return list(self._initial)

    def save(self, message):
        self.saved.append(message)


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
    started = []

    class Recorder(TransportConnector):
        def start(self, on_receive):
            started.append(True)

        def send(self, message):
            pass

    app = ChatApp()
    app.connect_transport(Recorder())
    async with app.run_test():
        assert started == [True]


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
    events = []

    class Recorder(TransportConnector):
        def start(self, on_receive):
            events.append("started")

        def send(self, message):
            pass

    app = ChatApp()
    async with app.run_test():
        app.connect_transport(Recorder())  # attached after mount
    assert events == ["started"]


@pytest.mark.asyncio
async def test_transport_stop_called_on_unmount():
    events = []

    class Recorder(TransportConnector):
        def start(self, on_receive):
            events.append("started")

        def send(self, message):
            pass

        def stop(self):
            events.append("stopped")

    app = ChatApp()
    app.connect_transport(Recorder())
    async with app.run_test():
        pass
    assert events == ["started", "stopped"]


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
    connector = JsonlHistoryConnector(tmp_path / "does-not-exist.jsonl")
    assert connector.load() == []


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
