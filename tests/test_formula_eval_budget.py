"""No formula, and no render, may make the hub do unbounded work (S2).

S1 capped text at 64 KB, but CPU needs no large strings: ``FILTER`` and
``FOREACH`` evaluate an expression per item, ``SPLIT`` turns 64 KB into
32 K items, and nesting multiplies. ``COUNT(FILTER(A, COUNT(FILTER(A,
TRUE)) > 0))`` over 32 K items ran past 60 s from ~150 bytes. Pinned here:

- an **evaluation-step budget** per formula and per render (every node the
  evaluator visits counts), past which a formula is ``#VALUE``;
- a **regex-time budget** per formula and per render, on top of the 0.1 s
  per-call timeout (which bounds one call, not 64 K of them);
- deep nesting is ``#SYNTAX`` for that formula, not a ``RecursionError``
  that fails the whole render;
- the budgets sit far above the heaviest legitimate board (pinned too);
- ``REPLACE`` with an empty search string is bounded before it builds.
"""

from __future__ import annotations

import time
import tracemalloc

import pytest

from src.templates import expressions
from src.templates.engine import TemplateEngine
from src.templates.expressions import evaluate

A = 'SPLIT(REPT(REPT("a,",1024),32), ",")'  # 32 769 items from 64 KB
A_1K = 'REPT("A",1024)'
A_64K = f"REPT({A_1K},64)"


def _timed(formula: str) -> tuple[str, float]:
    started = time.perf_counter()
    value = evaluate(formula)
    return value, time.perf_counter() - started


# ── the attack ──────────────────────────────────────────────────────────────


def test_nested_filter_over_32k_items_stops_fast():
    value, elapsed = _timed(f"COUNT(FILTER({A}, COUNT(FILTER({A}, TRUE)) > 0))")

    assert value == "#VALUE"
    assert elapsed < 1


def test_nested_foreach_stops_fast():
    value, elapsed = _timed(f'FOREACH({A}, COUNT(FILTER({A}, item = "a")))')

    assert value == "#VALUE"
    assert elapsed < 1


def test_an_over_budget_formula_says_why():
    outcome = expressions.evaluate_detailed(f"COUNT(FILTER({A}, COUNT(FILTER({A}, TRUE)) > 0))")

    assert outcome.error == "#VALUE"
    assert "too much work" in (outcome.message or "")


# ── the budgets sit far above a real board ──────────────────────────────────

ITEMS = [{"name": f"STOP {n}", "eta": n % 60, "route": "J" if n % 2 else "N"} for n in range(1000)]
HEAVY = (
    '{{= FOREACH(SLICE(SORT(FILTER(transit.items, item.eta < 30 AND item.route = "J"), "eta"), 0, 3), '
    'PAD(UPPER(item.name), 12) & PADLEFT(TEXT(item.eta), 4) & "M") }}'
)


def test_the_heaviest_real_board_renders_unaffected():
    """A 96 x 128 panel, every line a FILTER + SORT + FOREACH over 1 000 items."""
    engine = TemplateEngine.__new__(TemplateEngine)
    engine._plugin_registry = None
    lines = [HEAVY] * 96

    rows = engine.render_lines(lines, {"transit": {"items": ITEMS}}, device_type="panel", grid_rows=96, grid_cols=128)

    assert "#VALUE" not in rows
    assert rows.split("\n")[0].startswith("STOP 1")


def test_the_budgets_leave_ten_times_the_heaviest_real_formula():
    steps = expressions.count_steps(HEAVY[4:-3], {"transit": {"items": ITEMS}})

    assert steps * 10 <= expressions.MAX_FORMULA_STEPS
    assert steps * 96 * 10 <= expressions.MAX_RENDER_STEPS


# ── the render budget ───────────────────────────────────────────────────────


