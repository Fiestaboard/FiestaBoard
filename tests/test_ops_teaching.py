"""The generated teaching text must describe what the platform actually does.

Issue #1764: the MCP server's hardcoded teaching copy had rotted — it
advertised ``|upper``/``|lower`` template filters that never existed and a
15-function formula roster frozen in time. The fix is generation
(:mod:`src.ops.teaching` derives every fact from the defining module), and
these tests are the lock: each claim the teaching text makes is checked
against the engine that has to honor it.
"""

from __future__ import annotations

import pytest

from src.devices import DEVICE_DIMENSIONS, get_dimensions
from src.ops import teaching
from src.templates.engine import COLOR_CODES, TemplateEngine
from src.templates.expressions import function_signatures

# ---------------------------------------------------------------------------
# Filters: every filter the teaching text advertises must actually transform
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spelling", "value", "expected"),
    [
        ("pad:5", "7", "7    "),
        ("truncate:2", "SUNNY", "SU"),
        ("zeropad:3", "7", "007"),
    ],
)
def test_advertised_value_filters_are_implemented_by_the_engine(spelling, value, expected):
    engine = TemplateEngine.__new__(TemplateEngine)  # filter logic needs no engine state
    assert engine._apply_filter(value, spelling) == expected


def test_advertised_wrap_filter_is_recognized_by_the_engine():
    found = TemplateEngine._find_wrap_expression("{{weather.summary|wrap}}")
    assert found is not None, "the teaching text advertises |wrap but the engine no longer detects it"


def test_the_filters_the_old_mcp_copy_invented_still_do_not_exist():
    """``|upper`` and ``|lower`` were taught by the stale MCP text but were
    never implemented — a value passes through them unchanged. If the engine
    ever grows them, TEMPLATE_FILTERS (and this test) must be updated."""
    engine = TemplateEngine.__new__(TemplateEngine)
    assert engine._apply_filter("sunny", "upper:1") == "sunny"
    advertised = {spelling.split(":")[0] for spelling, _ in teaching.TEMPLATE_FILTERS}
    assert "upper" not in advertised
    assert "lower" not in advertised


def test_every_advertised_filter_appears_in_the_syntax_block():
    block = teaching.template_syntax_block()
    for spelling, summary in teaching.TEMPLATE_FILTERS:
        assert f"|{spelling}" in block
        assert summary in block


# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------


def test_every_named_color_token_is_taught():
    phrase = teaching.color_tokens_phrase()
    for name in COLOR_CODES:
        assert "{{" + name + "}}" in phrase


def test_numeric_color_range_matches_the_engine_palette():
    low, high = teaching.numeric_color_range()
    assert low == min(COLOR_CODES.values())
    assert high == max(COLOR_CODES.values())
    assert f"{low}–{high}" in teaching.template_syntax_block()


# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("device_type", sorted(DEVICE_DIMENSIONS))
def test_dimensions_phrase_matches_device_metadata(device_type):
    dims = get_dimensions(device_type)
    assert teaching.dimensions_phrase(device_type) == f"{dims.cols} columns x {dims.rows} rows"


def test_device_dimensions_block_lists_every_device():
    block = teaching.device_dimensions_block()
    for device, dims in DEVICE_DIMENSIONS.items():
        assert device in block
        assert f"{dims.cols} columns × {dims.rows} rows" in block


def test_dimensions_summary_sentence_covers_every_device():
    sentence = teaching.dimensions_summary_sentence()
    for device, dims in DEVICE_DIMENSIONS.items():
        assert f"{dims.cols}×{dims.rows}" in sentence
        assert device.capitalize() in sentence


# ---------------------------------------------------------------------------
# Formula functions
# ---------------------------------------------------------------------------


def test_formula_roster_is_the_live_registry_not_a_frozen_list():
    names = teaching.formula_function_names()
    assert names == sorted(function_signatures())
    # The stale hardcoded list had 15 entries; the live registry is larger,
    # which is exactly why a frozen copy rots.
    assert len(names) > 15
    block = teaching.template_syntax_block()
    for name in names:
        assert name in block
