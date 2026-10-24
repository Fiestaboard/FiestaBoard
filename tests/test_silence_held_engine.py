"""Held delivery through v9's actual per-board engine and worker."""

import importlib
import threading
import time
from datetime import UTC, datetime

import pytest

from src import silence_queue
from src.main import BoardRuntime, DisplayService
from src.pages.models import PageUpdate
from src.pages.service import get_page_service
from src.send_outcome import SendOutcome
from tests.helpers import decode_board_rows
from tests.test_silence_send_integration import sends as sends


@pytest.fixture
def engine(sends, monkeypatch):
    service = DisplayService()
    service.runtimes = {bid: BoardRuntime(client=c, board_id=bid) for bid, c in sends.clients.items()}
    service._primary_board_id = sends.boards[0]["id"]
    monkeypatch.setattr(service, "_check_trigger_override", lambda: None)
    monkeypatch.setattr(service, "request_board_refresh", lambda: None)
    for board in sends.boards:
        sends.settings.set_schedule_enabled(False, board_id=board["id"])
    sends.settings.set_active_page_id(sends.page.id)
    yield service
    service.wait_until_idle()
    for rt in service.runtimes.values():
        if rt.send_worker:
            rt.send_worker.stop()


def drive(engine, sends, index=0):
    board = sends.boards[index]
    return engine.check_and_send_for_board(
        board["id"], engine.runtimes[board["id"]], is_primary=index == 0, board=board
    )


@pytest.mark.parametrize("kind", ["text", "lines", "grid", "page", "display"])
def test_restart_delivers_each_kind_at_silence_exit(engine, sends, monkeypatch, kind):
    bid = sends.boards[0]["id"]
    factories = {
        "text": lambda: silence_queue.HeldSend.text("GOOD MORNING", board_id=bid),
        "lines": lambda: silence_queue.HeldSend.lines(["GOOD", "MORNING"], board_id=bid),
        "grid": lambda: silence_queue.HeldSend.grid([[1] * 22 for _ in range(6)], board_id=bid),
        "page": lambda: silence_queue.HeldSend.page(sends.page.id, board_id=bid),
        "display": lambda: silence_queue.HeldSend.display("weather", board_id=bid),
    }
    from types import SimpleNamespace

    monkeypatch.setattr(
        "src.displays.service.get_display_service",
        lambda: SimpleNamespace(get_display=lambda _: SimpleNamespace(available=True, formatted="PLUGIN")),
    )
    silence_queue.hold(factories[kind]())
    importlib.reload(silence_queue)
    if kind == "page":
        get_page_service().update_page(sends.page.id, PageUpdate(template=["FRESH"]))
    sends.clock.set(datetime(2026, 10, 25, 8, tzinfo=UTC))
    assert drive(engine, sends) is True
    assert silence_queue.peek(bid) is None
    grid = sends.clients[bid].render.call_args.args[0]
    rows = decode_board_rows(grid)
    assert (
        rows[0].strip()
        == {"text": "GOOD MORNING", "lines": "GOOD", "grid": "A" * 22, "page": "FRESH", "display": "PLUGIN"}[kind]
    )


@pytest.mark.parametrize("failure", ["offline", "throttle", "pause", "ui"])
def test_failed_or_blocked_delivery_retries_without_consuming(engine, sends, failure):
    bid = sends.boards[0]["id"]
    held = silence_queue.HeldSend.text("RETRY", board_id=bid)
    silence_queue.hold(held)
    sends.clock.set(datetime(2026, 10, 25, 8, tzinfo=UTC))
    if failure == "pause":
        sends.settings.set_paused(True, board_id=bid)
    elif failure == "ui":
        sends.settings.set_output_target("ui")
    else:
        sends.clients[bid].render.return_value = (
            (False, False) if failure == "offline" else SendOutcome(True, False, True, 3, 15)
        )
    assert drive(engine, sends) is False
    assert silence_queue.peek(bid) == held
    sends.settings.set_paused(False, board_id=bid)
    sends.settings.set_output_target("both")
    sends.clients[bid].render.return_value = (True, True)
    assert drive(engine, sends) is True
    assert silence_queue.peek(bid) is None