def test_a_render_cannot_add_up_many_formulas_just_under_the_limit():
    """Each line alone fits the per-formula budget; together they exceed the render's."""
    engine = TemplateEngine.__new__(TemplateEngine)
    engine._plugin_registry = None
    line = f'{{{{= COUNT(FILTER({A}, LEN(item) = 1 AND item = "a")) }}}}'

    started = time.perf_counter()
    rows = engine.render_lines([line] * 96, {}, device_type="panel", grid_rows=96, grid_cols=128).split("\n")
    elapsed = time.perf_counter() - started

    assert rows[0].strip() == "32768"
    assert rows[-1].strip() == "#VALUE"
    assert elapsed < 20  # bounded: about 4 s here, where unbounded it is 25 M steps


# ── the regex budget ────────────────────────────────────────────────────────


def test_regex_time_is_budgeted_in_total_not_only_per_call(monkeypatch):
    """Every regex call is made to look 50 ms long: 1 000 of them would be 50 s."""
    clock = [0.0]

    def slow_clock() -> float:
        clock[0] += 0.025
        return clock[0]

    monkeypatch.setattr(expressions, "_regex_clock", slow_clock)
    words = 'SPLIT(REPT("ab ",1000))'

    value, elapsed = _timed(f'COUNT(FILTER({words}, REGEXMATCH(item, "^a")))')

    assert value == "#VALUE"
    assert elapsed < 1


def test_ordinary_regex_use_is_unaffected():
    assert evaluate('COUNT(FILTER(SPLIT(REPT("ab ",1000)), REGEXMATCH(item, "^a")))') == "1000"


# ── nesting ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "formula",
    ["(" * 5000 + "1" + ")" * 5000, "1" + "+1" * 20000, "-" * 20000 + "1", "NOT " * 5000 + "TRUE"],
    ids=["parentheses", "long-chain", "unary-minus", "not-chain"],
)
def test_deep_nesting_is_syntax_for_that_formula(formula):
    assert evaluate(formula).startswith("#SYNTAX")


def test_deep_nesting_fails_only_its_own_line():
    engine = TemplateEngine.__new__(TemplateEngine)
    engine._plugin_registry = None
    deep = "{{= " + "(" * 5000 + "1" + ")" * 5000 + " }}"

    rows = engine.render_lines(["OK", deep], {}).split("\n")

    assert rows[0].strip() == "OK"
    assert rows[1].strip().startswith("#SYNTAX")


def test_ordinary_nesting_still_works():
    assert evaluate("(" * 40 + "1" + ")" * 40) == "1"
    assert evaluate("IF(TRUE, " * 30 + "7" + ")" * 30) == "7"


# ── REPLACE with an empty search string (S1 review: surviving mutant) ───────


def test_replace_with_an_empty_search_checks_before_it_builds():
    tracemalloc.start()
    try:
        assert evaluate(f'LET(x, {A_64K}, REPLACE({A_1K}, "", x))') == "#VALUE"
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 8 * 1024 * 1024


# ── each limit answers for itself (not only through a fallback) ─────────────


def test_the_regex_budget_is_what_stops_it(monkeypatch):
    clock = [0.0]

    def slow_clock() -> float:
        clock[0] += 0.025
        return clock[0]

    monkeypatch.setattr(expressions, "_regex_clock", slow_clock)
    outcome = expressions.evaluate_detailed('COUNT(FILTER(SPLIT(REPT("ab ",1000)), REGEXMATCH(item, "^a")))')

    assert outcome.error == "#VALUE"
    assert "too much work" in (outcome.message or "")


def test_the_parenthesis_limit_is_what_stops_it():
    outcome = expressions.evaluate_detailed("(" * 5000 + "1" + ")" * 5000)

    assert outcome.error == "#SYNTAX"
    assert f"{expressions.MAX_PAREN_DEPTH} parentheses" in (outcome.message or "")


def test_a_long_chain_past_the_depth_limit_is_syntax_before_python_would_fail():
    chain = "1" + "+1" * (expressions.MAX_EVAL_DEPTH + 100)

    assert evaluate(chain).startswith("#SYNTAX")
    assert evaluate("1" + "+1" * 100) == "101"


def test_iferror_cannot_trap_too_much_work():
    attack = f"COUNT(FILTER({A}, COUNT(FILTER({A}, TRUE)) > 0))"

    assert evaluate(f'IFERROR({attack}, "fine")') == "#VALUE"
