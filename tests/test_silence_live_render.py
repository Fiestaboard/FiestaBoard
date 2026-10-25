"""The page editor's Live Output never wakes a silenced board by itself (#1943).

``POST /templates/render/live`` wrote every keystroke to the board through
its live driver, silence or not. During silence it now still renders (the
editor preview keeps working) but leaves the board alone and says so with
``silenced: true``. ``override_silence: true`` is the explicit "send to board
anyway". Live output is never *held*: a keystroke stream is not an intent.
"""

from __future__ import annotations

from unittest import mock

import pytest
from fastapi.testclient import TestClient

from src import silence_queue
from src.silence_queue import HeldSend
from tests.live_boards import install_live_boards
from tests.silence_helpers import silenced
from tests.test_wire_goldens import install_wire_recorder, local_flagship


@pytest.fixture(autouse=True)
def _clean_queue():
    silence_queue.clear()
    yield
    silence_queue.clear()


@pytest.fixture
def wire(monkeypatch):
    recorder = install_wire_recorder(monkeypatch)
    install_live_boards([local_flagship("b1")])
    recorder.take()
    return recorder


def _posts(wire):
    return [c for c in wire.take() if c["method"] == "POST"]


def _live(body):
    from src.api_server import app

    return TestClient(app).post("/templates/render/live", json={"template": ["LIVE EDIT"], **body})


def test_silenced_live_render_previews_but_leaves_the_board_alone(wire):
    with silenced(holds=True):
        resp = _live({"board_id": "b1"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["lines"][0].strip() == "LIVE EDIT"
    assert (body["sent_to_board"], body["silenced"], body["paused"]) == (False, True, False)
    assert _posts(wire) == []
    # Never held: a keystroke stream is not an intent.
    assert silence_queue.peek("b1") is None


def test_silenced_live_render_does_not_touch_the_live_driver(wire):
    with silenced(), mock.patch("src.templates.routes.run_board_preview") as preview:
        _live({"board_id": "b1"})
    preview.assert_not_called()


def test_override_silence_writes_and_discards_the_held_entry(wire):
    silence_queue.hold(HeldSend.text("NIGHT", board_id="b1"))
    with silenced(holds=True):
        body = _live({"board_id": "b1", "override_silence": True}).json()
    assert (body["sent_to_board"], body["silenced"]) == (True, False)
    assert len(_posts(wire)) == 1
    assert silence_queue.peek("b1") is None


def test_pause_wins_over_the_override_and_is_reported(wire):
    with silenced(), mock.patch("src.templates.routes._board_is_paused", return_value=True):
        overridden = _live({"board_id": "b1", "override_silence": True}).json()
        plain = _live({"board_id": "b1"}).json()
    assert _posts(wire) == []
    assert (overridden["paused"], overridden["silenced"], overridden["sent_to_board"]) == (True, False, False)
    assert (plain["paused"], plain["silenced"]) == (True, True)


def test_not_silenced_live_render_sends_as_before(wire):
    body = _live({"board_id": "b1"}).json()
    assert (body["sent_to_board"], body["silenced"]) == (True, False)
    assert len(_posts(wire)) == 1


def test_omitted_board_resolves_the_first_boards_window(wire):
    with silenced(board="b1"):
        body = _live({}).json()
    assert body["silenced"] is True
    assert _posts(wire) == []
