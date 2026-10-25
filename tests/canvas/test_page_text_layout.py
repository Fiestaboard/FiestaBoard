"""Text around canvases (design §3 step 1): ``flow`` spans and ``hide`` blanking, on every board."""

from __future__ import annotations

import pytest

from src.markup import parse_line
from src.pages.models import LineMetadata, Page
from src.pages.service import PageService
from src.pages.storage import PageStorage

PIXELS = {"size": [1, 1], "palette": {"r": "#f00"}, "pixels": ["r"]}
PANGRAM = "THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG"


@pytest.fixture
def service(tmp_path):
    return PageService(storage=PageStorage(storage_file=str(tmp_path / "pages.json")))


def _canvas(row, col, rows, cols, text="flow", cid="c"):
    return {"id": cid, "area": {"row": row, "col": col, "rows": rows, "cols": cols}, "text": text, "content": PIXELS}


def _render(service, template, canvases, meta=None, **kw) -> list[str]:
    page = Page(
        name="P",
        type="template",
        template=template,
        line_metadata=[LineMetadata(**m) for m in meta] if meta else None,
        canvases=canvases,
        **kw,
    )
    result = service.render_page(page, context={})
    assert result.available, result.error
    return result.formatted.split("\n")


def _wrap(n=6, first=None):
    meta = [{"alignment": "left", "wrap": False} for _ in range(n)]
    meta[0] = first or {"alignment": "left", "wrap": True}
    return meta


def test_wrapped_text_flows_left_of_a_canvas_on_the_right(service):
    rows = _render(service, [PANGRAM], [_canvas(1, 15, 3, 8)], _wrap())
    assert rows[0] == "THE QUICK".ljust(14) + " " * 8
    assert rows[1] == "BROWN FOX".ljust(14) + " " * 8
    assert rows[2] == "JUMPS OVER THE" + " " * 8
    assert rows[3] == "LAZY DOG".ljust(22)
    assert all(len(r) == 22 for r in rows)


def test_text_flows_right_of_a_canvas_on_the_left_and_aligns_within_the_span(service):
    rows = _render(service, ["HELLO WORLD"], [_canvas(1, 1, 2, 6)], [{"alignment": "center", "wrap": False}])
    assert rows[0] == " " * 6 + "  HELLO WORLD   "


def test_right_alignment_is_within_the_span(service):
    rows = _render(service, ["HI"], [_canvas(1, 1, 1, 6)], [{"alignment": "right", "wrap": False}])
    assert rows[0] == " " * 20 + "HI"
    rows = _render(service, ["HI"], [_canvas(1, 17, 1, 6)], [{"alignment": "right", "wrap": False}])
    assert rows[0] == " " * 14 + "HI" + " " * 6


def test_wrapped_text_fills_the_left_span_then_the_right_span_then_the_next_row(service):
    rows = _render(service, ["ONE TWO THREE FOUR FIVE"], [_canvas(1, 9, 2, 6)], _wrap())
    assert rows[0] == "ONE TWO ".ljust(8) + " " * 6 + "THREE".ljust(8)
    assert rows[1] == "FOUR".ljust(8) + " " * 6 + "FIVE".ljust(8)


def test_words_are_never_split_a_word_too_wide_for_a_span_moves_on(service):
    # The left span is 3 wide: "ALPHABET" cannot fit it and goes to the 13-wide right span.
    rows = _render(service, ["ALPHABET SOUP TODAY"], [_canvas(1, 4, 1, 6)], _wrap())
    assert rows[0] == " " * 3 + " " * 6 + "ALPHABET SOUP"
    assert rows[1] == "TODAY".ljust(22)


def test_a_line_without_wrap_clips_at_the_span_end(service):
    rows = _render(service, ["ABCDEFGHIJKLMNOP"], [_canvas(1, 9, 1, 6)], [{"alignment": "left", "wrap": False}])
    assert rows[0] == "ABCDEFGH" + " " * 14


def test_several_canvases_shape_each_row(service):
    canvases = [_canvas(1, 1, 1, 4, cid="a"), _canvas(2, 19, 1, 4, cid="b")]
    rows = _render(service, [PANGRAM], canvases, _wrap())
    assert rows[0] == " " * 4 + "THE QUICK BROWN".ljust(18)
    assert rows[1] == "FOX JUMPS OVER THE" + " " * 4
    assert rows[2] == "LAZY DOG".ljust(22)


def test_rows_without_canvases_render_as_before(service):
    template = ["FIRST", "SECOND"]
    plain = _render(service, template, None)
    with_canvas = _render(service, template, [_canvas(6, 1, 1, 22)])
    assert with_canvas[:5] == plain[:5]
    assert with_canvas[5] == " " * 22


# --- hide ----------------------------------------------------------------------


def test_hide_renders_text_as_usual_then_blanks_the_covered_cells_on_split_flap(service):
    rows = _render(service, ["HELLO WORLD", "{63}{63}{63}{63}"], [_canvas(1, 1, 2, 5, text="hide")])
    assert rows[0] == " " * 5 + " WORLD" + " " * 11
    assert rows[1] == " " * 22  # the four tiles were under the canvas


def test_hide_blanks_cells_of_colour_spans_on_an_extended_markup_board(service):
    page = Page(
        name="P",
        type="template",
        template=["{{red:HELLO}} WORLD"],
        canvases=[_canvas(1, 1, 1, 2, text="hide")],
    )
    formatted = service.render_page(page, context={}, extended_markup=True).formatted
    tokens = parse_line(formatted.split("\n")[0], extended_markup=True)
    assert [t.value for t in tokens[:5]] == [" ", " ", "L", "L", "O"]
    assert tokens[0].color is None and tokens[2].color == "red"


def test_hide_blanks_a_narrow_strip_mid_row(service):
    page = Page(name="P", type="template", template=["XXXXXXXXXX"], canvases=[_canvas(1, 3, 1, 2, text="hide")])
    assert service.render_page(page, context={}).formatted.split("\n")[0][:6] == "XX  XX"
