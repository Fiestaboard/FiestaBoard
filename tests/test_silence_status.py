"""``GET /silence-status`` says when silence ends and what is held (#1943, #1944).

The UI quotes "Silenced until 7:00 AM" and "Held message: …" from this one
read, so the three new fields are pinned by value: ``ends_at_utc`` is the
same instant ``seconds_until_next_change`` counts down to, ``holds_blocked_sends``
is the board's own resolved ``show_queued_on_exit``, and ``held`` previews the
store. ``DELETE /silence-queue`` is the Discard button behind it.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src import silence_queue
from src.silence_queue import HeldSend


@pytest.fixture(autouse=True)
def _clean_queue():
    silence_queue.clear()
    yield
    silence_queue.clear()


@pytest.fixture
def client():
    from src.api_server import app

    return TestClient(app)


@pytest.fixture
def boards():
    from src.settings.service import get_settings_service

    stored = get_settings_service().set_boards(
        [
            {"id": "b1", "device_type": "flagship", "name": "Kitchen"},
            {"id": "b2", "device_type": "note", "name": "Hall"},
        ]
    )
    return [b["id"] for b in stored.boards]


def _schedule(**feature):
    from src.config_manager import get_config_manager

    get_config_manager().set_feature(
        "silence_schedule",
        {"enabled": True, "start_time": "00:00+00:00", "end_time": "23:59+00:00", **feature},
    )


def test_ends_at_utc_is_now_plus_seconds_until_next_change(client, boards):
    _schedule(by_board={boards[0]: {"enabled": True, "start_time": "00:00+00:00", "end_time": "23:59+00:00"}})
    body = client.get("/silence-status").json()
    assert body["enabled"] is True
    current = datetime.fromisoformat(body["ends_at_utc"]) - timedelta(seconds=body["seconds_until_next_change"])
    assert abs((current - datetime.now(current.tzinfo)).total_seconds()) < 5


def test_ends_at_utc_is_null_when_silence_is_disabled(client, boards):
    body = client.get("/silence-status").json()
    assert body["enabled"] is False
    assert body["ends_at_utc"] is None


def test_holds_blocked_sends_is_resolved_per_board(client, boards):
    _schedule(show_queued_on_exit=False, by_board={"b2": {"show_queued_on_exit": True}})
    assert client.get("/silence-status?board_id=b1").json()["holds_blocked_sends"] is False
    assert client.get("/silence-status?board_id=b2").json()["holds_blocked_sends"] is True


def test_held_previews_the_store(client, boards):
    silence_queue.hold(HeldSend.text("GOOD MORNING EVERYONE HAVE A GREAT DAY TODAY", board_id="b1"))
    held = client.get("/silence-status").json()["held"]
    assert held["kind"] == "text"
    assert held["preview"] == "GOOD MORNING EVERYONE HAVE A…"
    assert datetime.fromisoformat(held["queued_at"]).tzinfo is not None
    assert client.get("/silence-status?board_id=b2").json()["held"] is None


def test_delete_silence_queue_discards_then_reports_nothing_to_discard(client, boards):
    silence_queue.hold(HeldSend.text("HI", board_id="b1"))
    first = client.delete("/silence-queue")
    assert first.status_code == 200
    assert first.json() == {"board_id": "b1", "discarded": True}
    assert silence_queue.peek("b1") is None
    assert client.delete("/silence-queue?board_id=b1").json() == {"board_id": "b1", "discarded": False}


def test_delete_silence_queue_targets_one_board(client, boards):
    silence_queue.hold(HeldSend.text("ONE", board_id="b1"))
    silence_queue.hold(HeldSend.text("TWO", board_id="b2"))
    assert client.delete("/silence-queue?board_id=b2").json()["discarded"] is True
    assert silence_queue.peek("b1") is not None


def test_delete_silence_queue_404s_an_unknown_board(client, boards):
    resp = client.delete("/silence-queue?board_id=nope")
    assert resp.status_code == 404
