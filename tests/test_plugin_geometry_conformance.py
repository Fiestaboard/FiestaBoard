"""Tests for the shared board-geometry conformance suite.

The suite is what every plugin repository will be held to, so these tests
pin its behaviour from both sides: a plugin that adapts correctly must pass,
and plugins reproducing each real failure shape found in the plugin audit
must fail with the right code.
"""

import pytest

from src.devices import BoardContext
from src.plugins.base import PluginBase, PluginResult
from src.plugins.geometry_conformance import (
    GROWTH_LADDER,
    STANDARD_GEOMETRIES,
    assert_board_conformance,
    check_growth,
    check_manifest,
    check_unbound_board,
    note_array,
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

    def test_cap_just_below_capacity_is_a_known_blind_spot(self):
        # Pins a limit rather than a feature, so nobody assumes this is covered.
        # A cap of 10 renders 3 -> 11 -> 11: 11 of 12 rows is not saturation,
        # so no growth is required at the next rung and the cap passes.
        #
        # This is not fixable from here. "Capped at 10" and "only had 7 things
        # to show" give identical row counts, and the suite cannot see how much
        # content the plugin's upstream had. Widening the rule to catch the
        # first misreports every plugin whose fixture or maxItems config is
        # legitimately small -- when tried, it flagged four correct plugins.
        # A data cap belongs in a plugin's own test, asserting the cap scales
        # with the board rather than asserting a rendered row count.
        class CappedAt10(_Base):
            def fetch_data(self) -> PluginResult:
                board = self.board
                rows = board.rows if board else 6
                cols = board.cols if board else 22
                items = [f"ITEM{n}"[:cols] for n in range(min(10, max(0, rows - 1)))]
                return PluginResult(
                    available=True, data={}, formatted_lines=["HDR".center(cols), *items]
                )

        violations, counts = check_growth(CappedAt10)
        assert counts == {"15x3": 3, "15x12": 11, "15x24": 11}, counts
        assert violations == [], (
            "documented blind spot: if this now reports a violation the suite "
            "got stricter, which is good -- verify it does not also flag a "
            "plugin whose content is legitimately short, then update this test"
        )

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
        # 15 markers is 60 characters but exactly 15 tiles, so it fits a Note.
        report = run_conformance(lambda: ColourMarkerPlugin(15))
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
