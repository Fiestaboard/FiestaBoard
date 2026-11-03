"""Golden flexible layouts for the spec's devices (plan Task 11, spec section 8).

:data:`SAMPLE` is laid out for each golden device and compared with
``tests/golden/layout/<device>.json``. A golden holds the frame twice (as
ASCII art to review by eye, and as a SHA-256 of the RGB bytes so colour is
held exactly), a few RGB spot pixels on colour boards, the hidden cell lines
and every layout issue.

Regenerate with ``FIESTABOARD_UPDATE_LAYOUT_GOLDEN=1`` and review every
``frame_ascii`` by eye.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from src.layout.engine import FlexRender, layout_flexible_page
from src.layout.issues import LayoutIssue
from src.led.matrix import LedFrame
from src.pages.models import Page
from tests.layout.devices import GOLDEN_DEVICES, SAMPLE, SAMPLE_CTX, golden_target

GOLDEN = Path(__file__).resolve().parent.parent / "golden" / "layout"

#: ASCII for an unlit (black) pixel and for a lit one.
UNLIT, LIT = ".", "#"

#: How many RGB spot pixels a colour board's golden holds.
RGB_SPOTS = 3

_BLACK = b"\x00\x00\x00"


def _pixel(frame: LedFrame, x: int, y: int) -> bytes:
    i = (y * frame.width + x) * 3
    return frame.pixels[i : i + 3]


def _frame_ascii(frame: LedFrame) -> list[str]:
    return [
        "".join(UNLIT if _pixel(frame, x, y) == _BLACK else LIT for x in range(frame.width))
        for y in range(frame.height)
    ]


def _rgb_spots(frame: LedFrame) -> dict[str, str]:
    """Up to :data:`RGB_SPOTS` pixels that pin the frame's colours.

    In row-major order: the first lit pixel of each distinct colour, then the
    last lit pixel, then the top-left corner (the background), without
    repeats.
    """
    chosen: list[tuple[int, int]] = []
    colours: set[bytes] = set()
    last_lit: tuple[int, int] | None = None
    for y in range(frame.height):
        for x in range(frame.width):
            rgb = _pixel(frame, x, y)
            if rgb == _BLACK:
                continue
            last_lit = (x, y)
            if rgb not in colours:
                colours.add(rgb)
                chosen.append((x, y))
    for extra in (last_lit, (0, 0)):
        if extra is not None and extra not in chosen:
            chosen.append(extra)
    return {f"{x},{y}": "#" + _pixel(frame, x, y).hex() for x, y in chosen[:RGB_SPOTS]}


def snapshot(render: FlexRender, name: str) -> dict[str, Any]:
    """The golden form of ``render`` laid out for golden device ``name``.

    ``frame_ascii``, ``frame_sha256`` and ``rgb_spot`` are ``None`` on a cell
    board; ``rgb_spot`` is also ``None`` on a monochrome panel, whose colour
    is its one lit colour.
    """
    frame = render.frame
    monochrome = golden_target(name).monochrome is not None
    return {
        "device": name,
        "frame_ascii": _frame_ascii(frame) if frame is not None else None,
        "frame_sha256": hashlib.sha256(frame.pixels).hexdigest() if frame is not None else None,
        "rgb_spot": _rgb_spots(frame) if frame is not None and not monochrome else None,
        "cell_lines": list(render.cell_lines),
        "issues": [issue.to_json() for issue in render.issues],
    }


# --- the goldens ----------------------------------------------------------------


@pytest.mark.parametrize("name", GOLDEN_DEVICES)
def test_flexible_layout_matches_golden(name):
    got = snapshot(layout_flexible_page(Page.model_validate(SAMPLE), golden_target(name), SAMPLE_CTX), name)
    path = GOLDEN / f"{name}.json"
    if os.environ.get("FIESTABOARD_UPDATE_LAYOUT_GOLDEN") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(got, indent=2) + "\n")
    assert got == json.loads(path.read_text()), (
        "regenerate with FIESTABOARD_UPDATE_LAYOUT_GOLDEN=1 and review the ascii"
    )


# --- the snapshot form --------------------------------------------------------


def _frame(width: int, height: int, lit: dict[tuple[int, int], bytes]) -> LedFrame:
    pixels = bytearray(width * height * 3)
    for (x, y), rgb in lit.items():
        i = (y * width + x) * 3
        pixels[i : i + 3] = rgb
    return LedFrame(width, height, bytes(pixels))


def _render(frame: LedFrame | None, issues: tuple[LayoutIssue, ...] = ()) -> FlexRender:
    return FlexRender(frame=frame, cell_lines=("AB", "CD"), issues=issues, shown=())


WHITE, ORANGE = b"\xff\xff\xff", b"\xff\x88\x00"


def test_snapshot_of_a_cell_board_has_no_frame_fields():
    got = snapshot(_render(None), "flagship")
    assert (got["frame_ascii"], got["frame_sha256"], got["rgb_spot"]) == (None, None, None)


def test_snapshot_holds_device_cells_and_issues():
    issue = LayoutIssue(("blocks", "time", "style", "size"), "size_ignored", "info", "one size")
    got = snapshot(_render(None, (issue,)), "flagship")
    assert (got["device"], got["cell_lines"], got["issues"]) == ("flagship", ["AB", "CD"], [issue.to_json()])


def test_snapshot_frame_ascii_marks_lit_pixels():
    got = snapshot(_render(_frame(3, 2, {(1, 0): WHITE, (2, 1): ORANGE})), "pixoo64_3x5")
    assert got["frame_ascii"] == [".#.", "..#"]


def test_snapshot_frame_sha256_is_of_the_rgb_bytes():
    frame = _frame(3, 2, {(1, 0): WHITE})
    assert snapshot(_render(frame), "pixoo64_3x5")["frame_sha256"] == hashlib.sha256(frame.pixels).hexdigest()


def test_snapshot_rgb_spot_takes_first_pixel_of_each_colour():
    frame = _frame(4, 2, {(1, 0): WHITE, (2, 0): WHITE, (0, 1): ORANGE, (3, 1): b"\x00\x00\xff"})
    assert snapshot(_render(frame), "pixoo64_3x5")["rgb_spot"] == {
        "1,0": "#ffffff",
        "0,1": "#ff8800",
        "3,1": "#0000ff",
    }


def test_snapshot_rgb_spot_pads_with_last_lit_and_background():
    frame = _frame(4, 2, {(1, 0): WHITE, (2, 1): WHITE})
    assert snapshot(_render(frame), "pixoo64_3x5")["rgb_spot"] == {
        "1,0": "#ffffff",
        "2,1": "#ffffff",
        "0,0": "#000000",
    }


def test_snapshot_of_a_monochrome_panel_has_no_rgb_spot():
    got = snapshot(_render(_frame(2, 1, {(0, 0): b"\xff\x00\x00"})), "max7219_32x8")
    assert got["rgb_spot"] is None and got["frame_ascii"] == ["#."]
