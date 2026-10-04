"""``WriteResult``: a write that reached part of the board says so.

A local note array is several devices. When one tile fails and the rest
take their slice, the board is half-updated: the healthy tiles show the new
content, the failed one the old. Before ``WriteResult`` the only verdict was
``(success=False, was_sent=True)`` and ``POST /v1/boards/{board}/message``
answered a bare 500 "Failed to send" — indistinguishable from a write that
changed nothing (wire-goldens finding A4.3).

``WriteResult`` is today's ``SendOutcome`` (``SendOutcome`` is now an alias)
plus ``partial`` and ``failed_regions``; the v1 route answers 502 with a
structured detail naming the cells that did not update.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import requests
from fastapi.testclient import TestClient

from src.devices import NOTE_COLS, NOTE_ROWS
from src.outputs.plugin_driver import OutputPluginDriver
from src.send_outcome import FrameRegion, SendOutcome, WriteResult
from tests.first_party_drivers import tiles_driver
from tests.live_boards import install_live_boards
from tests.test_wire_goldens import install_wire_recorder, make_response, note_array_local


def _tile(row: int, col: int) -> dict:
    return {"row": row, "col": col, "host": f"10.0.0.{10 + col}", "port": 7000, "local_api_key": f"key-{col}"}


def _two_wide() -> OutputPluginDriver:
    return tiles_driver([_tile(0, 0), _tile(0, 1)], 2, 1)


def _grid() -> list[list[int]]:
    return [[(r * 30 + c) % 70 for c in range(NOTE_COLS * 2)] for r in range(NOTE_ROWS)]


def _failing(*hosts: str):
    def post(url, **_kwargs):
        response = Mock()
        if any(host in url for host in hosts):
            response.raise_for_status.side_effect = requests.exceptions.HTTPError("tile down")
        else:
            response.raise_for_status = Mock()
        return response

    return post


class TestTheType:
    def test_send_outcome_is_write_result(self):
        assert SendOutcome is WriteResult

    def test_a_whole_write_is_not_partial(self):
        result = WriteResult(True, True)
        assert (result.partial, result.failed_regions) == (False, ())

    def test_of_passes_a_write_result_through(self):
        result = WriteResult(False, True, partial=True, failed_regions=(FrameRegion(0, 15, 3, 15),))
        assert SendOutcome.of(result) is result


class TestLocalNoteArrayPartialFailure:
    @patch("requests.post")
    def test_one_failed_tile_is_a_partial_write_naming_its_cells(self, mock_post):
        mock_post.side_effect = _failing("10.0.0.11")

        result = _two_wide().send_characters(_grid(), with_outcome=True)

        assert result == WriteResult(
            False, True, partial=True, failed_regions=(FrameRegion(row=0, col=15, rows=3, cols=15),)
        )

    @patch("requests.post")
    def test_every_tile_failing_is_not_partial(self, mock_post):
        mock_post.side_effect = _failing("10.0.0.10", "10.0.0.11")

        result = _two_wide().send_characters(_grid(), with_outcome=True)

        assert (result.success, result.was_sent, result.partial) == (False, False, False)
        assert result.failed_regions == (FrameRegion(0, 0, 3, 15), FrameRegion(0, 15, 3, 15))

    @patch("requests.post")
    def test_the_legacy_pair_is_unchanged(self, mock_post):
        mock_post.side_effect = _failing("10.0.0.11")
        assert _two_wide().send_characters(_grid()) == (False, True)


class TestTheV1RouteReportsAHalfUpdatedBoard:
    def test_partial_write_is_a_502_naming_the_failed_cells(self, monkeypatch):
        from src.api_server import app

        wire = install_wire_recorder(monkeypatch)
        install_live_boards([note_array_local()])
        wire.respond = lambda method, url, kwargs: (
            make_response(500, {"error": "tile down"}, url) if "192.168.0.21" in url else None
        )

        resp = TestClient(app).post("/v1/boards/wire-tiles/message", json={"text": "HELLO TILES"})

        assert resp.status_code == 502, resp.text
        detail = resp.json()["detail"]
        assert detail["partial"] is True
        assert detail["failed_regions"] == [{"row": 0, "col": 15, "rows": 3, "cols": 15}]
        assert "partly updated" in detail["message"]

    def test_the_executor_carries_the_partial_verdict(self, monkeypatch):
        from src.ops import executors

        wire = install_wire_recorder(monkeypatch)
        install_live_boards([note_array_local()])
        wire.respond = lambda method, url, kwargs: (
            make_response(500, {"error": "tile down"}, url) if "192.168.0.21" in url else None
        )

        result = executors.send_message("HELLO TILES", "wire-tiles")

        assert result["status"] == "error"
        assert result["partial"] is True
        assert result["failed_regions"] == [{"row": 0, "col": 15, "rows": 3, "cols": 15}]
