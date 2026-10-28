"""Tests for the shared board-geometry conformance suite.

The suite is what every plugin repository will be held to, so these tests
pin its behaviour from both sides: a plugin that adapts correctly must pass,
and plugins reproducing each real failure shape found in the plugin audit
must fail with the right code.
"""

import pytest

from src.devices import NOTE_COLS, NOTE_ROWS, BoardContext
from src.plugins.base import PluginBase, PluginResult
from src.plugins.geometry_conformance import (
    GROWTH_LADDER,
    LED_GEOMETRIES,
    PANEL_GEOMETRIES,
    STANDARD_GEOMETRIES,
    assert_board_conformance,
    check_growth,
    check_manifest,
    check_unbound_board,
    note_array,
    panel,
    run_conformance,
)

MANIFEST = {"id": "probe", "name": "Probe", "version": "1.0.0"}


class _Base(PluginBase):
    def __init__(self):
        super().__init__(MANIFEST)
        self._enabled = True

    @property
    def plugin_id(self) -> str:
        return "probe"


class AdaptivePlugin(_Base):
    """Derives every dimension from the bound board. The reference shape."""

    def fetch_data(self) -> PluginResult:
        board = self.board
        rows = board.rows if board else 6
        cols = board.cols if board else 22
        lines = [f"ROW {n}".center(cols) for n in range(rows)]
        return PluginResult(available=True, data={}, formatted_lines=lines)


class FixedFlagshipPlugin(_Base):
    """The Tier A shape: a hardcoded 22x6 block on every board."""

    def fetch_data(self) -> PluginResult:
        lines = ["HELLO".center(22) for _ in range(6)]
        return PluginResult(available=True, data={}, formatted_lines=lines)


class CappedListPlugin(_Base):
    """The data-cap shape: bounds rows correctly but never supplies past 3."""

    MAX_ITEMS = 3

    def fetch_data(self) -> PluginResult:
        board = self.board
        rows = board.rows if board else 6
        cols = board.cols if board else 22
        items = [f"ITEM {n}"[:cols] for n in range(self.MAX_ITEMS)]
        return PluginResult(available=True, data={}, formatted_lines=items[:rows])


class StaleCachePlugin(_Base):
    """The un-keyed cache shape: first geometry seen wins forever."""

    def __init__(self):
        super().__init__()
        self._frame: list[str] | None = None

    def fetch_data(self) -> PluginResult:
        if self._frame is None:
            board = self.board
            cols = board.cols if board else 22
            rows = board.rows if board else 6
            self._frame = ["X" * cols for _ in range(rows)]
        return PluginResult(available=True, data={}, formatted_lines=list(self._frame))


class CrashesOnUnboundPlugin(_Base):
    """Treats ``self.board`` as always present."""

    def fetch_data(self) -> PluginResult:
        cols = self.board.cols  # AttributeError when board is None
        return PluginResult(available=True, data={}, formatted_lines=["ok".center(cols)])


class ColourMarkerPlugin(_Base):
    """Emits colour markers: four characters, one tile."""

    def __init__(self, tiles_per_row: int):
        super().__init__()
        self._tiles = tiles_per_row

    def fetch_data(self) -> PluginResult:
        board = self.board
        rows = board.rows if board else 6
        return PluginResult(available=True, data={}, formatted_lines=["{66}" * self._tiles for _ in range(rows)])


class UnavailablePlugin(_Base):
    def fetch_data(self) -> PluginResult:
        return PluginResult(available=False, error="no network")


class HookOnlyPlugin(_Base):
    """Adapts fetch_data but leaves the documented hook hardcoded."""

    def fetch_data(self) -> PluginResult:
        board = self.board
        cols = board.cols if board else 22
        return PluginResult(available=True, data={}, formatted_lines=["ok".center(cols)])

    def get_formatted_display(self):
        return ["HELLO".center(22) for _ in range(6)]


def codes(report):
    return {v.code for v in report.violations}


class TestPassingPlugin:
    def test_adaptive_plugin_conforms(self):
        report = assert_board_conformance(AdaptivePlugin, strict_growth=True)
        assert report.ok

    def test_adaptive_plugin_fills_taller_boards(self):
        _, counts = check_growth(AdaptivePlugin)
        assert counts["15x3"] == 3
        assert counts["15x12"] == 12
        assert counts["15x24"] == 24

    def test_unavailable_result_is_not_a_violation(self):
        # Nothing reaches the board, which is a valid state rather than a
        # geometry failure -- the suite must not punish an offline plugin.
        report = run_conformance(UnavailablePlugin)
        assert report.ok


