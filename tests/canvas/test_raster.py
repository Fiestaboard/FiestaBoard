"""Pixel-exact goldens for the pure-Python canvas rasteriser.

Goldens are drawn as ASCII: ``.`` is a transparent pixel, every other
character is the colour named in the test's legend.
"""

import time

import pytest

from src.canvas.evaluate import resolve_canvas
from src.canvas.models import Canvas
from src.canvas.raster import fit_nearest, rasterize, render_content, upscale
from src.led.fonts import LED_FONTS

R = (255, 0, 0, 255)
G = (0, 255, 0, 255)
B = (0, 0, 255, 255)
W = (255, 255, 255, 255)
LEGEND = {R: "R", G: "G", B: "B", W: "W"}


def _resolve(content, context=None):
    canvas = Canvas.model_validate({"id": "t", "area": {"row": 1, "col": 1, "rows": 1, "cols": 1}, "content": content})
    resolved, issues = resolve_canvas(canvas, context or {})
    assert issues == []
    return resolved


def _ascii(rgba: bytes, width: int, height: int) -> list[str]:
    assert len(rgba) == width * height * 4
    rows = []
    for y in range(height):
        row = ""
        for x in range(width):
            px = tuple(rgba[(y * width + x) * 4 : (y * width + x) * 4 + 4])
            row += "." if px[3] == 0 else LEGEND.get(px, "?")
        rows.append(row)
    return rows


def _draw(shapes, size=(8, 8), **content):
    resolved = _resolve({"shapes": shapes, **content})
    return _ascii(rasterize(resolved, *size), *size)


def test_empty_content_is_transparent():
    assert rasterize(_resolve({}), 2, 2) == bytes(16)


def test_filled_rect():
    assert _draw([{"type": "rect", "x": 1, "y": 1, "w": 3, "h": 2, "fill": "#f00"}]) == [
        "........",
        ".RRR....",
        ".RRR....",
        "........",
        "........",
        "........",
        "........",
        "........",
    ]


def test_stroked_rect_and_stroke_over_fill():
    assert _draw(
        [
            {"type": "rect", "x": 0, "y": 0, "w": 4, "h": 3, "stroke": "#00f"},
            {"type": "rect", "x": 4, "y": 4, "w": 4, "h": 4, "fill": "#0f0", "stroke": "#fff"},
        ]
    ) == [
        "BBBB....",
        "B..B....",
        "BBBB....",
        "........",
        "....WWWW",
        "....WGGW",
        "....WGGW",
        "....WWWW",
    ]


def test_rect_float_coordinates_round_half_up_and_clip():
    # x 0.5 -> 1, x+w 2.5 -> 3; a rect running off the canvas is clipped.
    assert _draw([{"type": "rect", "x": 0.5, "y": -2, "w": 2, "h": 3, "fill": "#f00"}], size=(4, 2)) == [
        ".RR.",
        "....",
    ]


def test_negative_size_rect_is_normalised():
    assert _draw([{"type": "rect", "x": 3, "y": 2, "w": -2, "h": -2, "fill": "#f00"}], size=(4, 3)) == [
        ".RR.",
        ".RR.",
        "....",
    ]


def test_filled_circle():
    assert _draw([{"type": "circle", "cx": 4, "cy": 4, "r": 3, "fill": "#f00"}]) == [
        "........",
        "..RRRR..",
        ".RRRRRR.",
        ".RRRRRR.",
        ".RRRRRR.",
        ".RRRRRR.",
        "..RRRR..",
        "........",
    ]


def test_stroked_circle_is_a_one_pixel_ring():
    assert _draw([{"type": "circle", "cx": 4, "cy": 4, "r": 4, "stroke": "#fff"}]) == [
        "..WWWW..",
        ".W....W.",
        "W......W",
        "W......W",
        "W......W",
        "W......W",
        ".W....W.",
        "..WWWW..",
    ]


def test_filled_ellipse():
    assert _draw([{"type": "ellipse", "cx": 4, "cy": 2, "rx": 4, "ry": 2, "fill": "#0f0"}], size=(8, 4)) == [
        ".GGGGGG.",
        "GGGGGGGG",
        "GGGGGGGG",
        ".GGGGGG.",
    ]


def test_line_bresenham():
    assert _draw([{"type": "line", "x1": 0, "y1": 0, "x2": 7, "y2": 3, "stroke": "#f00"}], size=(8, 4)) == [
        "RR......",
        "..RR....",
        "....RR..",
        "......RR",
    ]


def test_line_is_the_same_drawn_either_way():
    # Plain Bresenham from (4, 1) back to (0, 0) would draw "RRR.." / "...RR".
    forward = _draw([{"type": "line", "x1": 0, "y1": 0, "x2": 4, "y2": 1, "stroke": "#f00"}], size=(5, 2))
    backward = _draw([{"type": "line", "x1": 4, "y1": 1, "x2": 0, "y2": 0, "stroke": "#f00"}], size=(5, 2))
    assert forward == ["RR...", "..RRR"]
    assert backward == forward


