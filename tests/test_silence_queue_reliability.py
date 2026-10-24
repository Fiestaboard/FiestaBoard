"""Retry and recoverable storage failures use isolated data and fake boards."""

import importlib
import json
from dataclasses import asdict
from datetime import UTC, datetime

import pytest

from src import silence_queue
from tests.test_silence_held_engine import drive
from tests.test_silence_held_engine import engine as engine
from tests.test_silence_send_integration import sends as sends


@pytest.mark.parametrize("damage", ["read", "json", "shape", "record", "mixed"])
def test_unavailable_store_rejects_mutations_preserves_bytes_and_recovers(sends, monkeypatch, damage):
    bid = sends.boards[0]["id"]
    old = silence_queue.HeldSend.text("KEEP", board_id=bid)
    path = silence_queue._path()
    valid = json.dumps({bid: asdict(old)})
    contents = {
        "read": valid,
        "json": "{broken",
        "shape": "[]",
        "record": '{"bad":null}',
        "mixed": json.dumps({bid: asdict(old), "bad": None}),
    }[damage]
    path.write_text(contents)
    importlib.reload(silence_queue)
    with monkeypatch.context() as patch:
        if damage == "read":
            read = type(path).read_text

            def unavailable(self, *args, **kwargs):
                if self == path:
                    raise OSError("temporarily unreadable")
                return read(self, *args, **kwargs)

            patch.setattr(type(path), "read_text", unavailable)
        status = sends.http.get("/silence-status", params={"board_id": bid})
        assert status.status_code == 200
        assert status.json()["queue_available"] is False
        assert status.json()["active"] is True
        assert status.json()["held"] is None
        for method, url, kwargs in [
            ("post", "/send-message", {"json": {"text": "NEW"}}),
            ("post", f"/v1/boards/{bid}/message", {"json": {"text": "NEW"}}),
            ("delete", "/silence-queue", {"params": {"board_id": bid}}),
        ]:
            response = getattr(sends.http, method)(url, **kwargs)
            assert response.status_code == 503
            assert path.read_bytes() == contents.encode()
        sends.clients[bid].render.assert_not_called()
    # Repair in place, with no module reload: failure must not cache emptiness.
    path.write_text(valid)
    status = sends.http.get("/silence-status", params={"board_id": bid}).json()
    assert status["queue_available"] is True
    assert status["held"]["preview"] == "KEEP"
    assert sends.http.post("/send-message", json={"text": "NEW"}).status_code == 202
    importlib.reload(silence_queue)
    assert silence_queue.peek(bid).payload == "NEW"


def test_missing_store_accepts_first_hold(sends):
    bid = sends.boards[0]["id"]
    assert not silence_queue._path().exists()
    assert sends.http.get("/silence-status", params={"board_id": bid}).json()["queue_available"] is True
    assert sends.http.post("/send-message", json={"text": "FIRST"}).status_code == 202
    importlib.reload(silence_queue)
    assert silence_queue.peek(bid).payload == "FIRST"


@pytest.mark.parametrize("restart", [False, True])
def test_ambiguous_send_retries_and_preserves_newer_intent(engine, sends, restart):
    bid = sends.boards[0]["id"]
    old = silence_queue.HeldSend.text("RETRY", board_id=bid)
    silence_queue.hold(old)
    sends.clock.set(datetime(2026, 10, 25, 8, tzinfo=UTC))
    sends.clients[bid].render.side_effect = OSError("ambiguous connection loss")
    assert drive(engine, sends) is False
    if restart:
        importlib.reload(silence_queue)
    assert silence_queue.peek(bid).payload == "RETRY"

    def success_with_new_hold(*args, **kwargs):
        from tests.helpers import decode_board_rows

        assert decode_board_rows(args[0])[0].strip() == "RETRY"
        silence_queue.hold(silence_queue.HeldSend.text("NEWER", board_id=bid))
        return True, True

    sends.clients[bid].render.side_effect = success_with_new_hold
    assert drive(engine, sends) is True
    assert silence_queue.peek(bid).payload == "NEWER"
    sends.clients[bid].render.side_effect = None
    assert drive(engine, sends) is True
    assert silence_queue.peek(bid) is None


def test_old_candidate_marker_is_automatically_retryable(engine, sends):
    bid = sends.boards[0]["id"]
    record = asdict(silence_queue.HeldSend.text("RETRY OLD MARKER", board_id=bid))
    record["delivery_state"] = "unresolved"
    silence_queue._path().write_text(json.dumps({bid: record}))
    importlib.reload(silence_queue)
    sends.clock.set(datetime(2026, 10, 25, 8, tzinfo=UTC))
    assert drive(engine, sends) is True
    sends.clients[bid].render.assert_called_once()
    assert silence_queue.peek(bid) is None


@pytest.mark.parametrize("surface", ["active", "page", "display"])
@pytest.mark.parametrize("gate", ["paused", "ui"])
def test_unavailable_queue_preserves_no_write_selection_and_preview(sends, surface, gate):
    bid = sends.boards[0]["id"]
    path = silence_queue._path()
    path.write_text("{damaged")
    importlib.reload(silence_queue)
    sends.settings.set_paused(gate == "paused", board_id=bid)
    if gate == "ui":
        sends.settings.set_output_target("ui")
    method, url, body = {
        "active": ("put", "/settings/active-page", {"page_id": sends.page.id, "board_id": bid}),
        "page": ("post", f"/pages/{sends.page.id}/send", {}),
        "display": ("post", "/displays/weather/send", {}),
    }[surface]
    response = getattr(sends.http, method)(url, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["sent_to_board"] is False
    assert response.json()["paused"] is (gate == "paused")
    if surface == "active":
        assert sends.settings.get_active_page_id(board_id=bid) == sends.page.id
    sends.clients[bid].render.assert_not_called()
    assert path.read_text() == "{damaged"


@pytest.mark.parametrize("missing", ["board", "page"])
def test_invalid_selection_still_returns_404_with_unavailable_queue(sends, missing):
    bid = sends.boards[0]["id"]
    path = silence_queue._path()
    path.write_text("{damaged")
    importlib.reload(silence_queue)
    response = sends.http.put(
        "/settings/active-page",
        json={
            "board_id": "missing" if missing == "board" else bid,
            "page_id": "missing" if missing == "page" else sends.page.id,
        },
    )
    assert response.status_code == 404
    sends.clients[bid].render.assert_not_called()
    assert path.read_text() == "{damaged"
