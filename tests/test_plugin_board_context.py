"""Tests for board-awareness in the plugin system.

Covers the BoardContext binding on PluginBase, per-board result caching,
thread-safety of the binding under concurrent fan-out, and the registry's
per-board context builder.
"""

import threading
import time

from src.devices import BoardContext
from src.plugins.base import PluginBase, PluginResult

MANIFEST = {
    "id": "board_probe",
    "name": "Board Probe",
    "version": "1.0.0",
    "settings_schema": {
        "type": "object",
        "properties": {"refresh_seconds": {"type": "integer", "default": 300, "minimum": 10, "maximum": 600}},
    },
}

LIVE_MANIFEST = {**MANIFEST, "live_data": True}


class BoardProbePlugin(PluginBase):
    """Records the board it saw on each fetch and how many times it fetched."""

    def __init__(self, manifest=None, delay=0.0):
        super().__init__(manifest or MANIFEST)
        self._enabled = True
        self.fetch_count = 0
        self.seen_devices = []
        self._delay = delay

    @property
    def plugin_id(self) -> str:
        return "board_probe"

    def fetch_data(self) -> PluginResult:
        self.fetch_count += 1
        if self._delay:
            time.sleep(self._delay)
        device = self.board.device_type if self.board else None
        self.seen_devices.append(device)
        return PluginResult(available=True, data={"device": device})


class TestBoardBinding:
    def test_board_visible_inside_fetch(self):
        plugin = BoardProbePlugin()
        result = plugin.get_data(BoardContext.from_device_type("note"))
        assert result.data["device"] == "note"

    def test_board_none_outside_call(self):
        plugin = BoardProbePlugin()
        assert plugin.board is None
        plugin.get_data(BoardContext.from_device_type("flagship"))
        # Binding is transient — cleared once the fetch returns.
        assert plugin.board is None

    def test_no_board_records_none(self):
        plugin = BoardProbePlugin()
        result = plugin.get_data()
        assert result.data["device"] is None


class TestPerBoardCaching:
    def test_distinct_boards_fetch_independently(self):
        plugin = BoardProbePlugin()
        plugin.get_data(BoardContext.from_device_type("flagship"))
        plugin.get_data(BoardContext.from_device_type("note"))
        assert plugin.fetch_count == 2
        assert plugin.seen_devices == ["flagship", "note"]

    def test_same_board_served_from_cache(self):
        plugin = BoardProbePlugin()
        plugin.get_data(BoardContext.from_device_type("flagship"))
        plugin.get_data(BoardContext.from_device_type("flagship"))
        assert plugin.fetch_count == 1

    def test_flagship_cache_not_polluted_by_note(self):
        plugin = BoardProbePlugin()
        assert plugin.get_data(BoardContext.from_device_type("flagship")).data["device"] == "flagship"
        assert plugin.get_data(BoardContext.from_device_type("note")).data["device"] == "note"
        # Flagship re-fetch within TTL still returns flagship data, not note's.
        assert plugin.get_data(BoardContext.from_device_type("flagship")).data["device"] == "flagship"
        assert plugin.fetch_count == 2

    def test_note_arrays_of_different_sizes_cache_independently(self):
        """Note arrays share device_type 'note_array' but differ in size — they
        must not collide in the per-board cache (would serve wrong-sized data)."""
        plugin = BoardProbePlugin()
        plugin.get_data(BoardContext("note_array", rows=3, cols=60))  # 4 side-by-side
        plugin.get_data(BoardContext("note_array", rows=6, cols=30))  # 2×2 grid
        assert plugin.fetch_count == 2
        # Re-fetching the first size within TTL is served from cache (no new fetch).
        plugin.get_data(BoardContext("note_array", rows=3, cols=60))
        assert plugin.fetch_count == 2

    def test_same_note_array_size_served_from_cache(self):
        plugin = BoardProbePlugin()
        plugin.get_data(BoardContext("note_array", rows=3, cols=60))
        plugin.get_data(BoardContext("note_array", rows=3, cols=60))
        assert plugin.fetch_count == 1

    def test_clear_cache_wipes_all_boards(self):
        plugin = BoardProbePlugin()
        plugin.get_data(BoardContext.from_device_type("flagship"))
        plugin.get_data(BoardContext.from_device_type("note"))
        plugin.clear_cache()
        plugin.get_data(BoardContext.from_device_type("flagship"))
        plugin.get_data(BoardContext.from_device_type("note"))
        assert plugin.fetch_count == 4

    def test_live_data_bypasses_cache_but_sees_board(self):
        plugin = BoardProbePlugin(LIVE_MANIFEST)
        for _ in range(3):
            assert plugin.get_data(BoardContext.from_device_type("note")).data["device"] == "note"
        assert plugin.fetch_count == 3  # no caching for live_data


class TestConcurrentBinding:
    def test_no_cross_board_bleed_under_threads(self):
        """Concurrent fetches for different boards must not see each other's board."""
        plugin = BoardProbePlugin(LIVE_MANIFEST, delay=0.02)
        results = {}

        def fetch(device_type):
            board = BoardContext.from_device_type(device_type)
            results[device_type] = plugin.get_data(board).data["device"]

        threads = [threading.Thread(target=fetch, args=(dt,)) for dt in ("flagship", "note", "flagship", "note")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results["flagship"] == "flagship"
        assert results["note"] == "note"


class TestRegistryPerBoardContexts:
    def test_build_template_contexts_for(self):
        from src.plugins.registry import PluginRegistry

        registry = PluginRegistry()
        plugin = BoardProbePlugin()
        registry._plugins[plugin.plugin_id] = plugin
        registry._enabled[plugin.plugin_id] = True

        boards = {
            "flagship": BoardContext.from_device_type("flagship"),
            "note": BoardContext.from_device_type("note"),
        }
        contexts = registry.build_template_contexts_for(boards)

        assert contexts["flagship"][plugin.plugin_id]["device"] == "flagship"
        assert contexts["note"][plugin.plugin_id]["device"] == "note"