def test_diagonal_line():
    rows = _draw([{"type": "line", "x1": 0, "y1": 0, "x2": 7.9, "y2": 7.9, "stroke": "#f00"}])
    # Endpoints floor to their pixel: 7.9 is pixel 7.
    assert rows == [("." * i) + "R" + ("." * (7 - i)) for i in range(8)]


def test_wide_line_stamps_a_square_brush():
    assert _draw([{"type": "line", "x1": 1, "y1": 2, "x2": 5, "y2": 2, "stroke": "#00f", "width": 3}], size=(8, 5)) == [
        "........",
        "BBBBBBB.",
        "BBBBBBB.",
        "BBBBBBB.",
        "........",
    ]


def test_triangle_polygon():
    assert _draw([{"type": "polygon", "points": [[0, 0], [8, 0], [0, 8]], "fill": "#f00"}]) == [
        "RRRRRRR.",
        "RRRRRR..",
        "RRRRR...",
        "RRRR....",
        "RRR.....",
        "RR......",
        "R.......",
        "........",
    ]


def test_polygon_fill_is_even_odd():
    # Inner square wound the SAME way as the outer one: non-zero would fill
    # it, even-odd leaves a hole.
    points = [[0, 0], [8, 0], [8, 8], [0, 8], [0, 0], [2, 2], [6, 2], [6, 6], [2, 6], [2, 2]]
    assert _draw([{"type": "polygon", "points": points, "fill": "#f00"}]) == [
        "RRRRRRRR",
        "RRRRRRRR",
        "RR....RR",
        "RR....RR",
        "RR....RR",
        "RR....RR",
        "RRRRRRRR",
        "RRRRRRRR",
    ]


def test_polygon_stroke_closes_the_outline():
    assert _draw([{"type": "polygon", "points": [[0, 0], [4, 0], [4, 3], [0, 3]], "stroke": "#fff"}], size=(5, 4)) == [
        "WWWWW",
        "W...W",
        "W...W",
        "WWWWW",
    ]


def test_text_uses_led_font_bitmaps():
    face = LED_FONTS["3x5"]
    rows = _draw([{"type": "text", "x": 1, "y": 1, "text": "AB", "color": "#fff", "font": "3x5"}], size=(9, 7))
    a, b = face.glyphs["A"], face.glyphs["B"]
    gap = "." * face.spacing_x
    expected = ["." * 9] + ["." + a[i].replace("#", "W") + gap + b[i].replace("#", "W") + "." for i in range(5)]
    expected.append("." * 9)
    assert rows == expected


def test_text_lower_case_and_newline():
    face = LED_FONTS["3x5"]
    rows = _draw([{"type": "text", "x": 0, "y": 0, "text": "a\nb", "color": "#fff", "font": "3x5"}], size=(3, 11))
    a, b = face.glyphs["a"], face.glyphs["b"]
    assert rows[:5] == [r.replace("#", "W") for r in a]
    assert rows[5] == "..."
    assert rows[6:] == [r.replace("#", "W") for r in b]


def test_text_defaults_to_5x7():
    face = LED_FONTS["5x7"]
    rows = _draw([{"type": "text", "x": 0, "y": 0, "text": "H", "color": "#fff"}], size=(5, 7))
    assert rows == [r.replace("#", "W") for r in face.glyphs["H"]]


def _channel(rgba: bytes, width: int, x: int, y: int, c: int = 0) -> int:
    return rgba[(y * width + x) * 4 + c]


def test_gradient_left_to_right():
    rgba = rasterize(_resolve({"shapes": [{"type": "gradient", "from": "#000", "to": "#f00", "angle": 0}]}), 4, 1)
    # Pixel centres at t = 1/8, 3/8, 5/8, 7/8 of 255, rounded half up.
    assert [_channel(rgba, 4, x, 0) for x in range(4)] == [32, 96, 159, 223]
    assert all(_channel(rgba, 4, x, 0, 3) == 255 for x in range(4))


def test_gradient_default_is_top_to_bottom():
    rgba = rasterize(_resolve({"shapes": [{"type": "gradient", "from": "#000", "to": "#f00"}]}), 1, 4)
    assert [_channel(rgba, 1, 0, y) for y in range(4)] == [32, 96, 159, 223]


def test_gradient_180_reverses():
    rgba = rasterize(_resolve({"shapes": [{"type": "gradient", "from": "#000", "to": "#f00", "angle": 180}]}), 4, 1)
    assert [_channel(rgba, 4, x, 0) for x in range(4)] == [223, 159, 96, 32]


def test_gradient_region():
    rgba = rasterize(
        _resolve({"shapes": [{"type": "gradient", "x": 1, "y": 0, "w": 2, "h": 1, "from": "#f00", "to": "#f00"}]}), 4, 1
    )
    assert _ascii(rgba, 4, 1) == [".RR."]


