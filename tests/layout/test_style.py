"""Layout issues, the board target and the style cascade resolver (spec section 3)."""

from dataclasses import FrozenInstanceError, replace

import pytest

from src.layout.issues import ISSUE_CODES, LayoutIssue, LayoutIssueModel
from src.layout.style import (
    ResolvedLayout,
    board_style_for,
    device_default_style,
    resolve_block_style,
    resolve_color_value,
    resolve_layout,
)
from src.layout.target import FlexTarget, flex_target_for
from src.led.matrix import DEFAULT_LED_TEXT_COLOR, color_code_to_hex
from src.pages.flexible import FlexLayout
from src.templates.engine import TemplateEngine
from tests.layout.devices import profile

PIXOO = FlexTarget(rows=10, cols=16, display=profile("divoom_pixoo64", font="3x5"))
STRIP_MONO = FlexTarget(rows=1, cols=8, display=profile("max7219_4in1"))
FLAGSHIP = FlexTarget(rows=6, cols=22, display=None)

PANEL_RED = "#ff3b1f"  # the max7219 model's panel colour


# --- layout issues -------------------------------------------------------------------------------


def test_issue_to_json_carries_path_as_a_list():
    issue = LayoutIssue(path=("blocks", "b2", "style", "size"), code="size_rounded", severity="info", message="m")
    assert issue.to_json() == {
        "path": ["blocks", "b2", "style", "size"],
        "code": "size_rounded",
        "severity": "info",
        "message": "m",
    }


def test_issue_is_frozen():
    issue = LayoutIssue(path=("blocks",), code="wrapped", severity="info", message="m")
    with pytest.raises(FrozenInstanceError):
        issue.code = "shrunk"  # type: ignore[misc]


def test_issue_rejects_a_code_outside_the_catalogue():
    with pytest.raises(ValueError, match="sized_rounded"):
        LayoutIssue(path=(), code="sized_rounded", severity="info", message="m")


def test_issue_model_validates_the_json_form():
    issue = LayoutIssue(path=("regions", "r1"), code="dropped", severity="warning", message="m")
    model = LayoutIssueModel.model_validate(issue.to_json())
    assert model.model_dump() == issue.to_json()


def test_issue_codes_are_the_catalogue():
    expected = frozenset(
        {
            "font_unavailable",
            "glyph_fallback",
            "size_rounded",
            "size_too_small",
            "size_ignored",
            "color_invalid",
            "color_dropped",
            "background_dropped",
            "case_unsupported",
            "overflow_unsupported",
            "style_unknown",
            "block_kind_unsupported",
            "layout_kind_unsupported",
            "if_failed",
            "wrapped",
            "shrunk",
            "ellipsized",
            "truncated",
            "dropped",
            "canvas",
            "canvas_not_drawn",
            "surface_too_small",
        }
    )
    assert expected == ISSUE_CODES


# --- the board target ----------------------------------------------------------------------------


def test_pixel_target_properties_come_from_the_display():
    assert (PIXOO.pixels, PIXOO.width, PIXOO.height, PIXOO.color_model, PIXOO.default_face_id) == (
        True,
        64,
        64,
        "rgb",
        "3x5",
    )


def test_mono_target_reports_its_panel_colour():
    assert (STRIP_MONO.color_model, STRIP_MONO.monochrome) == ("mono", PANEL_RED)


def test_target_without_a_display_is_a_tile_board_of_cells():
    assert (FLAGSHIP.pixels, FLAGSHIP.width, FLAGSHIP.color_model, FLAGSHIP.mixed_case, FLAGSHIP.monochrome) == (
        False,
        None,
        "tiles",
        False,
        None,
    )


def test_flex_target_takes_the_grid_from_the_display():
    t = flex_target_for({"device_type": "flagship"}, PIXOO.display)
    assert (t.rows, t.cols) == (10, 16)


def test_flex_target_takes_the_grid_from_the_board_without_a_display_grid():
    t = flex_target_for({"device_type": "note"}, None)
    assert (t.rows, t.cols) == (3, 15)


def test_flex_target_defaults_to_the_flagship_grid():
    t = flex_target_for(None, None)
    assert (t.rows, t.cols, t.display) == (6, 22, None)


