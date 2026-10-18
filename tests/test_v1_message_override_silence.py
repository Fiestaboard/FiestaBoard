"""Writing a message to a silenced board: refuse, hold, or override (#1943, #1944).

``POST /v1/boards/{board}/message`` and the deprecated ``POST /send-message``
give a silenced board three possible answers:

* ``override_silence: true`` — the caller explicitly asked to wake the board:
  it is written (pause still refuses, 409).
* the board's ``show_queued_on_exit`` is on — the write is **held** and shown
  when silence ends: HTTP 202 with ``held: true``.
* otherwise — 409 whose detail names both ways forward.

v1's ``force`` keeps its meaning (resend unchanged content); it does not
override silence.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from src import silence_queue
from src.board_guards import SILENCE_DETAIL, SILENCE_OVERRIDE_HINT
from src.silence_queue import HeldSend
from tests.silence_helpers import silenced
from tests.test_v1_contract import BLANK_FLAGSHIP, board_client, boards, client  # noqa: F401  (fixtures)

HELD_REASON = "Held: the board is silenced until 07:00 UTC; this will show when silence ends."


@pytest.fixture(autouse=True)
def _clean_queue():
    silence_queue.clear()
    yield
    silence_queue.clear()


def _post(client, body, board="primary"):  # noqa: F811
    return client.post(f"/v1/boards/{board}/message", json=body)


def test_silenced_write_without_holds_is_409_with_the_override_hint(client, boards, board_client):  # noqa: F811
    with silenced(holds=False):
        response = _post(client, {"text": "Hello"})
    assert response.status_code == 409
    assert response.json() == {"detail": SILENCE_DETAIL + SILENCE_OVERRIDE_HINT}
    assert response.json()["detail"].endswith("hold it until silence ends.")
    board_client.render.assert_not_called()
    assert silence_queue.peek(boards[0]) is None


def test_silenced_write_with_holds_is_accepted_for_later(client, boards, board_client):  # noqa: F811
    with silenced(holds=True):
        response = _post(client, {"text": "Good morning"})
    assert response.status_code == 202, response.text
    body = response.json()
    assert (body["sent"], body["silenced"], body["held"]) == (False, True, True)
    assert body["reason"] == HELD_REASON
    board_client.render.assert_not_called()
    held = silence_queue.peek(boards[0])
    assert (held.kind, held.payload, held.board_id) == ("text", "Good morning", boards[0])


@pytest.mark.parametrize(
    ("body", "kind", "payload"),
    [
        ({"lines": ["ONE", "TWO"]}, "lines", ["ONE", "TWO"]),
        ({"characters": BLANK_FLAGSHIP}, "grid", {"characters": BLANK_FLAGSHIP, "cells": None}),
        ({"fill": 0}, "grid", {"characters": BLANK_FLAGSHIP, "cells": None}),
    ],
)
def test_each_form_is_held_as_its_intent(client, boards, board_client, body, kind, payload):  # noqa: F811
    with silenced(holds=True):
        response = _post(client, body)
    assert response.status_code == 202, response.text
    held = silence_queue.peek(boards[0])
    assert (held.kind, held.payload) == (kind, payload)


def test_a_page_write_is_held_as_the_page_not_its_frame(client, boards, board_client):  # noqa: F811
    from tests.test_v1_contract import _seed_page

    page_id = _seed_page(client)
    with silenced(holds=True):
        response = _post(client, {"page_id": page_id})
    assert response.status_code == 202, response.text
    held = silence_queue.peek(boards[0])
    assert (held.kind, held.payload) == ("page", page_id)


def test_override_silence_writes_and_discards_the_held_send(client, boards, board_client):  # noqa: F811
    silence_queue.hold(HeldSend.text("NIGHT", board_id=boards[0]))
    with silenced(holds=True):
        response = _post(client, {"text": "Wake up", "override_silence": True})
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["sent"], body["silenced"], body["held"]) == (True, False, False)
    board_client.render.assert_called_once()
    assert silence_queue.peek(boards[0]) is None


def test_override_silence_never_overrides_pause(client, boards, board_client):  # noqa: F811
    from src.settings.service import get_settings_service

    get_settings_service().set_paused(True, board_id=boards[0])
    with silenced(holds=False):
        response = _post(client, {"text": "Wake up", "override_silence": True})
    assert response.status_code == 409
    assert response.json() == {"detail": "Board is paused — sends are blocked until it is resumed."}
    board_client.render.assert_not_called()


def test_force_does_not_override_silence(client, boards, board_client):  # noqa: F811
    with silenced(holds=False):
        response = _post(client, {"text": "Hello", "force": True})
    assert response.status_code == 409
    board_client.render.assert_not_called()


def test_override_silence_must_be_a_real_boolean(client, boards, board_client):  # noqa: F811
    assert _post(client, {"text": "Hello", "override_silence": "true"}).status_code == 422


def test_silence_is_the_target_boards_window(client, boards, board_client):  # noqa: F811
    with silenced(holds=True, board=boards[1]):
        loud = _post(client, {"text": "Hello"}, board=boards[0])
    assert loud.status_code == 200
    assert loud.json()["silenced"] is False


# ---------------------------------------------------------------------------
# The deprecated POST /send-message
# ---------------------------------------------------------------------------


def test_send_message_holds_with_202(client, boards, board_client):  # noqa: F811
    with silenced(holds=True):
        response = client.post("/send-message", json={"text": "Good morning"})
    assert response.status_code == 202, response.text
    assert response.json() == {"message": "Held until silence ends", "sent": False, "held": True}
    held = silence_queue.peek(boards[0])
    assert (held.kind, held.payload) == ("text", "Good morning")
    board_client.render.assert_not_called()


def test_send_message_without_holds_is_409_with_the_hint(client, boards, board_client):  # noqa: F811
    with silenced(holds=False):
        response = client.post("/send-message", json={"text": "Hello"})
    assert response.status_code == 409
    assert response.json()["detail"] == SILENCE_DETAIL + SILENCE_OVERRIDE_HINT


def test_send_message_override_silence_writes(client, boards, board_client):  # noqa: F811
    silence_queue.hold(HeldSend.text("NIGHT", board_id=boards[0]))
    with silenced(holds=True):
        response = client.post("/send-message", json={"text": "Hello", "override_silence": True})
    assert response.status_code == 200, response.text
    assert response.json()["sent"] is True
    assert silence_queue.peek(boards[0]) is None


# ---------------------------------------------------------------------------
# MCP send_message
# ---------------------------------------------------------------------------


def test_mcp_send_message_held_keeps_the_blocked_contract(boards, board_client):  # noqa: F811
    from src.ops import executors

    with silenced(holds=True), patch("src.api_server.get_service", return_value=_service(board_client)):
        result = executors.send_message("Good morning")
    assert result["status"] == "blocked"
    assert result["silence_mode"] is True
    assert result["held"] is True
    assert result["silence_ends_at"] == "2026-10-18T07:00:00+00:00"
    assert result["message"] == "Held until silence ends at 07:00 UTC."
    assert silence_queue.peek(boards[0]).payload == "Good morning"


def test_mcp_send_message_refused_names_the_override(boards, board_client):  # noqa: F811
    from src.ops import executors

    with silenced(holds=False), patch("src.api_server.get_service", return_value=_service(board_client)):
        result = executors.send_message("Hello")
    assert result["status"] == "blocked"
    assert result["held"] is False
    assert result["message"] == (
        "The board is silenced until 07:00 UTC: the message was not sent. Pass override_silence=true to send it anyway."
    )


def test_mcp_send_message_tool_passes_override_through(boards, board_client):  # noqa: F811
    from src.mcp_server import _build_mcp_server

    server = _build_mcp_server()
    with silenced(holds=False), patch("src.api_server.get_service", return_value=_service(board_client)):
        asyncio.run(server.call_tool("send_message", {"text": "Hello", "override_silence": True}))
    board_client.render.assert_called_once()


def _service(board_client):  # noqa: F811
    from unittest.mock import Mock

    service = Mock()
    service.vb_client = board_client
    service.get_board_client.return_value = board_client
    return service
