"""The send verdict is per call, not a flag read after the fact (#1931 review).

``BoardClient`` reports a throttled write and an unchanged-content skip with
the same ``(True, False)``. The first fix for #1931 told them apart by
reading ``client.last_send_throttled`` *after* ``render()`` had released the
per-board send lock — and a concurrent sender on the same client (the engine
tick, a BoardSendWorker job, a debug write) can reset or set that flag in the
gap, so the executor could answer ``ok(skipped=True)`` for a dropped write or
429 for an unchanged one.

The verdict now travels with the call: ``_admit_send`` decides it, and
``send_characters`` / ``send_text`` / ``render`` hand it back as a
:class:`~src.send_outcome.SendOutcome` behind ``with_outcome=True``. Every
existing ``(success, was_sent)`` caller is untouched.
"""

from __future__ import annotations

import threading
from unittest.mock import Mock, patch

import pytest

from src.board_client import BoardClient

POST = "src.board_client.requests.post"


def _grid(fill: int) -> list[list[int]]:
    return [[fill] * 22 for _ in range(6)]


def _ok_response() -> Mock:
    return Mock(raise_for_status=Mock())


def throttled_cloud_client(now: dict, *, elapsed: float = 0.0) -> BoardClient:
    """A REAL RW Cloud client whose next send lands inside its 15s floor.

    One delivered write opens the window at ``now["t"]``; the clock is then
    advanced by ``elapsed`` so the remaining window is ``15 - elapsed``.
    Shared by the v1 / MCP / debug throttle tests so none of them has to
    fake the verdict — a stub that sets a flag would only re-encode the
    implementation this module exists to retire.
    """
    client = BoardClient(api_key="test_key", use_cloud=True, _time_func=lambda: now["t"])
    with patch(POST, return_value=_ok_response()):
        assert client.send_characters(_grid(1)) == (True, True)
    now["t"] += elapsed
    return client


# ---------------------------------------------------------------------------
# The race
# ---------------------------------------------------------------------------


def test_the_executor_verdict_survives_a_concurrent_send_in_the_gap(monkeypatch):
    """Two threads, one client, deterministic via Events.

    Thread A (the executor) renders inside the window: the client drops the
    write. Before A settles its verdict, thread B — standing in for the
    engine tick — waits out the window and delivers a different grid on the
    same client, which resets the instance flag. A's answer must still be
    "dropped, retry after N": the verdict belongs to A's call.
    """
    from src import ops
    from src.displays import messages

    now = {"t": 1000.0}
    client = throttled_cloud_client(now, elapsed=5.0)
    service = Mock()
    service.vb_client = client
    service.get_board_client.return_value = client
    monkeypatch.setattr("src.api_server.get_service", lambda: service)

    verdict_taken = threading.Event()
    other_sender_done = threading.Event()
    real_render_message = messages.render_message

    def render_then_yield(*args, **kwargs):
        result = real_render_message(*args, **kwargs)  # the send lock is released here
        verdict_taken.set()
        assert other_sender_done.wait(5), "the concurrent sender never ran"
        return result

    monkeypatch.setattr(messages, "render_message", render_then_yield)

    def other_sender():
        assert verdict_taken.wait(5)
        now["t"] += 20.0  # the window has passed for this thread
        with patch(POST, return_value=_ok_response()):
            assert client.send_characters(_grid(2), force=True) == (True, True)
        other_sender_done.set()

    thread = threading.Thread(target=other_sender, name="engine-tick")
    thread.start()
    result = ops.executors.send_message("WORLD")
    thread.join(5)

    assert result["status"] == "error", f"a dropped write was settled as: {result}"
    assert result["retry_after_seconds"] == 10, result
    assert client.last_send_throttled is False, "the concurrent send did run — the flag alone would have lied"


# ---------------------------------------------------------------------------
# The stale flag
# ---------------------------------------------------------------------------


class _PreemptedRunner:
    """A transition runner cancelled before its first frame: it never sends."""

    def run(self, **kwargs):
        return (True, False)


