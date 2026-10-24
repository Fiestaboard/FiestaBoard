"""Whole-branch review regressions using isolated stores and fake hardware."""

import importlib
from dataclasses import asdict
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src import silence_queue
from src.pages.service import get_page_service
from tests.test_silence_held_engine import drive
from tests.test_silence_held_engine import engine as engine
from tests.test_silence_send_integration import sends as sends


@pytest.mark.parametrize("override", [False, True])
@pytest.mark.parametrize("gate", ["pause", "silence", "ui"])
def test_active_selection_rechecks_gates_after_render(sends, monkeypatch, gate, override):
    bid = sends.boards[0]["id"]
    old = silence_queue.HeldSend.text("KEEP", board_id=bid)
    silence_queue.hold(old)
    sends.clock.set(datetime(2026, 10, 25, 8, tzinfo=UTC))
    preview = get_page_service().preview_page

    def render(*args, **kwargs):
        result = preview(*args, **kwargs)
        if gate == "pause":
            sends.settings.set_paused(True, board_id=bid)
        elif gate == "ui":
            sends.settings.set_output_target("ui")
        else:
            sends.clock.set(datetime(2026, 10, 25, 22, tzinfo=UTC))
        return result

    monkeypatch.setattr(get_page_service(), "preview_page", render)
    response = sends.http.put(
        "/settings/active-page",
        json={"page_id": sends.page.id, "board_id": bid, "override_silence": override},
    )
    assert response.status_code == 200
    assert sends.settings.get_active_page_id(board_id=bid) == sends.page.id
    should_send = gate == "silence" and override
    assert response.json()["sent_to_board"] is should_send
    if should_send:
        assert sends.clients[bid].render.call_count == 1
        assert silence_queue.peek(bid) is None
    else:
        sends.clients[bid].render.assert_not_called()
        if gate == "silence":
            assert response.json()["silenced"] is True
            assert response.json()["held"] is True
            assert silence_queue.peek(bid).payload == sends.page.id
        else:
            assert silence_queue.peek(bid) == old
            assert response.json()["paused"] is (gate == "pause")


@pytest.mark.parametrize("kind", ["deleted", "incompatible", "unavailable"])
@pytest.mark.parametrize("override", [False, True])
def test_unrenderable_hold_allows_existing_content(engine, sends, monkeypatch, kind, override):
    from src.pages.models import PageCreate
    from src.settings.service import TemporaryOverride
    from tests.helpers import decode_board_rows

    bid = sends.boards[0]["id"]
    if kind == "deleted":
        held = silence_queue.HeldSend.page("deleted-page", board_id=bid)
    elif kind == "incompatible":
        page = get_page_service().create_page(
            PageCreate(name="Note", type="template", template=["WRONG SIZE"], device_type="note")
        )
        held = silence_queue.HeldSend.page(page.id, board_id=bid)
    else:
        held = silence_queue.HeldSend.display("weather", board_id=bid)
        monkeypatch.setattr(
            "src.displays.service.get_display_service",
            lambda: SimpleNamespace(get_display=lambda *a, **kw: SimpleNamespace(available=False)),
        )
    silence_queue.hold(held)
    if override:
        sends.settings.set_temporary_override(TemporaryOverride(template=["EXPLICIT"], device_type="flagship"))
    sends.clock.set(datetime(2026, 10, 25, 8, tzinfo=UTC))
    assert drive(engine, sends) is True
    assert decode_board_rows(sends.clients[bid].render.call_args.args[0])[0].strip() == (
        "EXPLICIT" if override else "HELLO"
    )
    assert silence_queue.peek(bid) == (None if override else held)


def test_unrenderable_hold_survives_failed_override(engine, sends):
    from src.settings.service import TemporaryOverride

    bid = sends.boards[0]["id"]
    held = silence_queue.HeldSend.page("deleted", board_id=bid)
    silence_queue.hold(held)
    sends.settings.set_temporary_override(TemporaryOverride(template=["EXPLICIT"], device_type="flagship"))
    sends.clients[bid].render.return_value = (False, False)
    sends.clock.set(datetime(2026, 10, 25, 8, tzinfo=UTC))
    assert drive(engine, sends) is False
    sends.clients[bid].render.assert_called_once()
    assert silence_queue.peek(bid) == held