class TestHardcodedGeometry:
    def test_fixed_flagship_overflows_a_note(self):
        report = run_conformance(FixedFlagshipPlugin)
        assert not report.ok
        assert "TOO_MANY_ROWS" in codes(report)
        assert "ROW_TOO_WIDE" in codes(report)

    def test_violation_names_the_offending_geometry(self):
        report = run_conformance(FixedFlagshipPlugin)
        assert any("note 15x3" in v.geometry for v in report.violations)


class TestDataCaps:
    def test_capped_list_is_a_warning_by_default(self):
        report = run_conformance(CappedListPlugin)
        assert report.ok
        assert "SHRANK_ON_TALLER_BOARD" not in codes(report)

    def test_capped_list_fails_under_strict_growth(self):
        # 3 items exactly fill a 3-row Note, so there was more to show; a
        # 12-row board still rendering 3 is the cap, not a lack of content.
        report = run_conformance(CappedListPlugin, strict_growth=True)
        assert not report.ok
        assert "DID_NOT_GROW" in codes(report)

    def test_short_content_is_not_punished(self):
        # A plugin with genuinely little to say never fills the short board,
        # so the growth rule stays silent rather than demanding filler.
        class TwoLinePlugin(_Base):
            def fetch_data(self) -> PluginResult:
                board = self.board
                cols = board.cols if board else 22
                return PluginResult(
                    available=True, data={}, formatted_lines=["STARDATE".center(cols), "4523.7".center(cols)]
                )

        report = run_conformance(TwoLinePlugin, strict_growth=True)
        assert report.ok, report.summary()

    def test_cap_just_below_capacity_needs_opt_in_signal(self):
        # A cap of 10 renders 3 -> 11 -> 11. By default this is ambiguous
        # ("capped" vs "only had 10 items"), so the shared check stays silent.
        # Plugin-specific tests can opt in when fixture content is known to be
        # abundant enough that near-full should still grow.
        class CappedAt10(_Base):
            def fetch_data(self) -> PluginResult:
                board = self.board
                rows = board.rows if board else 6
                cols = board.cols if board else 22
                items = [f"ITEM{n}"[:cols] for n in range(min(10, max(0, rows - 1)))]
                return PluginResult(available=True, data={}, formatted_lines=["HDR".center(cols), *items])

        violations, counts = check_growth(CappedAt10)
        assert counts == {"15x3": 3, "15x12": 11, "15x24": 11}, counts
        assert violations == []

        strict_violations, _ = check_growth(CappedAt10, near_full_slack_rows=1)
        assert [v.code for v in strict_violations] == ["DID_NOT_GROW"]

        report = run_conformance(CappedAt10, strict_growth=True, near_full_slack_rows=1)
        assert not report.ok
        assert "DID_NOT_GROW" in codes(report)

    def test_growth_ladder_holds_width_constant(self):
        widths = {g.cols for g in GROWTH_LADDER}
        assert widths == {15}, "growth must vary height alone to avoid confounding"


class TestStaleCache:
    def test_unkeyed_cache_surfaces_as_out_of_bounds(self):
        # The first geometry rendered is the Flagship, so the cached 22-wide
        # frame is then served to the 15-wide Note.
        report = run_conformance(StaleCachePlugin)
        assert not report.ok
        assert "ROW_TOO_WIDE" in codes(report) or "TOO_MANY_ROWS" in codes(report)


class TestUnboundBoard:
    def test_crash_on_none_board_is_reported(self):
        violations = check_unbound_board(CrashesOnUnboundPlugin)
        assert [v.code for v in violations] == ["UNBOUND_RAISED"]

    def test_adaptive_plugin_handles_none_board(self):
        assert check_unbound_board(AdaptivePlugin) == []


class TestTileCounting:
    def test_colour_markers_count_as_one_tile(self):
        # 10 markers is 40 characters but exactly 10 tiles, so it fits the
        # narrowest board (an LED board in its large face, 10 wide).
        report = run_conformance(lambda: ColourMarkerPlugin(10))
        assert "ROW_TOO_WIDE" not in codes(report)

    def test_too_many_markers_still_overflows(self):
        report = run_conformance(lambda: ColourMarkerPlugin(30))
        assert "ROW_TOO_WIDE" in codes(report)
        assert any("note 15x3" in v.geometry for v in report.violations)


