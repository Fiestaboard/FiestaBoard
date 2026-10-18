"""Picking a page never wakes a silenced board unless you say so (issue #1943).

``PUT /settings/active-page`` — and the two surfaces that delegate to it,
``PUT /v1/boards/{board}/active-page`` and the MCP ``set_active_page`` tool —
used to render and send the page immediately, silence or not. During silence
the selection is now saved and the immediate send is held: the page appears
when silence ends. ``override_silence: true`` is the one explicit way to show
it now. Pause is never overridden, and both flags are reported truthfully.
"""

from __future__ import annotations

import asyncio
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from src import silence_queue
from src.board_guards import SilenceVerdict
from src.silence_queue import HeldSend
from tests.live_boards import install_live_boards
from tests.test_wire_goldens import install_wire_recorder, local_flagship

SILENCED = SilenceVerdict(silenced=True, held=False, ends_at_utc="2026-10-18T07:00:00+00:00")
NOT_SILENCED = SilenceVerdict(silenced=False)


@pytest.fixture(autouse=True)
def _clean_queue():
    silence_queue.clear()
    yield
    silence_queue.clear()


@pytest.fixture
def boards(monkeypatch):
    """Two live local flagships on the wire recorder, and a page for each test."""
    from src.pages.models import PageCreate
    from src.pages.service import get_page_service

    wire = install_wire_recorder(monkeypatch)
    service = install_live_boards([local_flagship("b1"), local_flagship("b2", host="192.168.0.12")])
    page = get_page_service().create_page(PageCreate(name="Weather", type="template", template=["SUNNY"]))
    wire.take()
    return mock.Mock(wire=wire, service=service, page=page)


def _posts(wire):
    return [c for c in wire.take() if c["method"] == "POST"]


def _put(body):
    from src.api_server import app

    return TestClient(app).put("/settings/active-page", json=body)


def _silence_only(board):
    """Silence the named board's window and nothing else (real verdict path)."""
    return mock.patch("src.config.Config.is_silence_mode_active", side_effect=lambda b=None: b == board)


