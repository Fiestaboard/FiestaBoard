"""Tests for white_noise plugin."""

import json
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from src.plugins.base import PluginResult
from src.board_chars import BoardChars
from plugins.white_noise import (
    WhiteNoisePlugin,
    ROWS,
    COLS,
    INTENSITY_PRESETS,
    RAINDROP_COLORS,
    DEFAULT_INTENSITY,
    DEFAULT_DROP_COLOR,
    DEFAULT_DROPS_PER_FRAME,
    DEFAULT_MAX_DROPS,
)


class TestWhiteNoisePlugin:
    """Core tests for WhiteNoisePlugin."""

    def test_plugin_id(self, sample_manifest):
        """Plugin id must match directory name."""
        plugin = WhiteNoisePlugin(sample_manifest)
        assert plugin.plugin_id == "white_noise"

    # ------------------------------------------------------------------ #
    # Configuration validation
    # ------------------------------------------------------------------ #

    def test_validate_config_valid(self, sample_manifest, sample_config):
        """Valid config should produce no errors."""
        plugin = WhiteNoisePlugin(sample_manifest)
        errors = plugin.validate_config(sample_config)
        assert errors == []

    def test_validate_config_defaults(self, sample_manifest):
        """Empty config should be accepted (defaults apply)."""
        plugin = WhiteNoisePlugin(sample_manifest)
        errors = plugin.validate_config({})
        assert errors == []

    def test_validate_config_invalid_intensity(self, sample_manifest):
        """Invalid intensity value should trigger an error."""
        plugin = WhiteNoisePlugin(sample_manifest)
        errors = plugin.validate_config({"intensity": "tornado"})
        assert len(errors) == 1
        assert "intensity" in errors[0].lower()

    def test_validate_config_invalid_drop_color(self, sample_manifest):
        """Invalid drop_color should trigger an error."""
        plugin = WhiteNoisePlugin(sample_manifest)
        errors = plugin.validate_config({"drop_color": "pink"})
        assert len(errors) == 1
        assert "drop_color" in errors[0].lower()

    def test_validate_config_custom_intensity_valid(self, sample_manifest):
        """Custom intensity with valid drops_per_frame should be accepted."""
        plugin = WhiteNoisePlugin(sample_manifest)
        errors = plugin.validate_config({
            "intensity": "custom",
            "drop_color": "white",
            "drops_per_frame": 5,
            "max_drops": 40
        })
        assert errors == []

    def test_validate_config_custom_intensity_invalid_drops(self, sample_manifest):
        """Custom intensity with invalid drops_per_frame should error."""
        plugin = WhiteNoisePlugin(sample_manifest)
        errors = plugin.validate_config({
            "intensity": "custom",
            "drops_per_frame": 0
        })
        assert len(errors) == 1
        assert "drops_per_frame" in errors[0].lower()

    def test_validate_config_drops_per_frame_too_high(self, sample_manifest):
        """drops_per_frame exceeding board width should error."""
        plugin = WhiteNoisePlugin(sample_manifest)
        errors = plugin.validate_config({
            "intensity": "custom",
            "drops_per_frame": 25
        })
        assert len(errors) == 1
        assert "drops_per_frame" in errors[0].lower()

    def test_validate_config_invalid_max_drops(self, sample_manifest):
        """Invalid max_drops should trigger an error."""
        plugin = WhiteNoisePlugin(sample_manifest)
        errors = plugin.validate_config({"max_drops": 0})
        assert len(errors) == 1
        assert "max_drops" in errors[0].lower()

    def test_validate_config_max_drops_too_high(self, sample_manifest):
        """max_drops exceeding board capacity should error."""
        plugin = WhiteNoisePlugin(sample_manifest)
        errors = plugin.validate_config({"max_drops": 200})
        assert len(errors) == 1
        assert "max_drops" in errors[0].lower()

    # ------------------------------------------------------------------ #
    # fetch_data basics
    # ------------------------------------------------------------------ #

    def test_fetch_data_returns_available(self, sample_manifest, sample_config):
        """fetch_data should return an available result."""
        plugin = WhiteNoisePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        assert result.available is True
        assert result.error is None

    def test_fetch_data_contains_required_variables(self, sample_manifest, sample_config):
        """Result data must contain all declared variables."""
        plugin = WhiteNoisePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        for var in ["white_noise", "intensity", "drop_color", "active_drops", "drops_per_frame", "max_drops"]:
            assert var in result.data, f"Missing variable: {var}"

    def test_fetch_data_board_dimensions(self, sample_manifest, sample_config):
        """The board array must be 6×22."""
        plugin = WhiteNoisePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        board = result.data["white_noise_array"]
        assert len(board) == ROWS
        for row in board:
            assert len(row) == COLS

    def test_fetch_data_string_has_six_lines(self, sample_manifest, sample_config):
        """The string representation must have exactly 6 lines."""
        plugin = WhiteNoisePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        lines = result.data["white_noise"].split("\n")
        assert len(lines) == ROWS

    # ------------------------------------------------------------------ #
    # Rain simulation mechanics
    # ------------------------------------------------------------------ #

    def test_drops_appear_on_first_fetch(self, sample_manifest, sample_config):
        """After the first fetch some drops should exist."""
        random.seed(42)
        plugin = WhiteNoisePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        assert result.data["active_drops"] > 0

    def test_drops_cascade_downward(self, sample_manifest, sample_config):
        """Drops move down one row per step."""
        random.seed(42)
        plugin = WhiteNoisePlugin(sample_manifest)
        plugin.config = sample_config

        # First frame: drops at row 0
        plugin.fetch_data()
        first_drops = [list(d) for d in plugin._drops]

        # Second frame: old drops should have moved to row 1
        plugin.fetch_data()
        for d in first_drops:
            expected_row = d[0] + 1
            if expected_row < ROWS:
                assert [expected_row, d[1]] in plugin._drops

    def test_drops_removed_at_bottom(self, sample_manifest, sample_config):
        """Drops that fall off the bottom should be removed."""
        plugin = WhiteNoisePlugin(sample_manifest)
        plugin.config = sample_config
        # Place a drop at the last row
        plugin._drops = [[ROWS - 1, 5]]
        plugin.fetch_data()
        # That drop should now be gone (it would move to row ROWS which is out of bounds)
        assert [ROWS, 5] not in plugin._drops

    def test_light_intensity_drop_count(self, sample_manifest):
        """Light intensity should spawn at most 3 new drops."""
        random.seed(0)
        plugin = WhiteNoisePlugin(sample_manifest)
        plugin.config = {"intensity": "light", "drop_color": "white"}
        result = plugin.fetch_data()
        # On first frame all drops are new spawns at row 0
        top_drops = [d for d in plugin._drops if d[0] == 0]
        assert len(top_drops) <= INTENSITY_PRESETS["light"]["drops"]

    def test_heavy_intensity_more_drops(self, sample_manifest):
        """Heavy intensity should spawn more drops than light."""
        random.seed(0)
        light_plugin = WhiteNoisePlugin(sample_manifest)
        light_plugin.config = {"intensity": "light", "drop_color": "white"}
        light_plugin.fetch_data()

        random.seed(0)
        heavy_plugin = WhiteNoisePlugin(sample_manifest)
        heavy_plugin.config = {"intensity": "heavy", "drop_color": "white"}
        heavy_plugin.fetch_data()

        assert len(heavy_plugin._drops) >= len(light_plugin._drops)

    def test_custom_intensity_respects_drops_per_frame(self, sample_manifest):
        """Custom intensity should use drops_per_frame setting."""
        random.seed(0)
        plugin = WhiteNoisePlugin(sample_manifest)
        plugin.config = {
            "intensity": "custom",
            "drop_color": "white",
            "drops_per_frame": 7
        }
        result = plugin.fetch_data()
        # On first frame all drops are new spawns at row 0
        top_drops = [d for d in plugin._drops if d[0] == 0]
        assert len(top_drops) <= 7
        assert result.data["drops_per_frame"] == 7

    def test_max_drops_enforced(self, sample_manifest):
        """Plugin should not exceed max_drops limit."""
        random.seed(0)
        plugin = WhiteNoisePlugin(sample_manifest)
        plugin.config = {
            "intensity": "heavy",
            "drop_color": "white",
            "max_drops": 15
        }
        # Run multiple frames to build up drops
        for _ in range(10):
            plugin.fetch_data()
        assert len(plugin._drops) <= 15

    def test_max_drops_prevents_overflow(self, sample_manifest):
        """Very low max_drops should still work without errors."""
        random.seed(0)
        plugin = WhiteNoisePlugin(sample_manifest)
        plugin.config = {
            "intensity": "heavy",
            "drop_color": "white",
            "max_drops": 5
        }
        result = plugin.fetch_data()
        assert result.available is True
        assert len(plugin._drops) <= 5

    # ------------------------------------------------------------------ #
    # Drop colours
    # ------------------------------------------------------------------ #

    def test_drop_color_white(self, sample_manifest):
        """White drops should use BoardChars.WHITE."""
        random.seed(42)
        plugin = WhiteNoisePlugin(sample_manifest)
        plugin.config = {"intensity": "light", "drop_color": "white"}
        result = plugin.fetch_data()
        board = result.data["white_noise_array"]
        non_black = [
            code for row in board for code in row if code != BoardChars.BLACK
        ]
        assert all(c == BoardChars.WHITE for c in non_black)

    def test_drop_color_blue(self, sample_manifest):
        """Blue drops should use BoardChars.BLUE."""
        random.seed(42)
        plugin = WhiteNoisePlugin(sample_manifest)
        plugin.config = {"intensity": "light", "drop_color": "blue"}
        result = plugin.fetch_data()
        board = result.data["white_noise_array"]
        non_black = [
            code for row in board for code in row if code != BoardChars.BLACK
        ]
        assert all(c == BoardChars.BLUE for c in non_black)

    # ------------------------------------------------------------------ #
    # Board string conversion
    # ------------------------------------------------------------------ #

    def test_board_to_string_all_black(self, sample_manifest):
        """An empty board should render as all {black} markers."""
        plugin = WhiteNoisePlugin(sample_manifest)
        board = [[BoardChars.BLACK] * COLS for _ in range(ROWS)]
        result = plugin._board_to_string(board)
        assert "{white}" not in result
        assert "{black}" in result

    def test_board_to_string_contains_drop_marker(self, sample_manifest):
        """A board with a white drop should contain {white}."""
        plugin = WhiteNoisePlugin(sample_manifest)
        board = [[BoardChars.BLACK] * COLS for _ in range(ROWS)]
        board[0][0] = BoardChars.WHITE
        result = plugin._board_to_string(board)
        assert "{white}" in result

    # ------------------------------------------------------------------ #
    # cleanup
    # ------------------------------------------------------------------ #

    def test_cleanup_resets_drops(self, sample_manifest, sample_config):
        """cleanup() should clear the drop state."""
        plugin = WhiteNoisePlugin(sample_manifest)
        plugin.config = sample_config
        plugin.fetch_data()
        assert len(plugin._drops) > 0
        plugin.cleanup()
        assert plugin._drops == []

    # ------------------------------------------------------------------ #
    # Manifest consistency
    # ------------------------------------------------------------------ #

    def test_data_variables_match_manifest(self, sample_manifest, sample_config):
        """Returned data keys should include all manifest-declared variables."""
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        declared_vars = manifest["variables"]["simple"]

        plugin = WhiteNoisePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available
        for var in declared_vars:
            assert var in result.data, (
                f"Variable '{var}' declared in manifest but missing from data"
            )


