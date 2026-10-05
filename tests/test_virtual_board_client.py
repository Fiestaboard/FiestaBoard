"""Tests for VirtualBoardClient — the in-memory client behind FiestaPanel boards."""

from unittest.mock import patch

from src.board_client import board_client_from_board_dict
from src.outputs import OutputRuntime
from src.outputs.factory import build_driver
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
        assert client._frames.last_sent_at is not None

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

    def test_factory_virtual_note_array_gets_stitched_dims(self):
        """Auto-fit panels are note_array virtual boards; dims must stitch."""
        client = board_client_from_board_dict(
            {
                "api_mode": "virtual",
                "device_type": "note_array",
                "id": "b-array",
                "notes_wide": 2,
                "notes_tall": 4,
            }
        )
        assert client is not None
        assert (client.rows, client.cols) == (12, 30)
        ok, sent = client.send_characters([[0] * 30 for _ in range(12)])
        assert (ok, sent) == (True, True)


class TestFramesLiveInTheRuntime:
    """A virtual board's frame is its bound runtime's last-frame store.

    There is no per-board registry any more: every write to a saved board
    goes through its one live runtime, so instances are not shared by id.
    """

    def test_a_bound_clients_send_lands_in_its_runtimes_store(self):
        runtime = OutputRuntime("b-bound", output_id="fiestapanel")
        client = VirtualBoardClient(device_type="flagship", board_id="b-bound")
        client.set_output_runtime(runtime)
        client.send_characters(_grid(fill=9))
        assert runtime.last_frame == _grid(fill=9)
        assert runtime.last_sent_at is not None

    def test_instances_for_one_board_id_do_not_share_frames(self):
        a = VirtualBoardClient(device_type="flagship", board_id="b-same")
        b = VirtualBoardClient(device_type="flagship", board_id="b-same")
        a.send_characters(_grid(fill=1))
        assert b.read_current_message() is None

    def test_the_factory_passes_the_board_id(self):
        client = build_driver({"api_mode": "virtual", "device_type": "flagship", "id": "b-factory"})
        assert client.board_id == "b-factory"
        assert client.device_key() == "virtual:b-factory"


class TestReshape:
    """A panel TV-size edit reshapes the board; its runtime must not serve stale state."""

    @staticmethod
    def _reshaped() -> tuple[OutputRuntime, VirtualBoardClient]:
        """An 18x45 board whose runtime still stores the 12x15 frame it showed before."""
        runtime = OutputRuntime("b-resize", output_id="fiestapanel")
        after = VirtualBoardClient(device_type="note_array", board_id="b-resize", notes_wide=3, notes_tall=6)
        after.set_output_runtime(runtime)
        runtime.frames.record_sent(_grid(rows=12, cols=15, fill=5))
        return runtime, after

    def test_reshaped_board_does_not_serve_the_old_shape_frame(self):
        """After a re-fit, a client with the new dims must read None, not the
        old-shape frame still in the runtime's store.

        Repro of the live bug: resize a 55" panel (12×15) to 85" (18×45) —
        GET /panel/{ref}/frame kept returning the stale 12×15 grid while the
        config reported 18×45, so the TV rendered mismatched content forever.
        """
        runtime, after = self._reshaped()
        assert runtime.last_frame is not None
        assert after.read_current_message() is None

    def test_reshaped_board_accepts_new_shape_sends(self):
        """The stale dedupe cache must not block or corrupt the first new-shape send."""
        _runtime, after = self._reshaped()
        ok, sent = after.send_characters(_grid(rows=18, cols=45, fill=7))
        assert (ok, sent) == (True, True)
        assert after.read_current_message() == _grid(rows=18, cols=45, fill=7)
