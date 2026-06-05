"""Tests for src/ai/template_validator.py."""

from __future__ import annotations

import pytest

from src.ai.template_validator import repair_template_lines

# ---------------------------------------------------------------------------
# The reported bug.
# ---------------------------------------------------------------------------


def test_strips_trailing_period_from_color_name():
    lines = ["Title{{filled:green.}}99"]
    repaired, warnings = repair_template_lines(lines)
    assert repaired == ["Title{{filled:green}}99"]
    assert len(warnings) == 1
    assert "green" in warnings[0]
    assert "Line 1" in warnings[0]


@pytest.mark.parametrize(
    "color",
    ["red", "orange", "yellow", "green", "blue", "violet", "purple", "white", "black"],
)
def test_strips_trailing_period_for_each_color(color):
    repaired, warnings = repair_template_lines([f"{{{{filled:{color}.}}}}"])
    assert repaired == [f"{{{{filled:{color}}}}}"]
    assert len(warnings) == 1


def test_strips_other_trailing_punctuation():
    cases = [
        ("{{filled:blue,}}", "{{filled:blue}}"),
        ("{{filled:red!}}", "{{filled:red}}"),
        ("{{filled:white?}}", "{{filled:white}}"),
        ("{{filled:green;}}", "{{filled:green}}"),
        ("{{filled:black:}}", "{{filled:black}}"),
        ("{{filled:yellow }}", "{{filled:yellow}}"),
    ]
    for raw, expected in cases:
        repaired, warnings = repair_template_lines([raw])
        assert repaired == [expected], f"failed for {raw!r}"
        assert len(warnings) == 1, f"no warning for {raw!r}"


def test_handles_case_insensitive_color_name():
    repaired, warnings = repair_template_lines(["{{filled:GREEN.}}"])
    # Keep the model's original casing — engine matches case-insensitively.
    assert repaired == ["{{filled:GREEN}}"]
    assert len(warnings) == 1


def test_applies_to_fill_space_repeat_alias():
    repaired, warnings = repair_template_lines(["{{fill_space_repeat:blue.}}"])
    assert repaired == ["{{fill_space_repeat:blue}}"]
    assert len(warnings) == 1


def test_repairs_multiple_occurrences_on_same_line():
    repaired, warnings = repair_template_lines(["{{filled:red.}}A{{filled:blue,}}"])
    assert repaired == ["{{filled:red}}A{{filled:blue}}"]
    assert len(warnings) == 2


# ---------------------------------------------------------------------------
# Wrong-separator forms.
# ---------------------------------------------------------------------------


def test_rewrites_period_separator():
    repaired, warnings = repair_template_lines(["{{filled.green}}"])
    assert repaired == ["{{filled:green}}"]
    assert len(warnings) == 1
    assert "colon" in warnings[0].lower()


def test_rewrites_space_separator():
    repaired, warnings = repair_template_lines(["{{filled blue}}"])
    assert repaired == ["{{filled:blue}}"]
    assert len(warnings) == 1


def test_rewrites_period_separator_with_dot_pattern():
    # ``{{filled..}}`` → ``{{filled:.}}`` (dot pattern is valid).
    repaired, warnings = repair_template_lines(["Title{{filled..}}99"])
    assert repaired == ["Title{{filled:.}}99"]
    assert len(warnings) == 1


def test_warns_on_empty_argument():
    repaired, warnings = repair_template_lines(["{{filled:}}"])
    assert repaired == ["{{filled:}}"]
    assert len(warnings) == 1
    assert "no argument" in warnings[0].lower()


# ---------------------------------------------------------------------------
# Pass-through: well-formed templates must be untouched.
# ---------------------------------------------------------------------------


def test_leaves_valid_color_fill_alone():
    lines = ["{{filled:green}}", "Title{{filled:.}}99", "{{filled:red}}"]
    repaired, warnings = repair_template_lines(lines)
    assert repaired == lines
    assert warnings == []


def test_leaves_valid_text_pattern_alone():
    # Multi-char text patterns like ``{{filled:-=}}`` are intentional.
    lines = ["{{filled:-=}}", "{{filled:-}}", "{{filled:*}}"]
    repaired, warnings = repair_template_lines(lines)
    assert repaired == lines
    assert warnings == []


def test_leaves_unrelated_template_syntax_alone():
    lines = [
        "{{weather.temperature}}",
        "{red} ALERT {red}",
        "{{= IF(x, 1, 2) }}",
        "{{fill_space}}",
        "",
    ]
    repaired, warnings = repair_template_lines(lines)
    assert repaired == lines
    assert warnings == []


def test_empty_input():
    assert repair_template_lines([]) == ([], [])


def test_warning_includes_line_number():
    lines = ["", "", "Bad{{filled:red.}}"]
    repaired, warnings = repair_template_lines(lines)
    assert repaired[2] == "Bad{{filled:red}}"
    assert "Line 3" in warnings[0]


# ---------------------------------------------------------------------------
# Non-color trailing-character text pattern stays as text pattern.
# This protects against over-eager rewriting: ``{{filled:abc}}`` is a
# legitimate (if odd) repeating-text pattern, not a typo.
# ---------------------------------------------------------------------------


def test_does_not_touch_non_color_text_pattern():
    lines = ["{{filled:abc.}}", "{{filled:xy}}"]
    repaired, warnings = repair_template_lines(lines)
    assert repaired == lines
    assert warnings == []