class TestDocumentedHook:
    def test_hardcoded_hook_is_caught_even_though_core_never_calls_it(self):
        report = run_conformance(HookOnlyPlugin)
        assert not report.ok
        assert any("get_formatted_display()" in v.detail for v in report.violations)


class TestGeometryMatrix:
    def test_matrix_covers_both_awkward_aspect_ratios(self):
        shapes = {(g.cols, g.rows) for g in STANDARD_GEOMETRIES}
        assert (15, 12) in shapes, "tall-narrow array is narrower than a Flagship"
        assert (120, 3) in shapes, "wide-short array is wider but shorter"

    def test_note_array_helper_matches_platform_geometry(self):
        assert note_array(2, 4) == BoardContext("note_array", rows=12, cols=30)
        assert note_array(8, 8) == BoardContext("note_array", rows=24, cols=120)

    def test_matrix_covers_panel_grids_that_are_not_note_multiples(self):
        """Panels are fit per character, so plugins must not assume Note multiples."""
        panels = [g for g in STANDARD_GEOMETRIES if g.board.device_type == "panel"]
        assert any(g.cols % NOTE_COLS for g in panels), "a width that is not a multiple of 15"
        assert any(g.rows % NOTE_ROWS for g in panels), "a height that is not a multiple of 3"

    def test_matrix_covers_a_portrait_panel(self):
        assert any(g.board.device_type == "panel" and g.rows > g.cols for g in STANDARD_GEOMETRIES)

    def test_matrix_panel_grids_are_real_autofit_results(self):
        """Every panel geometry is what some TV actually fits to — not a made-up size."""
        from src.panels.autofit import compute_autofit_grid

        fits = {
            tuple(compute_autofit_grid(d, aw, ah))
            for d in range(3, 201)
            for aw, ah in ((16, 9), (9, 16), (21, 9), (4, 3))
        }
        for g in PANEL_GEOMETRIES:
            assert (g.rows, g.cols) in fits, g.label

    def test_matrix_led_grids_are_real_led_boards_in_the_large_face(self):
        """Every LED geometry is what a real LED model shows in 5x7, and both are in the matrix."""
        from src.fiestaui import builtin_device_models
        from src.led.matrix import model_with_led_font
        from src.outputs.geometry import model_cell_grid

        models = builtin_device_models()
        real = {
            model_cell_grid(model_with_led_font(models["divoom_pixoo64"], "5x7")),
            model_cell_grid(models["hub75_64x32"]),
        }
        assert {(g.rows, g.cols) for g in LED_GEOMETRIES} == real == {(8, 10), (4, 10)}
        assert set(LED_GEOMETRIES) <= set(STANDARD_GEOMETRIES)

    def test_panel_helper_builds_a_panel_context(self):
        assert panel(12, 29) == BoardContext("panel", rows=12, cols=29)


class TestManifestChecks:
    def test_long_max_lengths_warn(self):
        _, warnings = check_manifest({"max_lengths": {"formatted": 22, "short": 12}})
        long_warnings = [w for w in warnings if w.code == "MAX_LENGTH_EXCEEDS_NOTE"]
        assert len(long_warnings) == 1, "only the over-15 entry should warn"
        assert "formatted" in long_warnings[0].detail

    def test_missing_note_array_preview_warns_by_default(self):
        manifest = {"previews": [{"device_type": "flagship", "rows": []}]}
        violations, warnings = check_manifest(manifest)
        assert violations == []
        assert [w.code for w in warnings] == ["NO_NOTE_ARRAY_PREVIEW"]

    def test_missing_note_array_preview_can_be_required(self):
        manifest = {"previews": [{"device_type": "flagship", "rows": []}]}
        violations, _ = check_manifest(manifest, require_note_array_preview=True)
        assert [v.code for v in violations] == ["NO_NOTE_ARRAY_PREVIEW"]

    def test_note_array_preview_satisfies_the_check(self):
        manifest = {
            "previews": [
                {"device_type": "flagship", "rows": []},
                {"device_type": "note_array", "notes_wide": 2, "notes_tall": 2, "rows": []},
            ]
        }
        violations, warnings = check_manifest(manifest, require_note_array_preview=True)
        assert violations == []
        assert warnings == []


class TestAssertHelper:
    def test_assertion_message_carries_the_report(self):
        with pytest.raises(AssertionError) as excinfo:
            assert_board_conformance(FixedFlagshipPlugin)
        message = str(excinfo.value)
        assert "conformance" in message
        assert "TOO_MANY_ROWS" in message or "ROW_TOO_WIDE" in message