def test_board_style_is_empty_in_phase_1():
    assert dict(board_style_for({"device_type": "flagship"})) == {}
    assert dict(flex_target_for({"device_type": "flagship"}, None).board_style) == {}


# --- the cascade ---------------------------------------------------------------------------------


def test_cascade_block_beats_page_beats_board_beats_device():
    s, _ = resolve_block_style(
        [{"color": "#111111"}, {"color": "#222222"}, {"color": "#333333"}], PIXOO, {}, path=("blocks", "b1")
    )
    assert s.color == "#333333"
    s, _ = resolve_block_style([{"align": "right"}, None, {}], PIXOO, {}, path=("blocks", "b1"))
    assert s.align == "right"


def test_board_style_level_is_honoured_when_present():
    t = replace(PIXOO, board_style={"color": "#00ff00"})
    s, _ = resolve_block_style([t.board_style], t, {}, path=("blocks", "b1"))
    assert s.color == "#00ff00"


def test_device_defaults_apply_with_no_levels():
    s, issues = resolve_block_style([], PIXOO, {}, path=("blocks", "b1"))
    assert (s.family, s.px, s.color, s.background, s.align, s.case, s.overflow, s.height, s.fit) == (
        "fiesta",
        5,
        DEFAULT_LED_TEXT_COLOR,
        None,
        "left",
        "as-is",
        "wrap",
        "auto",
        False,
    )
    assert issues == []


def test_device_default_style_is_the_lowest_level():
    assert device_default_style(PIXOO)["size"] == "medium"
    assert device_default_style(PIXOO)["font"] == "fiesta"


# --- size ----------------------------------------------------------------------------------------


def test_named_large_on_pixoo_3x5_is_3x5_times_3():
    s, issues = resolve_block_style([{"size": "large"}], PIXOO, {}, path=("blocks", "b1"))
    assert (s.sized.face.id, s.sized.scale, s.px) == ("3x5", 3, 15) and issues == []


def test_exact_12px_rounds_down_with_issue():
    s, issues = resolve_block_style([{"size": 12}], PIXOO, {}, path=("blocks", "b1"))
    assert s.px == 10 and [i.code for i in issues] == ["size_rounded"]
    assert issues[0].path == ("blocks", "b1", "style", "size") and issues[0].severity == "info"


def test_exact_size_on_the_ladder_has_no_issue():
    s, issues = resolve_block_style([{"size": 14}], PIXOO, {}, path=("blocks", "b1"))
    assert (s.sized.face.id, s.sized.scale, s.px, issues) == ("5x7", 2, 14, [])


def test_size_below_the_smallest_face_is_too_small():
    s, issues = resolve_block_style([{"size": 3}], PIXOO, {}, path=("blocks", "b1"))
    assert s.px == 5 and [(i.code, i.severity) for i in issues] == [("size_too_small", "warning")]


def test_fit_size_is_flagged_for_the_fitter():
    s, issues = resolve_block_style([{"size": "fit"}], PIXOO, {}, path=("blocks", "b1"))
    assert s.fit is True and issues == []


def test_cell_target_ignores_a_non_medium_size():
    s, issues = resolve_block_style([{"size": "large"}], FLAGSHIP, {}, path=("blocks", "b1"))
    assert s.sized is None and [(i.code, i.severity) for i in issues] == [("size_ignored", "info")]


def test_cell_target_accepts_medium_silently():
    s, issues = resolve_block_style([{"size": "medium"}], FLAGSHIP, {}, path=("blocks", "b1"))
    assert s.sized is None and issues == []


# --- font ----------------------------------------------------------------------------------------


def test_unknown_font_falls_back_with_issue():
    s, issues = resolve_block_style([{"font": "comic"}], PIXOO, {}, path=("blocks", "b1"))
    assert s.family == "fiesta" and issues[0].code == "font_unavailable"


def test_unknown_board_style_font_also_reports():
    t = replace(PIXOO, board_style={"font": "serif"})
    s, issues = resolve_block_style([t.board_style, {"font": "comic"}], t, {}, path=("blocks", "b1"))
    assert s.family == "fiesta"
    assert [(i.code, i.severity) for i in issues] == [("font_unavailable", "warning"), ("font_unavailable", "warning")]


