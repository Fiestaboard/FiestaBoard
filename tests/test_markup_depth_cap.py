"""The span depth cap and the parser's linear-time guarantee (FiestaUI spec §4.1).

Spans nest at most :data:`src.markup.MAX_SPAN_DEPTH` (8) levels: an opener
that would open a ninth is literal text. The token-level parity cases (depth
7 + 1, 8 + 1, tiles and icons inside a literal opener, ...) are replayed from
FiestaUI's real parser in ``tests/test_markup_parity.py`` (the ``depth-*``
fixtures); this file pins what fixtures cannot: that a hostile run of braces
parses in linear time without exhausting Python's recursion limit, through
the parser and through the template engine, and the template normaliser's
own cap (``MAX_TEMPLATE_SPAN_DEPTH`` in :mod:`src.templates.engine`).

Timing budgets are loose (a loaded CI box), but an order of magnitude under
what the quadratic scan took; the unfixed code raised ``RecursionError``.
"""

from __future__ import annotations

import time

import pytest

from src.markup import MAX_SPAN_DEPTH, count_tiles, parse_line, split_rows, take_tiles, wrap_line
from src.templates import engine as template_engine
from src.templates.engine import TemplateEngine

DEEP = "{red:" * 10000 + "X" + "}" * 10000
DEEP_TEMPLATE = "{{red:" * 10000 + "X" + "}}" * 10000

# FiestaUI scripts/ci/tests/board-characters.test.mjs, "pathological brace runs".
PATHOLOGICAL = {
    "deep": DEEP,
    "openers": "{red:" * 100000,
    "bare-openers": "{" * 100000,
    "siblings": "{red:X}" * 50000,
    "closers": "{red:" * 100000 + "}",
    "icons": "{icon:" * 100000 + "}",
}


def _timed(fn, *args, **kwargs):
    started = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, time.perf_counter() - started


def nest(depth: int, inner: str) -> str:
    return "{red:" * depth + inner + "}" * depth


def template_nest(depth: int, inner: str) -> str:
    return "{{red:" * depth + inner + "}}" * depth


def test_the_caps_match_fiestaui():
    assert (MAX_SPAN_DEPTH, getattr(template_engine, "MAX_TEMPLATE_SPAN_DEPTH", None)) == (8, 8)


# --- the parser -----------------------------------------------------------------------------


@pytest.mark.parametrize("extended", [True, False], ids=["ext", "legacy"])
@pytest.mark.parametrize("name", list(PATHOLOGICAL))
def test_a_pathological_line_parses_in_linear_time_under_a_board_cap(name, extended):
    tokens, elapsed = _timed(parse_line, PATHOLOGICAL[name], 132, extended_markup=extended)
    assert len(tokens) <= 132
    assert elapsed < 1.0, f"{name} took {elapsed:.2f}s"


@pytest.mark.parametrize("extended", [True, False], ids=["ext", "legacy"])
@pytest.mark.parametrize("name", list(PATHOLOGICAL))
def test_a_pathological_line_parses_in_linear_time_uncapped(name, extended):
    line = PATHOLOGICAL[name]
    tokens, elapsed = _timed(parse_line, line, extended_markup=extended)
    assert len(tokens) <= len(line)
    # Up to half a million tokens are allocated here, which is the floor of
    # any parser; the quadratic scan took minutes, or overflowed the stack.
    assert elapsed < 10.0, f"{name} took {elapsed:.2f}s"


def test_the_spec_deep_run_parses_well_under_a_second_without_recursion_error():
    tokens, elapsed = _timed(parse_line, DEEP, extended_markup=True)
    assert elapsed < 1.0, f"took {elapsed:.2f}s"
    # Every opener past the eighth is literal, coloured by the eighth span,
    # and so are the closers up to the one that closes the depth-8 span.
    assert len(tokens) == len(DEEP) - 8 * len("{red:") - 8
    assert [t.to_dict() for t in tokens[:5]] == [{"type": "char", "value": v, "color": "red"} for v in "{RED:"]
    assert tokens[-1].to_dict() == {"type": "char", "value": "}", "color": "red"}


def test_a_ninth_level_opener_is_literal_text_in_the_eighth_span():
    tokens = parse_line(nest(8, "{blue:X}"), extended_markup=True)
    assert [(t.value, t.color) for t in tokens] == [(v, "red") for v in "{BLUE:X}"]
    assert [(t.value, t.color) for t in parse_line(nest(7, "{blue:X}"), extended_markup=True)] == [("X", "blue")]