@pytest.mark.parametrize("previous", [False, True])
@pytest.mark.parametrize("surface", ["legacy", "v1"])
def test_failed_hold_is_not_acknowledged_or_published(sends, monkeypatch, previous, surface):
    bid = sends.boards[0]["id"]
    old = silence_queue.HeldSend.text("OLD", board_id=bid) if previous else None
    if old:
        silence_queue.hold(old)
    with monkeypatch.context() as patch:
        patch.setattr(silence_queue, "write_json_atomic", lambda *a, **kw: (_ for _ in ()).throw(OSError("disk full")))
        url = "/send-message" if surface == "legacy" else f"/v1/boards/{bid}/message"
        response = sends.http.post(url, json={"text": "NEW"})
        assert response.status_code >= 500
        assert silence_queue.peek(bid) == old
        sends.clients[bid].render.assert_not_called()
    importlib.reload(silence_queue)
    restored = silence_queue.peek(bid)
    assert (asdict(restored) if restored else None) == (asdict(old) if old else None)


def test_failed_explicit_discard_retains_durable_intent(sends, monkeypatch):
    bid = sends.boards[0]["id"]
    old = silence_queue.HeldSend.text("KEEP", board_id=bid)
    silence_queue.hold(old)
    with monkeypatch.context() as patch:
        patch.setattr(silence_queue, "write_json_atomic", lambda *a, **kw: (_ for _ in ()).throw(OSError("read only")))
        response = sends.http.delete("/silence-queue", params={"board_id": bid})
        assert response.status_code >= 500
        assert silence_queue.peek(bid) == old
    importlib.reload(silence_queue)
    assert asdict(silence_queue.peek(bid)) == asdict(old)