# --- colour --------------------------------------------------------------------------------------


def test_rgb_colour_name_resolves_to_the_board_palette():
    s, _ = resolve_block_style([{"color": "Blue", "background": "{64}"}], PIXOO, {}, path=("blocks", "b1"))
    assert (s.color, s.background) == ("#4a90d9", "#f5a623")


def test_mono_colour_maps_to_panel_and_black_stays_unlit():
    s, issues = resolve_block_style([{"color": "#00ff00", "background": "black"}], STRIP_MONO, {}, path=("b",))
    assert (s.color, s.background, issues) == (PANEL_RED, "#000000", [])


def test_rgb_black_text_is_unlit_like_a_grid_cell():
    # The cell renderer draws a black span as #000000 (unlit), not the palette's #1a1a1a.
    s, _ = resolve_block_style([{"color": "black", "background": "yellow"}], PIXOO, {}, path=("b",))
    assert s.color == "#000000"


def test_rgb_black_background_is_an_opaque_unlit_fill():
    s, issues = resolve_block_style([{"background": "black"}], PIXOO, {}, path=("b",))
    assert (s.background, issues) == ("#000000", [])


def test_rgb_black_tile_code_background_is_an_opaque_unlit_fill():
    s, _ = resolve_block_style([{"background": "{70}"}], PIXOO, {}, path=("b",))
    assert s.background == "#000000"


def test_transparent_background_clears_inherited_block_fill():
    from src.pages.flexible import BlockStyle

    style = BlockStyle.model_validate({"background": "transparent"})
    s, issues = resolve_block_style(
        [{"background": "#ff0000"}, style.model_dump(exclude_none=True)], PIXOO, {}, path=("b",)
    )
    assert s.background is None
    assert issues == []


def test_transparent_is_only_a_background_value():
    from pydantic import ValidationError

    from src.pages.flexible import BlockStyle

    with pytest.raises(ValidationError):
        BlockStyle.model_validate({"color": "transparent"})


@pytest.mark.parametrize("color", ["#010203", "#1a1a1a", "#1a001a"])
def test_rgb_text_preserves_exact_dim_color(color):
    s, issues = resolve_block_style([{"color": color}], PIXOO, {}, path=("b",))
    assert (s.color, issues) == (color, [])


def test_mono_lit_text_on_lit_background_is_inverse_video():
    # The grid renderer draws a background block on a mono panel as lit field, unlit glyph.
    s, _ = resolve_block_style([{"color": "white", "background": "yellow"}], STRIP_MONO, {}, path=("b",))
    assert (s.color, s.background) == (None, PANEL_RED)


def test_mono_red_text_is_lit_not_lost():
    # Spec 3: any non-black colour counts as lit, so contrast is preserved.
    s, _ = resolve_block_style([{"color": "red"}], STRIP_MONO, {}, path=("b",))
    assert s.color == PANEL_RED


def test_mono_black_text_is_unlit():
    s, _ = resolve_block_style([{"color": "#000000"}], STRIP_MONO, {}, path=("b",))
    assert s.color is None


def test_mono_default_text_is_the_panel_colour():
    s, _ = resolve_block_style([], STRIP_MONO, {}, path=("b",))
    assert s.color == PANEL_RED


def test_tiles_drop_text_colour_with_issue():
    _, issues = resolve_block_style([{"color": "red"}], FLAGSHIP, {}, path=("blocks", "b1"))
    assert issues[0].code == "color_dropped"


def test_tiles_drop_background_in_phase_1():
    s, issues = resolve_block_style([{"background": "red"}], FLAGSHIP, {}, path=("blocks", "b1"))
    assert s.background is None and [i.code for i in issues] == ["background_dropped"]
    assert issues[0].path == ("blocks", "b1", "style", "background")


def test_tiles_without_a_colour_request_report_nothing():
    s, issues = resolve_block_style([{"align": "center"}], FLAGSHIP, {}, path=("blocks", "b1"))
    assert (s.color, issues) == (None, [])