@pytest.mark.parametrize(
    "fn",
    [count_tiles, lambda text: take_tiles(text, 22), lambda text: wrap_line(text, 22), split_rows],
    ids=["count_tiles", "take_tiles", "wrap_line", "split_rows"],
)
def test_measuring_and_splitting_a_deep_run_is_fast(fn):
    _, elapsed = _timed(fn, DEEP)
    assert elapsed < 2.0, f"took {elapsed:.2f}s"


# --- the template engine -------------------------------------------------------------------


@pytest.fixture
def engine():
    return TemplateEngine()


def test_a_deep_single_brace_run_renders_fast(engine):
    rendered, elapsed = _timed(engine.render, DEEP, {}, extended_markup=True)
    assert rendered == DEEP
    assert elapsed < 1.0, f"took {elapsed:.2f}s"


def test_a_deep_single_brace_run_renders_onto_a_board_fast(engine):
    _, elapsed = _timed(engine.render_lines, [DEEP], {}, extended_markup=True)
    assert elapsed < 2.0, f"took {elapsed:.2f}s"


def test_a_deep_template_span_run_renders_fast_without_recursion_error(engine):
    rendered, elapsed = _timed(engine.render, DEEP_TEMPLATE, {}, extended_markup=True)
    assert elapsed < 1.0, f"took {elapsed:.2f}s"
    # Eight levels normalise; the ninth-level token is kept whole as text.
    inner = "{{red:" * (10000 - 8) + "X" + "}}" * (10000 - 8)
    assert rendered == nest(8, inner)


def test_an_unbalanced_template_opener_run_renders_fast(engine):
    template = "{{red:" * 20000
    rendered, elapsed = _timed(engine.render, template, {}, extended_markup=True)
    assert rendered == template
    assert elapsed < 1.0, f"took {elapsed:.2f}s"


def test_validating_a_deep_template_is_fast(engine):
    _, elapsed = _timed(engine.validate_template, DEEP_TEMPLATE, extended_markup=True)
    assert elapsed < 2.0, f"took {elapsed:.2f}s"


def test_template_spans_normalise_eight_deep(engine):
    assert engine.render(template_nest(7, "{{blue:X}}"), {}, extended_markup=True) == nest(7, "{blue:X}")


def test_a_ninth_level_template_span_is_kept_whole_as_text(engine):
    rendered = engine.render(template_nest(8, "{{blue:X}}"), {}, extended_markup=True)
    assert rendered == nest(8, "{{blue:X}}")
    # The board parser then draws it as literal text in the eighth span.
    assert [(t.value, t.color) for t in parse_line(rendered, extended_markup=True)] == [
        (v, "red") for v in "{{BLUE:X}}"
    ]


def test_a_kept_ninth_level_token_is_not_read_as_a_variable_or_a_tile_name(engine):
    ctx = {"demo": {"temp": "72"}}
    rendered = engine.render(template_nest(8, "{{blue:{{demo.temp}} {{red}}}}"), ctx, extended_markup=True)
    assert rendered == nest(8, "{{blue:{{demo.temp}} {{red}}}}")


def test_the_parser_still_reads_tiles_inside_a_kept_ninth_level_token(engine):
    rendered = engine.render(template_nest(8, "{{blue:{63}}}"), {}, extended_markup=True)
    tokens = parse_line(rendered, extended_markup=True)
    assert [t.to_dict() for t in tokens] == [
        *({"type": "char", "value": v, "color": "red"} for v in "{{BLUE:"),
        {"type": "color", "code": "63"},
        *({"type": "char", "value": v, "color": "red"} for v in "}}"),
    ]


def test_template_spans_beside_the_cap_still_render_their_variables(engine):
    ctx = {"demo": {"temp": "72"}}
    rendered = engine.render(template_nest(8, "{{demo.temp}}"), ctx, extended_markup=True)
    assert rendered == nest(8, "72")


def test_a_long_word_hard_breaks_in_linear_time_on_a_split_flap_board():
    """The legacy wrap re-counted the rest of a too-wide word for every row."""
    from src.formatters.message_formatter import MessageFormatter

    word = "A{63}" * 40000
    rows, elapsed = _timed(MessageFormatter(cols=22)._wrap_line, word)
    assert "".join(rows) == word
    assert all(len(parse_line(row)) == 22 for row in rows[:-1])
    assert elapsed < 1.0, f"took {elapsed:.2f}s"
