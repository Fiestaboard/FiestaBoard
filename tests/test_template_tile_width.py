"""One width rule for a template line (bug bash BB-E-2).

The rich editor saves a colour tile as ``{{red}}`` (or ``{{63}}``). The
validator folded only the single-brace ``{red}`` to one tile, so ``{{red}}``
became the three characters ``{C}`` and a 22-tile art row reported
"66 of 22 columns · 44 cut off". The validator and the render report the
Inspector reads (H5) must agree with the board: a tile is one column.
"""

from unittest.mock import patch

import pytest

from src.templates.diagnostics import RenderReport
from src.templates.engine import TemplateEngine

TILES_22 = "{{red}}" * 11 + "{{orange}}" * 11

CASES = [
    # (line, cols, drawn tiles)
    (TILES_22, 22, 22),
    ("{{63}}" * 22, 22, 22),
    ("{{filled}}" * 4, 22, 4),
    ("A {{red}} B", 22, 5),
    ('PIZZA 12" {{red}} HOT', 15, 15),
    ("{{red}}{{orange}}", 22, 2),
    ("{red} TEXT {/red}", 22, 7),
    ("{63}{71}", 22, 2),
]


@pytest.fixture
def engine():
    engine = TemplateEngine()
    with (
        patch.object(TemplateEngine, "get_available_variables", return_value={}),
        patch.object(TemplateEngine, "get_all_known_sources", return_value=set()),
        patch.object(TemplateEngine, "_build_context", return_value={}),
    ):
        yield engine


def too_long(errors):
    return {e.line: e.max_length for e in errors if e.code == "line_too_long"}


@pytest.mark.parametrize(("line", "cols", "tiles"), CASES)
def test_a_colour_tile_is_one_column(engine, line, cols, tiles):
    assert engine._calculate_max_line_length(line, cols=cols) == tiles


@pytest.mark.parametrize(("line", "cols", "tiles"), [c for c in CASES if c[1] == 22])
def test_validate_measures_what_the_render_report_measures(engine, line, cols, tiles):
    report = RenderReport()
    engine.render_lines([line, "", "", "", "", ""], {}, report=report)
    assert report.lines[0].widest == tiles
    assert engine._calculate_max_line_length(line, cols=cols) == report.lines[0].widest


def test_a_22_tile_row_fits_a_22_column_board(engine):
    assert too_long(engine.validate_template(TILES_22, cols=22)) == {}


def test_one_tile_past_the_edge_is_one_column_cut(engine):
    assert too_long(engine.validate_template(TILES_22 + "{{red}}", cols=22)) == {1: 23}