def test_invalid_colour_falls_through_to_the_level_below():
    s, issues = resolve_block_style(
        [{"color": "#222222"}, {"color": "{{x.y}}"}], PIXOO, {"x": {"y": "nope"}}, path=("blocks", "b1")
    )
    assert s.color == "#222222" and [i.code for i in issues] == ["color_invalid"]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("red", "#eb4034"),
        ("{63}", "#eb4034"),
        ("63", "#eb4034"),
        ("#FF8800", "#ff8800"),
        ("#ff8800 ", "#ff8800"),
        ("???", None),
        ("", None),
    ],
)
def test_color_expression_formats_plugins_emit(raw, expected):  # [RF-4]
    # The plan writes ``{{weather.temp_color}}``; the template engine reserves the
    # ``_color`` suffix for colour-rule lookups (no rules -> ""), so the raw value is
    # carried by a plain field. ``""`` is what an unmatched ``_color`` expands to.
    ctx = {"weather": {"tint": raw}}
    s, issues = resolve_block_style([{"color": "{{weather.tint}}"}], PIXOO, ctx, path=("blocks", "b1"))
    assert s.color == (expected or DEFAULT_LED_TEXT_COLOR)
    assert (expected is None) == any(i.code == "color_invalid" for i in issues)


def test_resolve_color_value_renders_through_the_given_engine():
    class Engine:
        def render(self, value, context, *, extended_markup):
            assert extended_markup is True
            return "{66}"

    assert resolve_color_value("{{anything}}", {}, engine=Engine()) == "#7ed321"


def test_resolve_color_value_never_raises_when_the_engine_does():
    class Engine:
        def render(self, value, context, *, extended_markup):
            raise RuntimeError("boom")

    assert resolve_color_value("{{anything}}", {}, engine=Engine()) is None


def test_resolve_color_value_with_the_real_engine():
    assert resolve_color_value("{{red}}", {}, engine=TemplateEngine()) == "#eb4034"


def test_color_code_to_hex_is_public():
    assert color_code_to_hex("66") == "#7ed321"
    assert color_code_to_hex("70") is None


# --- case and overflow ---------------------------------------------------------------------------


def test_lower_on_uppercase_only_board_reports_and_uppercases():
    s, issues = resolve_block_style([{"case": "lower"}], FLAGSHIP, {}, path=("blocks", "b1"))
    assert s.case == "upper" and [i.code for i in issues] == ["case_unsupported"]


def test_lower_on_mixed_case_board_is_kept():
    s, issues = resolve_block_style([{"case": "lower"}], PIXOO, {}, path=("blocks", "b1"))
    assert (s.case, issues) == ("lower", [])


def test_scroll_falls_back_to_ellipsis():
    s, issues = resolve_block_style([{"overflow": "scroll"}], PIXOO, {}, path=("blocks", "b1"))
    assert s.overflow == "ellipsis" and [i.code for i in issues] == ["overflow_unsupported"]


# --- unknown keys and height ---------------------------------------------------------------------


def test_unknown_style_key_is_reported_as_info():
    _, issues = resolve_block_style([{"shadow": "soft"}], PIXOO, {}, path=("blocks", "b1"))
    assert [(i.code, i.severity, i.path) for i in issues] == [
        ("style_unknown", "info", ("blocks", "b1", "style", "shadow"))
    ]


def test_height_passes_through():
    s, _ = resolve_block_style([{"height": "fill"}, {"height": 0.5}], PIXOO, {}, path=("blocks", "b1"))
    assert s.height == 0.5


# --- page layout ---------------------------------------------------------------------------------


@pytest.mark.parametrize("gap,px", [("none", 0), ("small", 1), ("medium", 2), ("large", 4), (3, 3)])
def test_layout_gap_px(gap, px):
    layout, issues = resolve_layout(FlexLayout(gap=gap), path=("layout",))
    assert layout.gap_px == px and issues == []


def test_layout_defaults_without_a_layout():
    assert resolve_layout(None, path=("layout",)) == (ResolvedLayout(kind="stack", valign="top", gap_px=1), [])


def test_unknown_layout_kind_is_laid_out_as_a_stack():
    layout, issues = resolve_layout(FlexLayout(kind="grid", valign="middle"), path=("layout",))
    assert (layout.kind, layout.valign) == ("stack", "middle")
    assert [(i.code, i.severity, i.path) for i in issues] == [
        ("layout_kind_unsupported", "warning", ("layout", "kind"))
    ]
