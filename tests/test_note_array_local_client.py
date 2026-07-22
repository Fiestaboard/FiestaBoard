"""Tests for the local-API fan-out client for note arrays."""

from unittest.mock import Mock, patch

import requests

from src.board_client import board_client_from_board_dict
from src.devices import NOTE_COLS, NOTE_ROWS
from src.note_array_local_client import NoteArrayLocalClient


def _tile(row=0, col=0, host=None, key=None, port=7000):
    return {
        "row": row,
        "col": col,
        "host": host or f"10.0.0.{10 + row * 8 + col}",
        "port": port,
        "local_api_key": key or f"key-{row}-{col}",
        "enabled": True,
    }


def _grid(notes_wide, notes_tall):
    rows, cols = notes_tall * NOTE_ROWS, notes_wide * NOTE_COLS
    return [[(r * cols + c) % 70 for c in range(cols)] for r in range(rows)]


def _two_wide():
    return NoteArrayLocalClient([_tile(0, 0), _tile(0, 1)], notes_wide=2, notes_tall=1)


class TestSendFanout:
    @patch("src.board_client.requests.post")
    def test_each_tile_receives_its_slice(self, mock_post):
        mock_post.return_value.raise_for_status = Mock()
        client = _two_wide()
        grid = _grid(2, 1)

        success, was_sent = client.send_characters(grid)

        assert (success, was_sent) == (True, True)
        assert mock_post.call_count == 2
        by_url = {call.args[0] if call.args else call.kwargs["url"]: call for call in mock_post.call_args_list}
        left = by_url["http://10.0.0.10:7000/local-api/message"]
        right = by_url["http://10.0.0.11:7000/local-api/message"]
        assert left.kwargs["json"]["characters"] == [row[:15] for row in grid]
        assert right.kwargs["json"]["characters"] == [row[15:] for row in grid]
        assert right.kwargs["headers"]["X-Vestaboard-Local-Api-Key"] == "key-0-1"

    @patch("src.board_client.requests.post")
    def test_transitions_forwarded_to_tiles(self, mock_post):
        mock_post.return_value.raise_for_status = Mock()
        client = _two_wide()

        client.send_characters(_grid(2, 1), strategy="column", step_interval_ms=100)

        for call in mock_post.call_args_list:
            assert call.kwargs["json"]["strategy"] == "column"
            assert call.kwargs["json"]["step_interval_ms"] == 100

    @patch("src.board_client.requests.post")
    def test_unchanged_grid_skipped(self, mock_post):
        mock_post.return_value.raise_for_status = Mock()
        client = _two_wide()
        grid = _grid(2, 1)

        client.send_characters(grid)
        success, was_sent = client.send_characters(grid)

        assert (success, was_sent) == (True, False)
        assert mock_post.call_count == 2  # only from the first send

    @patch("src.board_client.requests.post")
    def test_custom_port_used(self, mock_post):
        mock_post.return_value.raise_for_status = Mock()
        client = NoteArrayLocalClient([_tile(0, 0, host="10.0.0.5", port=7001)], notes_wide=1, notes_tall=1)

        client.send_characters(_grid(1, 1))

        url = mock_post.call_args.args[0] if mock_post.call_args.args else mock_post.call_args.kwargs["url"]
        assert url == "http://10.0.0.5:7001/local-api/message"

    def test_wrong_dimensions_rejected(self):
        client = _two_wide()
        assert client.send_characters(_grid(1, 1)) == (False, False)

    def test_invalid_strategy_rejected(self):
        client = _two_wide()
        assert client.send_characters(_grid(2, 1), strategy="spin") == (False, False)

    def test_no_tiles_fails(self):
        client = NoteArrayLocalClient([], notes_wide=2, notes_tall=1)
        assert client.send_characters(_grid(2, 1)) == (False, False)

    def test_out_of_range_tiles_excluded(self):
        client = NoteArrayLocalClient([_tile(0, 0), _tile(0, 5)], notes_wide=2, notes_tall=1)
        assert set(client.tile_clients) == {(0, 0)}

    def test_send_text_refused(self):
        assert _two_wide().send_text("hello") == (False, False)


