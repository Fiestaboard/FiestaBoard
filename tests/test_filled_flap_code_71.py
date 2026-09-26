"""Flap code 71 (``filled``) must be one colour marker everywhere (#1885).

``src/templates/expressions.py`` has always known ``filled = 71`` and accepts
the numeric range 63-71: ``{{= COLOR("filled")}}`` and ``{{= COLOR(71)}}``
both render the marker ``{71}``. ``src/templates/engine.py`` disagreed with
itself about the same code — its tile-width counter accepted 63-71 while its
two word-wrap tokenizers and its plugin-value passthrough stopped at 70, and
``COLOR_CODES`` had no ``filled`` entry at all.

The visible consequence: a formula that produced a filled tile was counted as
one tile when measuring the line but treated as ordinary text when wrapping
it, so the wrap split in the wrong place. The generated teaching text
inherited the same off-by-one and taught models the range as 63-70, which is
the "minor correctness regression" recorded on #1885.

Four of the six tests below fail on the pre-fix engine; the two that do
not are marked, and say why they are still worth pinning.
"""

from __future__ import annotations

from src.ops import teaching
from src.templates.engine import COLOR_CODES, TemplateEngine


def _engine() -> TemplateEngine:
    """The wrap and colour helpers below need no engine state."""
    return TemplateEngine.__new__(TemplateEngine)


def test_filled_is_a_named_colour_token_like_every_other_flap():
    assert COLOR_CODES["filled"] == 71


def test_the_two_colour_maps_agree():
    """``expressions._COLOR_CODES`` documents itself as kept in sync with
    ``engine.COLOR_CODES``. It was not."""
    from src.templates.expressions import _COLOR_CODES

    assert _COLOR_CODES == COLOR_CODES


def test_word_wrap_treats_a_filled_marker_as_one_token():
    tokens = _engine()._split_into_tokens("{71} RISE")

    assert tokens[0] == "{71}", tokens


def test_word_wrap_tiles_counts_a_filled_marker_as_one_tile_not_four_chars():
    """``{71}HELLO`` is 6 tiles, so it fits an 8-tile line.

    This half was already correct before the fix — the tile counter used the
    63-71 range all along. It is pinned here because it is the behaviour the
    char-based tokenizer above now has to agree with: the bug was the two
    halves disagreeing, so a test that only covers the broken half would let
    a "fix" that moved the disagreement somewhere else pass.
    """
    assert _engine()._word_wrap_tiles("{71}HELLO WORLD", 8, 8, 2) == ["{71}HELLO", "WORLD"]


def test_a_plugin_value_that_is_a_filled_marker_passes_through_unchanged():
    r"""Also already correct pre-fix, via the generic ``^{\d+}`` passthrough
    that follows the colour-code check — the narrow 63-70 check there was
    dead-lettered rather than wrong. Pinned so the passthrough stays."""
    engine = _engine()
    engine.color_rules = {}

    rendered = engine._render_variables("{{p.tile}}", {"p": {"tile": "{71}"}})

    assert rendered == "{71}"


def test_the_taught_numeric_range_covers_the_filled_flap():
    """#1885: models were being taught 63-70 and so avoided a valid flap."""
    assert teaching.numeric_color_range() == (63, 71)


def test_the_fill_directive_is_untouched_by_the_new_named_token():
    """``{{filled}}`` is now a colour token; ``{{filled:X}}`` is still the
    fill-the-rest-of-the-line directive. The two must not collide."""
    from src.templates.engine import COLOR_PATTERN, FILLED_PATTERN

    assert COLOR_PATTERN.fullmatch("{{filled}}")
    assert COLOR_PATTERN.search("{{filled:*}}") is None
    assert FILLED_PATTERN.fullmatch("{{filled:*}}")
    assert FILLED_PATTERN.search("{{filled}}") is None