def test_a_preempted_plugin_transition_does_not_inherit_a_stale_throttle(monkeypatch):
    now = {"t": 1000.0}
    client = throttled_cloud_client(now, elapsed=5.0)
    assert client.send_characters(_grid(2)) == (True, False)
    assert client.last_send_throttled is True, "precondition: the previous tick was throttled"

    client.set_transition_runner(_PreemptedRunner())
    monkeypatch.setattr(BoardClient, "_transition_plugins_beta_enabled", staticmethod(lambda: True))

    assert client.render(_grid(3), strategy="plugin:fade") == (True, False)

    assert client.last_send_throttled is False, "a render that sent nothing reported the previous call's throttle"


def test_a_preempted_plugin_transition_reports_not_throttled_in_its_outcome(monkeypatch):
    now = {"t": 1000.0}
    client = throttled_cloud_client(now, elapsed=5.0)
    assert client.send_characters(_grid(2)) == (True, False)
    client.set_transition_runner(_PreemptedRunner())
    monkeypatch.setattr(BoardClient, "_transition_plugins_beta_enabled", staticmethod(lambda: True))

    outcome = client.render(_grid(3), strategy="plugin:fade", with_outcome=True)

    assert (outcome.success, outcome.was_sent, outcome.throttled) == (True, False, False)


# ---------------------------------------------------------------------------
# The per-call outcome
# ---------------------------------------------------------------------------


def test_send_characters_outcome_reports_the_remaining_window_not_the_whole_floor():
    now = {"t": 1000.0}
    client = throttled_cloud_client(now, elapsed=5.0)

    outcome = client.send_characters(_grid(2), with_outcome=True)

    assert outcome.success is True
    assert outcome.was_sent is False
    assert outcome.throttled is True
    assert outcome.retry_after_seconds == 10, "15s floor, 5s elapsed: 10s remain"
    assert outcome.floor_seconds == 15


def test_send_text_outcome_shares_the_verdict():
    now = {"t": 1000.0}
    client = throttled_cloud_client(now, elapsed=14.2)

    outcome = client.send_text("later", with_outcome=True)

    assert outcome.throttled is True
    assert outcome.retry_after_seconds == 1, "0.8s remain: rounded up, never 0"


def test_an_unchanged_skip_outcome_is_not_throttled():
    now = {"t": 1000.0}
    client = throttled_cloud_client(now, elapsed=20.0)

    outcome = client.send_characters(_grid(1), with_outcome=True)

    assert (outcome.success, outcome.was_sent, outcome.throttled) == (True, False, False)
    assert outcome.retry_after_seconds is None


def test_a_delivered_send_outcome_is_sent_and_not_throttled():
    now = {"t": 1000.0}
    client = throttled_cloud_client(now, elapsed=20.0)

    with patch(POST, return_value=_ok_response()):
        outcome = client.render(_grid(2), with_outcome=True)

    assert (outcome.success, outcome.was_sent, outcome.throttled) == (True, True, False)


def test_without_with_outcome_the_two_tuple_contract_is_unchanged():
    now = {"t": 1000.0}
    client = throttled_cloud_client(now, elapsed=5.0)

    result = client.send_characters(_grid(2))

    assert result == (True, False)
    assert type(result) is tuple and len(result) == 2


def test_the_guard_reads_the_outcome_not_the_client():
    """``raise_if_throttled`` takes the per-call outcome; a client whose flag
    says throttled but whose outcome says delivered is delivered."""
    from fastapi import HTTPException

    from src.board_guards import raise_if_throttled
    from src.send_outcome import SendOutcome

    raise_if_throttled(SendOutcome(True, True))  # no raise
    raise_if_throttled((True, False))  # a bare tuple has no throttle verdict: unchanged

    with pytest.raises(HTTPException) as refused:
        raise_if_throttled(SendOutcome(True, False, throttled=True, retry_after_seconds=7, floor_seconds=15))

    assert refused.value.status_code == 429
    assert refused.value.headers == {"Retry-After": "7"}
    assert refused.value.detail == "Send skipped: the board accepts at most one message every 15s. Retry in 7s."
