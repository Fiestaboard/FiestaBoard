"""Tests for VirtualBoardClient — the in-memory client behind FiestaPanel boards."""

from unittest.mock import patch

from src.board_client import board_client_from_board_dict
from src.virtual_board_client import VirtualBoardClient


def _grid(rows=6, cols=22, fill=0):
    return [[fill] * cols for _ in range(rows)]


class TestVirtualBoardClientSend:
    def test_send_characters_stores_frame_without_http(self):
        """A send lands in memory; no HTTP request is ever made."""
        client = VirtualBoardClient(device_type="flagship")
        with patch("requests.post") as mock_post, patch("requests.get") as mock_get:
            ok, sent = client.send_characters(_grid(fill=1))
        assert (ok, sent) == (True, True)
        mock_post.assert_not_called()
        mock_get.assert_not_called()
        assert client._last_characters == _grid(fill=1)
        assert client._last_sent_at is not None

    def test_send_characters_stores_a_copy(self):
        """Mutating the caller's grid after a send must not change the cache."""
        client = VirtualBoardClient(device_type="flagship")
        grid = _grid(fill=2)
        client.send_characters(grid)
        grid[0][0] = 99
        assert client._last_characters is not None
        assert client._last_characters[0][0] == 2

    def test_skip_unchanged_reports_not_sent(self):
        """An identical grid is acknowledged but not re-'sent'."""
        client = VirtualBoardClient(device_type="flagship")
        client.send_characters(_grid(fill=3))
        ok, sent = client.send_characters(_grid(fill=3))
        assert (ok, sent) == (True, False)

    def test_force_resends_unchanged_grid(self):
        """force=True bypasses the unchanged-skip like the HTTP clients."""
        client = VirtualBoardClient(device_type="flagship")
        client.send_characters(_grid(fill=3))
        ok, sent = client.send_characters(_grid(fill=3), force=True)
        assert (ok, sent) == (True, True)

    def test_rejects_wrong_shape_grid(self):
        """A grid that doesn't match the device dimensions is refused."""
        client = VirtualBoardClient(device_type="flagship")
        ok, sent = client.send_characters(_grid(rows=3, cols=15, fill=1))
        assert (ok, sent) == (False, False)
        assert client._last_characters is None

    def test_send_text_is_unsupported(self):
        """Virtual boards are characters-only, mirroring note arrays."""
        client = VirtualBoardClient(device_type="flagship")
        assert client.send_text("HELLO") == (False, False)

    def test_render_delegates_to_send_characters(self):
        """The mixin's render() path works for plain strategies."""
        client = VirtualBoardClient(device_type="flagship")
        ok, sent = client.render(_grid(fill=4))
        assert (ok, sent) == (True, True)
        assert client._last_characters == _grid(fill=4)


class TestVirtualBoardClientRead:
    def test_read_returns_none_before_any_send(self):
        client = VirtualBoardClient(device_type="flagship")
        assert client.read_current_message() is None

    def test_read_returns_copy_of_sent_frame_without_http(self):
        """The board poll loop calls read_current_message(); it must be HTTP-free."""
        client = VirtualBoardClient(device_type="flagship")
        client.send_characters(_grid(fill=5))
        with patch("requests.get") as mock_get, patch("requests.post") as mock_post:
            frame = client.read_current_message()
        mock_get.assert_not_called()
        mock_post.assert_not_called()
        assert frame == _grid(fill=5)
        assert frame is not None
        frame[0][0] = 99
        assert client._last_characters is not None
        assert client._last_characters[0][0] == 5

    def test_test_connection_is_true(self):
        """A virtual board is always reachable."""
        assert VirtualBoardClient(device_type="note").test_connection() is True

    def test_clear_cache_keeps_displayed_frame(self):
        """clear_cache forces a re-send (dedupe reset) but must not blank the panel.

        invalidate_board_content() calls clear_cache() after out-of-band
        writes; on a physical board the glass keeps its content, so the
        virtual board's displayed frame must survive too.
        """
        client = VirtualBoardClient(device_type="flagship")
        client.send_characters(_grid(fill=6))
        client.clear_cache()
        assert client.read_current_message() == _grid(fill=6)
        # dedupe cache is gone: the same grid counts as a fresh send again
        ok, sent = client.send_characters(_grid(fill=6))
        assert (ok, sent) == (True, True)


class TestFactoryDispatch:
    def test_factory_returns_virtual_client(self):
        client = board_client_from_board_dict({"api_mode": "virtual", "device_type": "flagship", "id": "b1"})
        assert isinstance(client, VirtualBoardClient)
        assert client.is_virtual is True
        assert client.use_cloud is False

    def test_factory_virtual_needs_no_credentials(self):
        client = board_client_from_board_dict({"api_mode": "virtual", "device_type": "note"})
        assert client is not None
        assert (client.rows, client.cols) == (3, 15)