class TestPartialFailure:
    @patch("src.board_client.requests.post")
    def test_one_tile_failing_fails_composite_without_caching(self, mock_post):
        def side_effect(url, **kwargs):
            response = Mock()
            if "10.0.0.11" in url:
                response.raise_for_status.side_effect = requests.exceptions.HTTPError("boom")
            else:
                response.raise_for_status = Mock()
            return response

        mock_post.side_effect = side_effect
        client = _two_wide()
        grid = _grid(2, 1)

        success, was_sent = client.send_characters(grid)

        assert success is False
        assert was_sent is True  # the healthy tile did update
        assert client._last_characters is None
        assert client.last_tile_results[(0, 0)] == (True, True)
        assert client.last_tile_results[(0, 1)] == (False, False)

    @patch("src.board_client.requests.post")
    def test_retry_after_partial_failure_only_resends_failed_tile(self, mock_post):
        calls = {"count": 0}

        def side_effect(url, **kwargs):
            calls["count"] += 1
            response = Mock()
            if "10.0.0.11" in url and calls["count"] <= 2:
                response.raise_for_status.side_effect = requests.exceptions.HTTPError("boom")
            else:
                response.raise_for_status = Mock()
            return response

        mock_post.side_effect = side_effect
        client = _two_wide()
        grid = _grid(2, 1)

        assert client.send_characters(grid)[0] is False
        mock_post.reset_mock()

        success, was_sent = client.send_characters(grid)

        assert (success, was_sent) == (True, True)
        # Healthy tile was skipped by its own cache; only the failed tile re-POSTs
        assert mock_post.call_count == 1
        url = mock_post.call_args.args[0] if mock_post.call_args.args else mock_post.call_args.kwargs["url"]
        assert "10.0.0.11" in url


class TestRead:
    @patch("src.board_client.requests.get")
    def test_stitched_read(self, mock_get):
        grid = _grid(2, 1)

        def side_effect(url, **kwargs):
            response = Mock()
            response.raise_for_status = Mock()
            half = [row[:15] for row in grid] if "10.0.0.10" in url else [row[15:] for row in grid]
            response.json.return_value = half
            return response

        mock_get.side_effect = side_effect
        client = _two_wide()

        assert client.read_current_message() == grid

    @patch("src.board_client.requests.get")
    def test_read_returns_none_when_any_tile_fails(self, mock_get):
        grid = _grid(2, 1)

        def side_effect(url, **kwargs):
            response = Mock()
            if "10.0.0.11" in url:
                response.raise_for_status.side_effect = requests.exceptions.HTTPError("boom")
            else:
                response.raise_for_status = Mock()
                response.json.return_value = [row[:15] for row in grid]
            return response

        mock_get.side_effect = side_effect
        assert _two_wide().read_current_message() is None

    def test_read_returns_none_for_partial_assignment(self):
        client = NoteArrayLocalClient([_tile(0, 0)], notes_wide=2, notes_tall=1)
        assert client.read_current_message() is None

    @patch("src.board_client.requests.get")
    def test_read_sync_cache_sets_composite_cache(self, mock_get):
        grid = _grid(1, 1)
        response = Mock()
        response.raise_for_status = Mock()
        response.json.return_value = grid
        mock_get.return_value = response
        client = NoteArrayLocalClient([_tile(0, 0)], notes_wide=1, notes_tall=1)

        assert client.read_current_message(sync_cache=True) == grid
        assert client._last_characters == grid


class TestDuckTypeSurface:
    def test_board_client_compatible_attributes(self):
        client = _two_wide()
        assert client.use_cloud is False
        assert client.skip_unchanged is True
        assert client._last_characters is None
        assert client._last_text is None
        assert client.would_send(characters=_grid(2, 1)) is True
        status = client.get_cache_status()
        assert status["has_cached_characters"] is False
        assert status["skip_unchanged_enabled"] is True

    @patch("src.board_client.requests.post")
    def test_clear_cache_cascades_to_tiles(self, mock_post):
        mock_post.return_value.raise_for_status = Mock()
        client = _two_wide()
        grid = _grid(2, 1)
        client.send_characters(grid)
        assert client._last_characters == grid

        client.clear_cache()

        assert client._last_characters is None
        assert all(c._last_characters is None for c in client.tile_clients.values())
        # A re-send now re-POSTs every tile
        mock_post.reset_mock()
        client.send_characters(grid)
        assert mock_post.call_count == 2


class TestFactory:
    def _board(self, **kw):
        return {
            "device_type": "note_array",
            "api_mode": "local",
            "notes_wide": 2,
            "notes_tall": 1,
            "tiles": [_tile(0, 0), _tile(0, 1)],
            **kw,
        }

    def test_local_array_builds_local_client(self):
        client = board_client_from_board_dict(self._board())
        assert isinstance(client, NoteArrayLocalClient)
        assert set(client.tile_clients) == {(0, 0), (0, 1)}

    def test_local_array_without_usable_tiles_returns_none(self):
        board = self._board(tiles=[{"row": 0, "col": 0, "host": "", "local_api_key": ""}])
        assert board_client_from_board_dict(board) is None

    def test_cloud_array_still_builds_cloud_client(self):
        board = self._board(api_mode="cloud", tiles=[], note_array_token="tok")
        client = board_client_from_board_dict(board)
        assert not isinstance(client, NoteArrayLocalClient)
        assert client is not None
        assert client._is_note_array is True

    def test_legacy_array_defaulting_local_without_tiles_uses_token(self):
        board = self._board(note_array_token="tok")
        board.pop("api_mode")
        board["tiles"] = []
        client = board_client_from_board_dict(board)
        assert not isinstance(client, NoteArrayLocalClient)
        assert client is not None
