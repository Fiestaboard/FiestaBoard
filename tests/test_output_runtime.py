"""``OutputRuntime``: core owns each board's send lock and cancel token.

The contract moved out of the old clients' ``TransitionRenderMixin`` unchanged:

- a new run signals the in-flight run's token *before* it waits on the lock,
  so a running transition is preempted rather than waited out;
- every run gets a fresh token, so a signal meant for the previous run can
  never pre-cancel the next one, and the preempted run keeps its own
  (signalled) token;
- the lock is re-entrant, so render() → send_characters() never self-deadlocks.

And the ownership: the engine's ``BoardRuntime`` creates one and binds it to
its client, so preempting a board no longer reaches into the client.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.main import BoardRuntime
from src.outputs import OutputRuntime
from tests.first_party_drivers import local_driver, panel_driver

TIMEOUT = 5.0


def _grid(fill: int = 0) -> list[list[int]]:
    return [[fill] * 22 for _ in range(6)]


class _BlockingRunner:
    """A transition runner that holds its run until cancelled (or released)."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.cancel_events: list[threading.Event] = []
        self.cancelled: list[bool] = []

    def run(self, *, cancel_event, **_kwargs):
        self.cancel_events.append(cancel_event)
        self.started.set()
        self.cancelled.append(cancel_event.wait(TIMEOUT))
        return True, True


@pytest.fixture
def plugins_on(monkeypatch):
    monkeypatch.setattr("src.outputs.plugin_driver.transition_plugins_enabled", lambda: True)


class TestRunContract:
    def test_a_new_run_preempts_the_run_in_flight(self):
        runtime = OutputRuntime("b1")
        inside = threading.Event()
        seen: dict[str, threading.Event] = {}
        woken: list[bool] = []

        def first() -> None:
            with runtime.run() as token:
                seen["first"] = token
                inside.set()
                # True only if signalled; a timeout means it was waited out.
                woken.append(token.wait(TIMEOUT))

        t = threading.Thread(target=first)
        t.start()
        assert inside.wait(TIMEOUT)

        with runtime.run() as second:
            seen["second"] = second
        t.join(TIMEOUT)

        assert woken == [True], "the first run was waited out, not told to stop"
        assert seen["first"].is_set()

    def test_each_run_gets_a_fresh_unsignalled_token(self):
        runtime = OutputRuntime("b1")
        with runtime.run() as first:
            pass
        with runtime.run() as second:
            assert second is not first
            assert not second.is_set(), "the signal meant for the previous run pre-cancelled this one"

    def test_the_preempted_run_keeps_its_signalled_token(self):
        runtime = OutputRuntime("b1")
        with runtime.run() as first:
            pass
        with runtime.run():
            pass
        assert first.is_set()
        assert runtime.cancel_event is not first

    def test_preempt_signals_the_current_token_without_taking_the_lock(self):
        runtime = OutputRuntime("b1")
        holding = threading.Event()
        release = threading.Event()

        def hold() -> None:
            with runtime.send_lock:
                holding.set()
                release.wait(TIMEOUT)

        t = threading.Thread(target=hold)
        t.start()
        assert holding.wait(TIMEOUT)
        try:
            current = runtime.cancel_event
            runtime.preempt()  # must not block on the held lock
            assert current.is_set()
        finally:
            release.set()
            t.join(TIMEOUT)

    def test_the_send_lock_is_reentrant_inside_a_run(self):
        runtime = OutputRuntime("b1")
        done = threading.Event()

        def nested() -> None:
            with runtime.run():
                with runtime.send_lock:
                    with runtime.send_lock:
                        done.set()

        t = threading.Thread(target=nested, daemon=True)
        t.start()
        assert done.wait(TIMEOUT), "nested acquisition deadlocked"


class TestClientUsesItsRuntime:
    def test_preempting_the_runtime_stops_a_clients_plugin_transition(self, plugins_on):
        runtime = OutputRuntime("panel")
        client = panel_driver("flagship")
        client.set_output_runtime(runtime)
        runner = _BlockingRunner()
        client.set_transition_runner(runner)

        t = threading.Thread(target=client.render, args=(_grid(1),), kwargs={"strategy": "plugin:wipe"})
        t.start()
        assert runner.started.wait(TIMEOUT)
        runtime.preempt()
        t.join(TIMEOUT)

        assert runner.cancelled == [True]
        assert runner.cancel_events[0].is_set()

    def test_a_concurrent_render_preempts_and_then_runs_with_a_fresh_token(self, plugins_on):
        runtime = OutputRuntime("panel")
        client = panel_driver("flagship")
        client.set_output_runtime(runtime)
        runner = _BlockingRunner()
        client.set_transition_runner(runner)

        t = threading.Thread(target=client.render, args=(_grid(1),), kwargs={"strategy": "plugin:wipe"})
        t.start()
        assert runner.started.wait(TIMEOUT)
        client.render(_grid(2))  # a plain send arriving mid-transition
        t.join(TIMEOUT)

        assert runner.cancelled == [True]
        assert runtime.cancel_event is not runner.cancel_events[0]
        assert not runtime.cancel_event.is_set()
        assert client.read_current_message() == _grid(2)

    @patch("requests.post")
    def test_preempting_the_runtime_abandons_a_send_retry_backoff(self, mock_post, monkeypatch):
        # A backoff far longer than the test: only the preempt can end it.
        monkeypatch.setattr("plugins.vestaboard.tiles.SEND_RETRY_BACKOFF_SECONDS", 60.0)
        runtime = OutputRuntime("b1")
        client = local_driver("test_key", "192.0.2.10")
        client.set_output_runtime(runtime)
        attempted = threading.Event()

        def refuse(*_a, **_k):
            attempted.set()
            raise requests.exceptions.ConnectionError("connection refused")

        mock_post.side_effect = refuse
        result: list = []
        t = threading.Thread(target=lambda: result.append(client.send_characters(_grid(1))))
        t.start()
        assert attempted.wait(TIMEOUT)
        runtime.preempt()
        t.join(TIMEOUT)

        assert result == [(False, False)]
        assert mock_post.call_count == 1, "the retry ran after the board was preempted"

    def test_an_unbound_client_has_its_own_runtime(self):
        a = panel_driver("flagship")
        b = panel_driver("flagship")
        a_token = a._output_runtime.cancel_event
        b._output_runtime.cancel_event.set()
        assert not a_token.is_set()


class TestBoardRuntimeOwnsIt:
    def test_board_runtime_binds_its_output_runtime_to_the_client(self, plugins_on):
        client = panel_driver("flagship")
        rt = BoardRuntime(client=client, board_id="panel")
        runner = _BlockingRunner()
        client.set_transition_runner(runner)

        t = threading.Thread(target=client.render, args=(_grid(1),), kwargs={"strategy": "plugin:wipe"})
        t.start()
        assert runner.started.wait(TIMEOUT)
        rt.output.preempt()
        t.join(TIMEOUT)

        assert runner.cancelled == [True]

    def test_assigning_a_client_later_binds_it_too(self):
        rt = BoardRuntime(client=None, board_id="b1")
        client = MagicMock()
        rt.client = client
        client.set_output_runtime.assert_called_once_with(rt.output)

    def test_each_board_runtime_has_its_own_output_runtime(self):
        a = BoardRuntime(client=None, board_id="a")
        b = BoardRuntime(client=None, board_id="b")
        assert a.output is not b.output
        assert a.output.board_id == "a"