@pytest.mark.parametrize("surface", ["held", "legacy", "v1", "active"])
def test_successful_write_with_failed_cleanup_is_truthful_and_does_not_replay(engine, sends, monkeypatch, surface):
    bid = sends.boards[0]["id"]
    silence_queue.hold(silence_queue.HeldSend.text("OLD", board_id=bid))
    sends.clock.set(datetime(2026, 10, 25, 8, tzinfo=UTC))
    write = silence_queue.write_json_atomic

    def reject_cleanup(path, data, **kwargs):
        if bid not in data:
            raise OSError("cleanup failed")
        return write(path, data, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(silence_queue, "write_json_atomic", reject_cleanup)
        if surface == "held":
            assert drive(engine, sends) is True
        else:
            if surface == "active":
                response = sends.http.put("/settings/active-page", json={"page_id": sends.page.id, "board_id": bid})
            else:
                url = "/send-message" if surface == "legacy" else f"/v1/boards/{bid}/message"
                response = sends.http.post(url, json={"text": "NEW"})
            assert response.status_code == 200
            assert response.json()["sent_to_board" if surface == "active" else "sent"] is True
        status = sends.http.get("/silence-status", params={"board_id": bid}).json()
        assert status["held"]["delivery_state"] == "unresolved"
    importlib.reload(silence_queue)
    assert silence_queue.peek(bid).delivery_state == "unresolved"
    sends.clients[bid].render.reset_mock()
    drive(engine, sends)
    from tests.helpers import decode_board_rows

    for call in sends.clients[bid].render.call_args_list:
        assert decode_board_rows(call.args[0])[0].strip() != "OLD"
    response = sends.http.delete("/silence-queue", params={"board_id": bid})
    assert response.status_code == 200 and response.json()["discarded"] is True
    importlib.reload(silence_queue)
    assert silence_queue.peek(bid) is None


@pytest.mark.parametrize("outcome", [(False, False), (True, False)])
def test_failed_or_throttled_delivery_restores_durable_pending(engine, sends, outcome):
    bid = sends.boards[0]["id"]
    silence_queue.hold(silence_queue.HeldSend.text("RETRY", board_id=bid))
    sends.clock.set(datetime(2026, 10, 25, 8, tzinfo=UTC))
    sends.clients[bid].render.return_value = outcome
    assert drive(engine, sends) is False
    importlib.reload(silence_queue)
    assert silence_queue.peek(bid).delivery_state == "pending"
    sends.clients[bid].render.return_value = (True, True)
    assert drive(engine, sends) is True
    assert silence_queue.peek(bid) is None


def test_interrupted_delivery_remains_unresolved_after_reload(engine, sends):
    bid = sends.boards[0]["id"]
    silence_queue.hold(silence_queue.HeldSend.text("UNCERTAIN", board_id=bid))
    sends.clock.set(datetime(2026, 10, 25, 8, tzinfo=UTC))
    sends.clients[bid].render.side_effect = RuntimeError("connection lost after starting write")
    assert drive(engine, sends) is False
    importlib.reload(silence_queue)
    assert silence_queue.peek(bid).delivery_state == "unresolved"


def test_marker_save_failure_prevents_hardware_and_preserves_pending(engine, sends, monkeypatch):
    bid = sends.boards[0]["id"]
    silence_queue.hold(silence_queue.HeldSend.text("KEEP", board_id=bid))
    sends.clock.set(datetime(2026, 10, 25, 8, tzinfo=UTC))
    attempted = []

    def fail_save(*args, **kwargs):
        attempted.append(True)
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr(silence_queue, "write_json_atomic", fail_save)
        assert drive(engine, sends) is False
        assert attempted == [True]
        sends.clients[bid].render.assert_not_called()
    importlib.reload(silence_queue)
    assert silence_queue.peek(bid).delivery_state == "pending"


def test_failed_pending_restore_remains_unresolved(engine, sends, monkeypatch):
    bid = sends.boards[0]["id"]
    silence_queue.hold(silence_queue.HeldSend.text("KEEP", board_id=bid))
    sends.clock.set(datetime(2026, 10, 25, 8, tzinfo=UTC))
    write = silence_queue.write_json_atomic

    def fail_restore(path, data, **kwargs):
        if data[bid]["delivery_state"] == "pending":
            raise OSError("restore failed")
        return write(path, data, **kwargs)

    sends.clients[bid].render.return_value = (False, False)
    with monkeypatch.context() as patch:
        patch.setattr(silence_queue, "write_json_atomic", fail_restore)
        assert drive(engine, sends) is False
    importlib.reload(silence_queue)
    assert silence_queue.peek(bid).delivery_state == "unresolved"


def test_overlapping_writes_of_same_observed_intent_settle_in_order(sends):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    bid = sends.boards[0]["id"]
    old = silence_queue.HeldSend.text("OLD", board_id=bid)
    silence_queue.hold(old)
    first_started, release, second_started = threading.Event(), threading.Event(), threading.Event()

    def first_write():
        first_started.set()
        assert release.wait(3)
        return False, False

    def second_write():
        second_started.set()
        return True, True

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(silence_queue.deliver, old, first_write)
        assert first_started.wait(2)
        second = pool.submit(silence_queue.deliver, old, second_write)
        try:
            assert not second_started.wait(0.1)
        finally:
            release.set()
        assert first.result() == (False, False)
        assert second.result() == (True, True)
    importlib.reload(silence_queue)
    assert silence_queue.peek(bid) is None


def test_in_flight_marker_does_not_let_background_content_preempt_held_delivery(engine, sends):
    import threading

    bid = sends.boards[0]["id"]
    started, release = threading.Event(), threading.Event()
    silence_queue.hold(silence_queue.HeldSend.text("HELD", board_id=bid))
    sends.clock.set(datetime(2026, 10, 25, 8, tzinfo=UTC))

    def write(*args, **kwargs):
        started.set()
        assert release.wait(3)
        return True, True

    sends.clients[bid].render.side_effect = write
    try:
        assert (
            engine.check_and_send_for_board(
                bid, engine.runtimes[bid], is_primary=True, board=sends.boards[0], wait=False
            )
            is True
        )
        assert started.wait(2)
        assert silence_queue.peek(bid).delivery_state == "unresolved"
        assert (
            engine.check_and_send_for_board(
                bid, engine.runtimes[bid], is_primary=True, board=sends.boards[0], wait=False
            )
            is False
        )
    finally:
        release.set()
        assert engine.wait_until_idle()
    sends.clients[bid].render.assert_called_once()
    assert silence_queue.peek(bid) is None


@pytest.mark.parametrize(
    "path,method",
    [
        ("/settings/active-page", "put"),
        ("/v1/boards/{board}/active-page", "put"),
        ("/templates/render/live", "post"),
    ],
)
def test_new_persistence_errors_are_declared_in_openapi(sends, path, method):
    from src.api_server import app
    from src.v1.visibility import build_internal_openapi

    schema = build_internal_openapi(app)
    assert "503" in schema["paths"][path][method]["responses"]
