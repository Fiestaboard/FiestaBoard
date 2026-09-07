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


def test_numeric_color_range_is_the_range_the_engine_accepts():
    """Pinned as literals, not recomputed from ``COLOR_CODES``.

    The old version asserted ``low == min(COLOR_CODES.values())``, which is
    the implementation restated: it agreed with any palette, including the
    one that dropped code 71 and taught models to avoid the ``filled`` flap
    (#1885). The range is a published fact about the hardware, so it is
    written out here; widening it is a deliberate edit to this line.
    """
    assert teaching.numeric_color_range() == (63, 71)
    assert "63–71" in teaching.template_syntax_block()


# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("device_type", "expected"),
    [
        ("flagship", "22 columns x 6 rows"),
        ("note", "15 columns x 3 rows"),
    ],
)
def test_dimensions_phrase_reads_as_the_prompt_expects(device_type, expected):
    """Pinned as literal sentences, not rebuilt from ``get_dimensions``.

    The old version formatted the expectation with the same f-string the
    implementation uses, so it could only ever catch a change to that one
    format string — never a wrong device table, a swapped rows/columns pair
    read from it, or a device silently resolving to the default.
    """
    assert teaching.dimensions_phrase(device_type) == expected


def test_dimensions_phrase_covers_every_device_the_platform_ships():
    """The literals above are a sample; this is the completeness half."""
    for device_type in DEVICE_DIMENSIONS:
        dims = get_dimensions(device_type)
        phrase = teaching.dimensions_phrase(device_type)
        assert str(dims.cols) in phrase and str(dims.rows) in phrase, phrase


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


def test_formula_roster_names_the_functions_the_engine_evaluates():
    """Pinned against the *evaluator*, not against ``function_signatures()``.

    ``names == sorted(function_signatures())`` was the implementation
    restated — it passed for any roster the same call produced, including an
    empty one. These names are the ones a model is told it may emit, so each
    is checked to be something the expression evaluator will actually run.
    """
    from src.templates.expressions import render_expressions

    names = teaching.formula_function_names()
    assert {"IF", "LEFT", "RIGHT", "UPPER", "ROUND"} <= set(names), names

    for name in ("IF", "LEFT", "UPPER"):
        assert name in function_signatures(), f"{name} is taught but not registered"

    # A taught function must evaluate rather than tag an error.
    assert render_expressions('{{= UPPER("ok")}}', {}) == "OK"
    assert render_expressions('{{= IF(1 > 0, "Y", "N")}}', {}) == "Y"


def test_formula_roster_stays_the_live_registry_rather_than_a_frozen_copy():
    """The regression #1764 fixed: a hardcoded 15-name list that rotted."""
    names = teaching.formula_function_names()
    assert len(names) > 15
    assert set(names) == set(function_signatures())
    block = teaching.template_syntax_block()
    for name in names:
        assert name in block