def test_background_then_shapes_then_pixels():
    rows = _draw(
        [{"type": "rect", "x": 0, "y": 0, "w": 2, "h": 2, "fill": "#f00"}],
        size=(3, 2),
        background="#00f",
        palette={"w": "#fff", "n": "none"},
        pixels=["w.n", ".w"],
    )
    # "." and a "none" palette entry leave what is under them.
    assert rows == ["WRB", "RWB"]


def test_pixels_beyond_the_content_are_clipped():
    rows = _draw([], size=(2, 1), palette={"w": "#fff"}, pixels=["www", "www"])
    assert rows == ["WW"]


def test_transparent_fill_draws_nothing():
    assert _draw([{"type": "rect", "x": 0, "y": 0, "w": 2, "h": 1, "fill": "none"}], size=(2, 1)) == [".."]


# --- Scaling ------------------------------------------------------------------


def test_fit_nearest_letterboxes_and_centres():
    src = bytes(R) + bytes(B)  # 2 x 1
    out = fit_nearest(src, 2, 1, 4, 4)
    assert _ascii(out, 4, 4) == ["....", "RRBB", "RRBB", "...."]


def test_fit_nearest_pillarboxes():
    src = bytes(R) + bytes(B)  # 1 x 2
    out = fit_nearest(src, 1, 2, 5, 4)
    assert _ascii(out, 5, 4) == [".RR..", ".RR..", ".BB..", ".BB.."]


def test_fit_nearest_non_integer_factor_is_floor_sampled():
    src = bytes(R) + bytes(G) + bytes(B)  # 3 x 1
    out = fit_nearest(src, 3, 1, 7, 1)
    # Height-bound: 3 x 1 fits 7 x 1 at 3 x 1, centred ((7 - 3) // 2 = 2).
    assert _ascii(out, 7, 1) == ["..RGB.."]


def test_fit_nearest_square_upsample():
    src = bytes(R) + bytes(G) + bytes(B) + bytes(W) + bytes(R) + bytes(G) + bytes(B) + bytes(W) + bytes(R)
    out = fit_nearest(src, 3, 3, 7, 7)
    # Source column for target x is x * 3 // 7: 0,0,0,1,1,2,2.
    assert _ascii(out, 7, 7)[0] == "RRRGGBB"
    assert _ascii(out, 7, 7)[3] == "WWWRRGG"


def test_fit_same_size_is_identity():
    src = bytes(R) + bytes(G)
    assert fit_nearest(src, 2, 1, 2, 1) == src


def test_upscale():
    src = bytes(R) + bytes(B)
    assert _ascii(upscale(src, 2, 1, 2), 4, 2) == ["RRBB", "RRBB"]


def test_render_content_uses_size_then_fits():
    resolved = _resolve({"size": [2, 1], "palette": {"r": "#f00", "b": "#00f"}, "pixels": ["rb"]})
    assert _ascii(render_content(resolved, 4, 4), 4, 4) == ["....", "RRBB", "RRBB", "...."]


def test_render_content_default_size_is_the_canvas():
    resolved = _resolve({"palette": {"r": "#f00"}, "pixels": ["r"]})
    assert _ascii(render_content(resolved, 2, 1), 2, 1) == ["R."]


def test_render_none_is_transparent():
    assert render_content(None, 2, 2) == bytes(16)


# --- Performance ----------------------------------------------------------------


def test_64x64_with_256_shapes_is_fast():
    shapes = []
    for i in range(255):
        kind = i % 6
        if kind == 0:
            shapes.append(
                {"type": "rect", "x": i % 50, "y": i % 40, "w": 30, "h": 20, "fill": "#f00", "stroke": "#fff"}
            )
        elif kind == 1:
            shapes.append({"type": "circle", "cx": 32, "cy": 32, "r": 30, "fill": "#0f0", "stroke": "#00f"})
        elif kind == 2:
            shapes.append({"type": "ellipse", "cx": 32, "cy": 32, "rx": 30, "ry": 18, "fill": "#00f"})
        elif kind == 3:
            shapes.append(
                {"type": "line", "x1": 0, "y1": i % 64, "x2": 63, "y2": 63 - i % 64, "stroke": "#fff", "width": 3}
            )
        elif kind == 4:
            shapes.append({"type": "polygon", "points": [[0, 0], [63, 10], [40, 63], [5, 50]], "fill": "#f00"})
        else:
            shapes.append({"type": "text", "x": 2, "y": i % 56, "text": "HELLO WORLD", "color": "#fff"})
    shapes.append({"type": "gradient", "from": "#000", "to": "#fff", "angle": 45})
    assert len(shapes) == 256
    resolved = _resolve({"shapes": shapes})
    start = time.perf_counter()
    rasterize(resolved, 64, 64)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"rasterising took {elapsed:.3f}s"


@pytest.mark.parametrize("size", [(1, 1), (128, 128)])
def test_extreme_sizes(size):
    resolved = _resolve({"shapes": [{"type": "circle", "cx": 0, "cy": 0, "r": 1000, "fill": "#fff"}]})
    assert len(rasterize(resolved, *size)) == size[0] * size[1] * 4