def test_secondary_has_own_dimensions_and_does_not_consume_primary(engine, sends):
    a, b = [board["id"] for board in sends.boards]
    silence_queue.hold(silence_queue.HeldSend.text("PRIMARY", board_id=a))
    silence_queue.hold(silence_queue.HeldSend.text("ONE TWO THREE FOUR FIVE", board_id=b))
    sends.clock.set(datetime(2026, 10, 25, 8, tzinfo=UTC))
    assert drive(engine, sends, 1) is True
    rows = decode_board_rows(sends.clients[b].render.call_args.args[0])
    assert len(rows) == 3
    assert rows[0].strip() == "ONE TWO THREE"
    assert rows[1].strip() == "FOUR FIVE"
    assert silence_queue.peek(a).payload == "PRIMARY"
    assert silence_queue.peek(b) is None


def test_older_delivery_preserves_newer_queued_during_send(engine, sends):
    bid = sends.boards[0]["id"]
    silence_queue.hold(silence_queue.HeldSend.text("OLD", board_id=bid))
    newer = silence_queue.HeldSend.text("NEW", board_id=bid)

    def deliver(*args, **kwargs):
        assert decode_board_rows(args[0])[0].strip() == "OLD"
        silence_queue.hold(newer)
        return True, True

    sends.clients[bid].render.side_effect = deliver
    sends.clock.set(datetime(2026, 10, 25, 8, tzinfo=UTC))
    assert drive(engine, sends) is True
    assert silence_queue.peek(bid) == newer


def test_expired_intent_does_not_replace_active_page(engine, sends):
    bid = sends.boards[0]["id"]
    silence_queue.hold(silence_queue.HeldSend("text", "STALE", bid, time.time() - 86401))
    sends.clock.set(datetime(2026, 10, 25, 8, tzinfo=UTC))
    drive(engine, sends)
    assert silence_queue.peek(bid) is None
    assert decode_board_rows(sends.clients[bid].render.call_args.args[0])[0].strip() == "HELLO"


def test_delivered_message_survives_unchanged_tick_then_yields_to_page_change(engine, sends):
    bid = sends.boards[0]["id"]
    silence_queue.hold(silence_queue.HeldSend.text("KEEP SHOWING", board_id=bid))
    sends.clock.set(datetime(2026, 10, 25, 8, tzinfo=UTC))
    assert drive(engine, sends) is True
    assert decode_board_rows(sends.clients[bid].render.call_args.args[0])[0].strip() == "KEEP SHOWING"
    assert drive(engine, sends) is False
    assert drive(engine, sends) is False
    assert sends.clients[bid].render.call_count == 1
    get_page_service().update_page(sends.page.id, PageUpdate(template=["CHANGED"]))
    assert drive(engine, sends) is True
    assert decode_board_rows(sends.clients[bid].render.call_args.args[0])[0].strip() == "CHANGED"


@pytest.mark.parametrize("change", ["discard", "replace", "pause"])
def test_worker_rechecks_intent_and_pause_before_pending_delivery(engine, sends, change):
    bid = sends.boards[0]["id"]
    rt = engine.runtimes[bid]
    started, release = threading.Event(), threading.Event()

    def blocker():
        started.set()
        assert release.wait(5)
        return True, True

    engine._dispatch_send(
        rt, bid, key=("barrier",), send=blocker, on_complete=lambda *args: True, wait=False, sink=None
    )
    assert started.wait(2)
    old = silence_queue.HeldSend.text("OLD", board_id=bid)
    newer = silence_queue.HeldSend.text("NEW", board_id=bid)
    try:
        silence_queue.hold(old)
        sends.clock.set(datetime(2026, 10, 25, 8, tzinfo=UTC))
        assert engine.check_and_send_for_board(bid, rt, board=sends.boards[0], is_primary=True, wait=False)
        if change == "discard":
            silence_queue.discard(bid)
        elif change == "replace":
            silence_queue.hold(newer)
        else:
            sends.settings.set_paused(True, board_id=bid)
    finally:
        release.set()
    assert engine.wait_until_idle()
    sends.clients[bid].render.assert_not_called()
    assert silence_queue.peek(bid) == {"discard": None, "replace": newer, "pause": old}[change]
