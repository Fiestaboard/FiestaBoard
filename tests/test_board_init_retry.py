"""Fake-clock tests for the failed-board-init retry loop (issue #1827).

A board whose client cannot be built at startup lands in
``DisplayService.board_init_errors`` (#1813) — and, before #1827, stayed
there until a human re-saved board settings. These tests pin the recovery
behavior: the board-poll thread re-attempts ONLY the failed boards, on a
per-board exponential backoff (60s doubling to a 900s cap), swaps a
successful client in without disturbing other boards' in-flight sends, and
clears the board's ``board_init_errors`` entry so GET /status shows it
healthy again.

The engine equivalence harness never starts the poll thread (its runtimes are
hand-set), so there is no run()-level golden scenario for recovery; these
tests drive ``_board_poll_loop`` itself on the test thread through a
``FakeTimeModule`` whose ``sleep`` advances the clock — deterministic,
single-threaded, no real waiting.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from src.main import DisplayService
from tests.engine_harness import (
    GoldenRecordingClient,
    SilenceOffConfigManager,
    make_board,
    make_page_service,
    make_settings_service,
)
from tests.fake_clock import FakeClock, FakeTimeModule, install_fake_time_service

T0 = datetime(2026, 7, 15, 9, 0, tzinfo=UTC)


class _NoLegacyBoardClient:
    """Stand-in for the legacy-Config BoardClient constructor: always fails.

    Keeps the all-boards-failed startup path deterministic regardless of any
    BOARD_* env vars present in the environment running the tests.
    """

    def __init__(self, *args, **kwargs):
        raise RuntimeError("no legacy board credentials in tests")


def _make_service(monkeypatch, clock, boards, factory, *, poll_interval=30, active_page_ids=None):
    """A DisplayService wired to stubs, with ``board_client_from_board_dict``
    replaced by ``factory`` and every clock seam on ``clock``."""
    service = DisplayService()
    settings = make_settings_service(
        boards=boards,
        polling_interval=15,
        active_page_ids=active_page_ids or {},
    )
    settings.get_polling_settings.return_value = SimpleNamespace(
        board_read_interval_local=poll_interval, board_read_interval_cloud=poll_interval
    )
    cm = SilenceOffConfigManager()
    install_fake_time_service(monkeypatch, clock)
    monkeypatch.setattr("src.config.get_config_manager", lambda: cm)
    monkeypatch.setattr("src.config_manager.get_config_manager", lambda: cm)
    monkeypatch.setattr("src.main.get_settings_service", lambda: settings)
    monkeypatch.setattr("src.main.board_client_from_board_dict", factory)
    monkeypatch.setattr("src.main.BoardClient", _NoLegacyBoardClient)
    monkeypatch.setattr(DisplayService, "_attach_transition_runner", staticmethod(lambda client: None))
    monkeypatch.setattr(service, "request_board_refresh", lambda *a, **k: None)
    return service, settings


def _run_poll_loop(monkeypatch, service, clock, *, until):
    """Run ``_board_poll_loop`` on this thread until the clock passes ``until``.

    The loop's ``time.sleep`` advances the fake clock; past the horizon it
    flips ``service.running`` so the loop exits on its own check.
    """
    ticks = {"n": 0}

    def on_sleep(seconds: float) -> None:
        ticks["n"] += 1
        if ticks["n"] > 10_000:
            raise AssertionError("poll loop never reached the horizon")
        clock.advance(seconds)
        if clock.utc > until:
            service.running = False

    monkeypatch.setattr("src.main.time", FakeTimeModule(clock, on_sleep=on_sleep))
    service.running = True
    service._board_poll_loop()


def test_transiently_failed_board_recovers_after_first_retry(monkeypatch):
    """A board that fails at init is retried ~60s later and rejoins the fleet.

    The stub factory raises (board unplugged) until t+45s, then succeeds. The
    poll loop (30s cadence) must re-attempt at t+60, build the client, clear
    ``board_init_errors`` and install a live runtime — after which a normal
    engine pass drives the board.
    """
    clock = FakeClock(T0)
    sink: list[dict] = []
    boards = [make_board("board-1")]

    def factory(board_dict):
        if clock.utc < T0 + timedelta(seconds=45):
            raise ConnectionError("board unplugged")
        return GoldenRecordingClient(clock, board_dict["id"], sink)

    service, _settings = _make_service(monkeypatch, clock, boards, factory, active_page_ids={"board-1": "page-static"})
    service._build_board_clients(sync_cache=False)
    assert service.board_init_errors == {"board-1": "board unplugged"}
    assert service.get_board_client("board-1") is None

    _run_poll_loop(monkeypatch, service, clock, until=T0 + timedelta(seconds=90))

    assert "board-1" not in service.board_init_errors, "recovery must clear the GET /status error"
    rt = service.runtimes.get("board-1")
    assert rt is not None and rt.client is not None, "recovered board must have a live runtime"

    # And the recovered board is drivable by a normal engine pass.
    pages = make_page_service({"page-static": "HELLO AGAIN"})
    monkeypatch.setattr("src.main.get_page_service", lambda: pages)
    monkeypatch.setattr("src.main.get_schedule_service", lambda: SimpleNamespace())
    monkeypatch.setattr(service, "_check_trigger_override", lambda: None)
    assert service.check_and_send_active_page(wait=True) is True
    assert [s["board"] for s in sink] == ["board-1"]
    assert sink[0]["rows"][0].rstrip() == "HELLO AGAIN"


def test_retry_backoff_doubles_to_cap_and_logs_quietly(monkeypatch, caplog):
    """A permanently failed board backs off 60/120/240/480/900(cap)s.

    Over one simulated hour that is exactly 7 attempts (t+60, 180, 420, 900,
    1800, 2700, 3600) — and error-level log lines only where the backoff step
    increased (4), NOT one per poll iteration (~120).
    """
    clock = FakeClock(T0)
    attempts: list[float] = []

    def factory(board_dict):
        attempts.append((clock.utc - T0).total_seconds())
        raise ConnectionError("still unplugged")

    service, _settings = _make_service(monkeypatch, clock, [make_board("board-1")], factory)
    service._build_board_clients(sync_cache=False)
    assert attempts == [0.0]  # the initial (failed) build

    with caplog.at_level(logging.DEBUG, logger="src.main"):
        _run_poll_loop(monkeypatch, service, clock, until=T0 + timedelta(seconds=3600))

    assert attempts[1:] == [60.0, 180.0, 420.0, 900.0, 1800.0, 2700.0, 3600.0]
    assert service.board_init_errors == {"board-1": "still unplugged"}

    retry_errors = [r for r in caplog.records if r.levelno == logging.ERROR and "retry" in r.getMessage().lower()]
    assert len(retry_errors) == 4, (
        "error-level retry noise must be bounded by backoff-step increases "
        f"(60->120->240->480->900), got {len(retry_errors)}: "
        f"{[r.getMessage() for r in retry_errors]}"
    )


def test_recovery_swap_does_not_disturb_other_boards_inflight_send(monkeypatch):
    """A retry landing while another board is mid-send must not touch it.

    Board-2's send worker is blocked inside a long send (Event) when board-1's
    recovery swaps a new runtime in. Board-2's runtime object and worker must
    be exactly the ones already in flight — same no-race property scenario 10
    pins for rebuilds (#1755).
    """
    clock = FakeClock(T0)
    sink: list[dict] = []
    boards = [make_board("board-1"), make_board("board-2")]
    allow_board_1 = {"ok": False}

    def factory(board_dict):
        if board_dict["id"] == "board-1" and not allow_board_1["ok"]:
            raise ConnectionError("board unplugged")
        return GoldenRecordingClient(clock, board_dict["id"], sink)

    service, _settings = _make_service(monkeypatch, clock, boards, factory)
    monkeypatch.setattr("src.main.time", FakeTimeModule(clock))
    service._build_board_clients(sync_cache=False)
    assert set(service.runtimes) == {"board-2"}
    assert "board-1" in service.board_init_errors

    # Seed the retry schedule (first pass), then make the retry due.
    service._retry_failed_board_inits()
    clock.advance(60)

    rt2 = service.runtimes["board-2"]
    started = threading.Event()
    release = threading.Event()

    def blocking_send():
        started.set()
        if not release.wait(timeout=10):
            return False, False
        return True, True

    try:
        service._dispatch_send(
            rt2,
            "board-2",
            key=("page", "page-x", "content"),
            send=blocking_send,
            on_complete=lambda success, was_sent, exc: was_sent,
            wait=False,
            sink=None,
        )
        assert started.wait(timeout=5), "board-2's worker never started the blocked send"
        worker2 = rt2.send_worker

        allow_board_1["ok"] = True
        service._retry_failed_board_inits()

        assert "board-1" in service.runtimes and service.runtimes["board-1"].client is not None
        assert "board-1" not in service.board_init_errors
        assert service.runtimes["board-2"] is rt2, "recovery must not replace an unrelated runtime"
        assert rt2.send_worker is worker2 and not worker2.stopped, (
            "recovery must not stop another board's in-flight worker"
        )
    finally:
        release.set()
    assert service.wait_until_idle(timeout=10.0, board_ids=["board-2"])


def test_retry_drops_board_removed_from_settings(monkeypatch):
    """A failed board deleted from settings stops being retried (state pruned)."""
    clock = FakeClock(T0)

    def factory(board_dict):
        raise ConnectionError("board unplugged")

    boards = [make_board("board-1"), make_board("board-2")]
    service, settings = _make_service(monkeypatch, clock, boards, factory)
    monkeypatch.setattr("src.main.time", FakeTimeModule(clock))
    service._build_board_clients(sync_cache=False)
    assert set(service.board_init_errors) == {"board-1", "board-2"}

    # board-2 disappears from settings before its first retry comes due.
    settings.get_board_settings.return_value = SimpleNamespace(boards=[boards[0]])
    service._retry_failed_board_inits()  # seeds schedules
    clock.advance(61)
    service._retry_failed_board_inits()

    assert "board-2" not in service.board_init_errors, "a deconfigured board must not report an init error"
    assert "board-2" not in service._board_retry_state