class TestWhiteNoiseEdgeCases:
    """Edge-case and boundary tests."""

    def test_fetch_data_exception_handling(self, sample_manifest):
        """An internal error should return available=False."""
        plugin = WhiteNoisePlugin(sample_manifest)
        plugin.config = {"intensity": "light", "drop_color": "white"}

        with patch.object(plugin, "_step", side_effect=RuntimeError("boom")):
            result = plugin.fetch_data()
            assert result.available is False
            assert result.error is not None

    def test_board_all_valid_codes(self, sample_manifest, sample_config):
        """Every cell in the board must be a valid character code."""
        plugin = WhiteNoisePlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()
        for row in result.data["white_noise_array"]:
            for code in row:
                assert 0 <= code <= 71, f"Invalid character code: {code}"

    def test_no_duplicate_drop_positions(self, sample_manifest, sample_config):
        """No two drops should share the same position."""
        random.seed(42)
        plugin = WhiteNoisePlugin(sample_manifest)
        plugin.config = sample_config
        # Run several frames
        for _ in range(10):
            plugin.fetch_data()
        positions = {(r, c) for r, c in plugin._drops}
        assert len(positions) == len(plugin._drops)

    def test_multiple_frames_stability(self, sample_manifest, sample_config):
        """Running many frames should not crash or leak memory."""
        plugin = WhiteNoisePlugin(sample_manifest)
        plugin.config = sample_config
        for _ in range(50):
            result = plugin.fetch_data()
            assert result.available is True
        # After 50 frames drops should be bounded (max ROWS * COLS)
        assert len(plugin._drops) <= ROWS * COLS

    def test_default_config_fetch(self, sample_manifest):
        """fetch_data with entirely default config should succeed."""
        plugin = WhiteNoisePlugin(sample_manifest)
        plugin.config = {}
        result = plugin.fetch_data()
        assert result.available is True

    def test_custom_with_extreme_drops_per_frame(self, sample_manifest):
        """Custom mode with maximum drops_per_frame should work."""
        random.seed(42)
        plugin = WhiteNoisePlugin(sample_manifest)
        plugin.config = {
            "intensity": "custom",
            "drops_per_frame": 22,
            "max_drops": 100
        }
        result = plugin.fetch_data()
        assert result.available is True
        # Should spawn up to 22 drops on first frame
        assert len(plugin._drops) <= 22

    def test_max_drops_with_fast_cascade(self, sample_manifest):
        """Max drops should limit total drops even with many frames."""
        random.seed(0)
        plugin = WhiteNoisePlugin(sample_manifest)
        plugin.config = {
            "intensity": "heavy",
            "max_drops": 20
        }
        # Run enough frames to exceed max_drops if not limited
        for _ in range(20):
            plugin.fetch_data()
        assert len(plugin._drops) <= 20