def test_set_active_page_during_silence_persists_but_does_not_send(boards):
    from src.settings.service import get_settings_service

    with mock.patch("src.settings.routes.silence_verdict", return_value=SILENCED):
        resp = _put({"page_id": boards.page.id, "board_id": "b1"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sent_to_board"] is False
    assert body["silenced"] is True
    assert body["paused"] is False
    assert body["error"] is None
    assert get_settings_service().get_active_page_id(board_id="b1") == boards.page.id
    assert _posts(boards.wire) == []


def test_not_silenced_sends_and_reports_silenced_false(boards):
    with mock.patch("src.settings.routes.silence_verdict", return_value=NOT_SILENCED):
        resp = _put({"page_id": boards.page.id, "board_id": "b1"})
    body = resp.json()
    assert body["sent_to_board"] is True
    assert body["silenced"] is False
    assert len(_posts(boards.wire)) == 1


def test_override_silence_sends_and_discards_held(boards):
    silence_queue.hold(HeldSend.text("HELLO", board_id="b1"))
    with _silence_only("b1"):
        resp = _put({"page_id": boards.page.id, "board_id": "b1", "override_silence": True})
    body = resp.json()
    assert body["sent_to_board"] is True
    assert body["silenced"] is False
    assert len(_posts(boards.wire)) == 1
    assert silence_queue.peek("b1") is None


def test_held_message_survives_a_silenced_page_pick(boards):
    # Only an explicit override write supersedes a held message; a pick held
    # by silence leaves it in place (the Home alert shows both).
    silence_queue.hold(HeldSend.text("HELLO", board_id="b1"))
    with _silence_only("b1"):
        _put({"page_id": boards.page.id, "board_id": "b1"})
    assert silence_queue.peek("b1") is not None


def test_pause_wins_over_override_and_both_flags_reported(boards):
    with _silence_only("b1"), mock.patch("src.settings.routes._board_is_paused", return_value=True):
        overridden = _put({"page_id": boards.page.id, "board_id": "b1", "override_silence": True}).json()
        held = _put({"page_id": boards.page.id, "board_id": "b1"}).json()
    assert _posts(boards.wire) == []
    assert (overridden["sent_to_board"], overridden["paused"], overridden["silenced"]) == (False, True, False)
    assert (held["sent_to_board"], held["paused"], held["silenced"]) == (False, True, True)


def test_silence_is_resolved_for_the_target_board(boards):
    with _silence_only("b2"):
        loud = _put({"page_id": boards.page.id, "board_id": "b1"}).json()
        assert len(_posts(boards.wire)) == 1
        quiet = _put({"page_id": boards.page.id, "board_id": "b2"}).json()
        assert _posts(boards.wire) == []
    assert (loud["sent_to_board"], loud["silenced"]) == (True, False)
    assert (quiet["sent_to_board"], quiet["silenced"]) == (False, True)


def test_omitted_board_resolves_the_primary_window(boards):
    with _silence_only("b1"):
        body = _put({"page_id": boards.page.id}).json()
    assert body["silenced"] is True
    assert _posts(boards.wire) == []


def test_silenced_pick_still_wakes_the_engine(boards):
    # The engine skips while snoozing and repaints the saved page when the
    # window ends; waking it here keeps that bookkeeping current.
    with _silence_only("b1"), mock.patch.object(boards.service, "wake") as wake:
        _put({"page_id": boards.page.id, "board_id": "b1"})
    wake.assert_called_once_with()


# ---------------------------------------------------------------------------
# v1 and MCP inherit it
# ---------------------------------------------------------------------------


def _v1_put(board, body):
    from src.api_server import app

    return TestClient(app).put(f"/v1/boards/{board}/active-page", json=body)


def test_v1_silenced_pin_is_saved_with_a_reason(boards):
    from src.settings.service import get_settings_service
    from src.v1.routes_boards import SILENCED_PIN_REASON

    with (
        _silence_only("b1"),
        mock.patch("src.board_guards.silence_window_end", return_value="2026-10-18T07:00:00+00:00"),
    ):
        resp = _v1_put("b1", {"page_id": boards.page.id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sent"] is False
    assert body["silenced"] is True
    assert body["error"] is None
    assert body["reason"] == SILENCED_PIN_REASON.format(time="07:00")
    assert "07:00 UTC" in body["reason"]
    assert get_settings_service().get_active_page_id(board_id="b1") == boards.page.id
    assert _posts(boards.wire) == []


def test_v1_override_silence_shows_the_page_now(boards):
    with _silence_only("b1"):
        body = _v1_put("b1", {"page_id": boards.page.id, "override_silence": True}).json()
    assert (body["sent"], body["silenced"], body["reason"]) == (True, False, None)
    assert len(_posts(boards.wire)) == 1


def test_v1_override_silence_must_be_a_real_boolean(boards):
    resp = _v1_put("b1", {"page_id": boards.page.id, "override_silence": "yes"})
    assert resp.status_code == 422


def test_mcp_set_active_page_reports_the_hold(boards):
    from src.ops import executors

    with (
        _silence_only("b1"),
        mock.patch("src.board_guards.silence_window_end", return_value="2026-10-18T07:00:00+00:00"),
    ):
        result = asyncio.run(executors.set_active_page(boards.page.id, board_id="b1"))
    assert result["status"] == "success"
    assert result["silenced"] is True
    assert result["silence_ends_at"] == "2026-10-18T07:00:00+00:00"
    assert result["sent_to_board"] is False
    assert result["message"] == (
        f"Active page set to '{boards.page.id}' on board 'b1'. The board is silenced until 07:00 UTC, "
        "so it will appear then. "
        "Pass override_silence=true to show it now."
    )
    assert _posts(boards.wire) == []


def test_mcp_set_active_page_passes_override_through(boards):
    from src.ops import executors

    with _silence_only("b1"):
        result = asyncio.run(executors.set_active_page(boards.page.id, board_id="b1", override_silence=True))
    assert result["silenced"] is False
    assert result["sent_to_board"] is True
    assert len(_posts(boards.wire)) == 1


@pytest.mark.parametrize("tool", ["set_active_page", "send_message"])
def test_mcp_tools_expose_override_silence(tool):
    from src.mcp_server import _build_mcp_server

    tools = {t.name: t for t in asyncio.run(_build_mcp_server().list_tools())}
    schema = tools[tool].input_schema
    assert "override_silence" in schema["properties"]
    assert schema["properties"]["override_silence"].get("default") is False
