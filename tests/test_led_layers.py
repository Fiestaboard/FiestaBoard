"""LED bitmap layers: a page's pixel canvases drawn over the cells (design §3 steps 5-6).

The goldens are FiestaUI's own bytes (``tests/fixtures/fiestaui-led-layers.json``,
copied from Fiestaboard/FiestaUI#343 at a8a62517): two layouts (alpha,
clipping, a monochrome panel) and two transitions (a half-flap flip whose
layers swap half-way, a fade between layers alone).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from src.canvas import CanvasLayer
from src.led import LedLayoutOptions, LedMatrixSpec, layout_message, rasterize
from src.led.matrix import LedBitmapLayer, decode_layers, grid_layout, layout_cells
from src.led.transitions import LedTransitionSpec, plan_transition, transition_frames

FIXTURE = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "fiestaui-led-layers.json").read_text(encoding="utf-8")
)
LAYOUTS = FIXTURE["layouts"]
TRANSITIONS = FIXTURE["transitions"]


def _spec(raw: dict) -> LedMatrixSpec:
    return LedMatrixSpec(width=raw["width"], height=raw["height"], font=raw.get("font", "5x7"))


def _layout_case(case: dict):
    raw = case.get("options", {})
    options = LedLayoutOptions(monochrome=raw.get("monochrome"), text_color=raw.get("textColor"))
    return layout_message(case["message"], _spec(case["spec"]), options, layers=raw.get("layers", ()))


def _diff(actual: bytes, expected: bytes, width: int, limit: int = 6) -> str:
    out = []
    for p in range(min(len(actual), len(expected)) // 3):
        got, want = actual[p * 3 : p * 3 + 3], expected[p * 3 : p * 3 + 3]
        if got != want:
            out.append(f"  ({p % width}, {p // width}): got #{got.hex()} want #{want.hex()}")
            if len(out) == limit:
                break
    return "\n".join(out)


def test_fixture_holds_the_four_layer_cases_from_fiestaui_343():
    assert FIXTURE["source"]["commit"] == "a8a62517"
    assert len(LAYOUTS) == 2 and len(TRANSITIONS) == 2


@pytest.mark.parametrize("case", LAYOUTS, ids=[c["name"] for c in LAYOUTS])
def test_layer_layout_frame_matches_fiestaui(case):
    layout = _layout_case(case)
    frame = rasterize(layout)
    expected = base64.b64decode(case["frame"])
    assert layout.text == case["text"]
    assert frame.pixels == expected, "first differing pixels:\n" + _diff(frame.pixels, expected, frame.width)


@pytest.mark.parametrize("case", TRANSITIONS, ids=[c["name"] for c in TRANSITIONS])
def test_layer_transition_frames_match_fiestaui(case):
    spec = _spec(case["spec"])
    before = layout_message(case["from"], spec, layers=case["fromLayers"])
    after = layout_message(case["to"], spec, layers=case["toLayers"])
    tr = plan_transition(before, after, LedTransitionSpec.from_dict(case["transition"]))
    assert (tr.duration_ms, tr.frame_count) == (case["durationMs"], case["frameCount"])
    frames = transition_frames(tr, case.get("fps", 30))
    expected = [base64.b64decode(f) for f in case["frames"]]
    assert len(frames) == len(expected)
    for i, (frame, want) in enumerate(zip(frames, expected, strict=True)):
        assert frame.pixels == want, f"frame {i} of {len(expected)} differs:\n" + _diff(frame.pixels, want, frame.width)


# --- the rules, one by one ---------------------------------------------------

S = LedMatrixSpec(width=12, height=5, font="3x5")


def _solid(x, y, w, h, rgba=(10, 20, 30, 255)) -> CanvasLayer:
    return CanvasLayer(x=x, y=y, w=w, h=h, rgba=bytes(rgba) * (w * h))


def _px(frame, x, y) -> bytes:
    i = (y * frame.width + x) * 3
    return frame.pixels[i : i + 3]


def test_no_layers_draws_exactly_what_it_drew_before():
    plain = layout_message("AB", S)
    empty = layout_message("AB", S, layers=())
    assert empty.ops == plain.ops
    assert empty.layers == ()
    assert rasterize(empty).pixels == rasterize(plain).pixels


def test_layers_are_bitmap_ops_after_every_cell_op():
    layout = layout_message("AB", S, layers=[_solid(0, 0, 2, 2), _solid(4, 0, 1, 1)])
    kinds = [op.kind for op in layout.ops]
    assert kinds[-2:] == ["bitmap", "bitmap"]
    assert "bitmap" not in kinds[:-2]


def test_alpha_above_zero_overwrites_without_blending_and_zero_is_transparent():
    under = rasterize(layout_message("AB", S))
    half = CanvasLayer(x=0, y=0, w=2, h=1, rgba=bytes([200, 100, 50, 1, 9, 9, 9, 0]))
    frame = rasterize(layout_message("AB", S, layers=[half]))
    assert _px(frame, 0, 0) == bytes([200, 100, 50])
    assert _px(frame, 1, 0) == _px(under, 1, 0)


def test_later_layers_paint_over_earlier_ones():
    frame = rasterize(layout_message("", S, layers=[_solid(0, 0, 2, 2, (1, 2, 3, 255)), _solid(1, 1, 2, 2)]))
    assert _px(frame, 0, 0) == bytes([1, 2, 3])
    assert _px(frame, 1, 1) == bytes([10, 20, 30])


def test_layers_clip_to_the_matrix_and_never_wrap_rows():
    frame = rasterize(layout_message("", S, layers=[_solid(10, 0, 4, 1)]))
    assert _px(frame, 11, 0) == bytes([10, 20, 30])
    assert _px(frame, 0, 1) == bytes([0, 0, 0])  # the 2 pixels past x=11 do not wrap to row 1


def test_monochrome_lights_bright_pixels_in_the_panel_colour_and_turns_dark_ones_off():
    bright = CanvasLayer(x=0, y=0, w=1, h=1, rgba=bytes([255, 255, 255, 255]))
    red = CanvasLayer(x=0, y=0, w=1, h=1, rgba=bytes([255, 0, 0, 255]))  # luma below 50%
    options = LedLayoutOptions(monochrome="#ff3b1f")
    assert _px(rasterize(layout_message("", S, options, layers=[bright])), 0, 0) == bytes([0xFF, 0x3B, 0x1F])
    lit_under = rasterize(layout_message("{63}", S, options))
    assert _px(lit_under, 0, 0) != bytes([0, 0, 0])
    assert _px(rasterize(layout_message("{63}", S, options, layers=[red])), 0, 0) == bytes([0, 0, 0])


def test_layers_accept_the_json_form_and_layout_cells_takes_them_too():
    layer = _solid(0, 0, 2, 1)
    from_json = layout_message("", S, layers=[layer.to_json()])
    assert from_json.layers == (LedBitmapLayer(0, 0, 2, 1, layer.rgba),)
    grid = grid_layout(S.width, S.height, S.font)
    cells_layout = layout_cells(grid, list(from_json.cells), from_json.options, layers=[layer])
    assert rasterize(cells_layout).pixels == rasterize(from_json).pixels


def test_decode_drops_empty_layers_and_fits_short_buffers():
    decoded = decode_layers(
        [
            {"x": 0, "y": 0, "width": 0, "height": 3, "rgba": ""},
            {"x": 1.7, "y": 0, "width": 2, "height": 1, "rgba": base64.b64encode(bytes([1, 2, 3, 255])).decode()},
        ]
    )
    assert decoded == (LedBitmapLayer(1, 0, 2, 1, bytes([1, 2, 3, 255, 0, 0, 0, 0])),)


# --- transitions -------------------------------------------------------------


def _flip(before_layers, after_layers, before="AB", after="CD"):
    spec = LedTransitionSpec.from_dict(
        {"kind": "flip", "stepMs": 80, "scrambleSteps": 3, "stagger": 0, "halfFlap": False}
    )
    a = layout_message(before, S, layers=before_layers)
    b = layout_message(after, S, layers=after_layers)
    return plan_transition(a, b, spec)


def test_flip_uses_the_before_layers_for_the_first_half_and_the_after_layers_for_the_second():
    old, new = _solid(0, 4, 12, 1, (255, 0, 0, 255)), _solid(0, 4, 12, 1, (0, 0, 255, 255))
    tr = _flip([old], [new])
    frames = tr.frame_count
    assert frames == 5  # stagger 0 + 3 scramble + 2
    for f in range(frames):
        want = (0, 0, 255) if 2 * f >= frames - 1 else (255, 0, 0)
        assert _px(tr.frame_at_index(f), 0, 4) == bytes(want), f"frame {f}"


def test_cascade_switches_layers_at_half_the_changed_cells():
    old, new = _solid(0, 4, 12, 1, (255, 0, 0, 255)), _solid(0, 4, 12, 1, (0, 0, 255, 255))
    a = layout_message("ABC", S, layers=[old])  # a 3-column grid: three changed cells
    b = layout_message("XYZ", S, layers=[new])
    tr = plan_transition(a, b, LedTransitionSpec.from_dict({"kind": "cascade", "durationMs": 300}))
    slot = tr.duration_ms / 3
    for n in range(3):
        want = (0, 0, 255) if 2 * n >= 3 else (255, 0, 0)
        assert _px(tr.frame_at(n * slot + slot / 2), 0, 4) == bytes(want), f"slot {n}"


def test_a_layers_only_change_snaps_a_per_cell_kind():
    tr = _flip([_solid(0, 4, 2, 1, (255, 0, 0, 255))], [_solid(0, 4, 2, 1, (0, 255, 0, 255))], "AB", "AB")
    assert tr.duration_ms == 0
    assert _px(tr.frame_at(0), 0, 4) == bytes([0, 255, 0])


def test_fade_between_layers_alone_animates():
    a = layout_message("HI", S, layers=[_solid(0, 4, 12, 1, (255, 0, 0, 255))])
    b = layout_message("HI", S, layers=[_solid(0, 4, 12, 1, (0, 0, 255, 255))])
    tr = plan_transition(a, b, LedTransitionSpec.from_dict({"kind": "fade", "durationMs": 200}))
    assert tr.duration_ms == 200
    mid = _px(tr.frame_at(100), 0, 4)
    assert mid not in (bytes([255, 0, 0]), bytes([0, 0, 255]))


def test_layers_stay_on_top_of_every_half_turned_flap():
    cover = _solid(0, 0, 12, 5, (9, 9, 9, 255))  # the whole panel
    spec = LedTransitionSpec.from_dict(
        {"kind": "flip", "stepMs": 80, "scrambleSteps": 2, "stagger": 0, "halfFlap": True}
    )
    tr = plan_transition(layout_message("AB", S, layers=[cover]), layout_message("CD", S, layers=[cover]), spec)
    for t in range(0, int(tr.duration_ms) + 1, 20):
        assert set(tr.frame_at(t).pixels) == {9}, f"t={t}"


def test_a_cascade_half_flap_keeps_the_layers_on_top():
    cover = _solid(0, 0, 12, 5, (9, 9, 9, 255))
    spec = LedTransitionSpec.from_dict({"kind": "cascade", "durationMs": 300})
    tr = plan_transition(layout_message("ABC", S, layers=[cover]), layout_message("XYZ", S, layers=[cover]), spec)
    for t in range(0, int(tr.duration_ms) + 1, 25):
        assert set(tr.frame_at(t).pixels) == {9}, f"t={t}"
