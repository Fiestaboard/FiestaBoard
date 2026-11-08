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


@pytest.fixture(autouse=True)
def _frozen_deadline_clock(monkeypatch):
    """The step budgets are what most of these tests pin, and CI runs many
    times slower than a desktop: the deadline clock stands still unless a
    test drives it."""
    monkeypatch.setattr(expressions, "_eval_clock", lambda: 0.0)


def _failure(formula: str) -> expressions.FormulaError:
    """The error that ends *formula*, read from the evaluator itself (not via
    H5's ``evaluate_detailed``, so these tests also run on the 10.x lines)."""
    with pytest.raises(expressions.FormulaError) as caught:
        expressions._eval_node(expressions._Parser(expressions._tokenize(formula)).parse(), {})
    return caught.value


def _seconds_per_step() -> float:
    """This machine's cost of one evaluation step, measured on a reference
    formula: CI runs under coverage on another Python, many times slower
    than a desktop, so time bounds are stated in steps, not seconds."""
    reference = f'COUNT(FILTER({A}, item = "a"))'
    steps = expressions.count_steps(reference)
    best = min(_timed(reference)[1] for _ in range(3))
    return best / steps


def _within_budget_time(elapsed: float, steps: int) -> bool:
    """Whether *elapsed* is about what *steps* evaluation steps cost here:
    10x slack (parallel test workers make the measured step rate noisy), plus
    a fixed allowance for building the 32 K-item list. Unbounded, these
    formulas take minutes."""
    return elapsed < 10 * steps * _seconds_per_step() + 1.0


def _timed(formula: str) -> tuple[str, float]:
    started = time.perf_counter()
    value = evaluate(formula)
    return value, time.perf_counter() - started


# ── the attack ──────────────────────────────────────────────────────────────


def test_nested_filter_over_32k_items_stops_fast():
    value, elapsed = _timed(f"COUNT(FILTER({A}, COUNT(FILTER({A}, TRUE)) > 0))")

    assert value == "#VALUE"
    assert _within_budget_time(elapsed, expressions.MAX_FORMULA_STEPS)  # ~0.2 s on a desktop


def test_nested_foreach_stops_fast():
    value, elapsed = _timed(f'FOREACH({A}, COUNT(FILTER({A}, item = "a")))')

    assert value == "#VALUE"
    assert _within_budget_time(elapsed, expressions.MAX_FORMULA_STEPS)


def test_an_over_budget_formula_says_why():
    failure = _failure(f"COUNT(FILTER({A}, COUNT(FILTER({A}, TRUE)) > 0))")

    assert failure.code == "#VALUE"
    assert "too much work" in failure.message


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
    # Bounded by the render budget, where unbounded it is 25 M steps (each
    # line also builds its own 32 K-item list: 96 times the fixed allowance).
    assert elapsed < 3 * expressions.MAX_RENDER_STEPS * _seconds_per_step() + 96 * 0.5


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
    assert elapsed < 5


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
    failure = _failure('COUNT(FILTER(SPLIT(REPT("ab ",1000)), REGEXMATCH(item, "^a")))')

    assert failure.code == "#VALUE"
    assert "too much work" in failure.message


def test_the_parenthesis_limit_is_what_stops_it():
    with pytest.raises(expressions.FormulaError) as caught:
        expressions._Parser(expressions._tokenize("(" * 5000 + "1" + ")" * 5000)).parse()

    assert caught.value.code == "#SYNTAX"
    assert f"{expressions.MAX_PAREN_DEPTH} parentheses" in caught.value.message


def test_a_long_chain_past_the_depth_limit_is_syntax_before_python_would_fail():
    chain = "1" + "+1" * (expressions.MAX_EVAL_DEPTH + 100)

    assert evaluate(chain).startswith("#SYNTAX")
    assert evaluate("1" + "+1" * 100) == "101"


def test_iferror_cannot_trap_too_much_work():
    attack = f"COUNT(FILTER({A}, COUNT(FILTER({A}, TRUE)) > 0))"

    assert evaluate(f'IFERROR({attack}, "fine")') == "#VALUE"


# ── W1: one step must not hide 64 KB of work (#2461 security review) ────────

B64K = 'REPT(REPT("abcdefgh,",1024),7)'  # 57 344 characters, 7 169 pieces


@pytest.mark.parametrize(
    "formula",
    [
        f'COUNT(FILTER({A}, COUNT(SPLIT({B64K}, ",")) > 0))',
        f'COUNT(FILTER({A}, COUNT(SORT(SPLIT({B64K}, ","))) > 0))',
        f"COUNT(FILTER({A}, LEN(UPPER({B64K})) > 0))",
        f'COUNT(FILTER({A}, NOT CONTAINS({B64K}, "z")))',
        f'COUNT(FILTER({A}, LEN(JOIN(SPLIT({B64K}, ","), ";")) > 0))',
    ],
    ids=["split", "sort-split", "upper", "contains", "join"],
)
def test_per_item_work_on_a_large_string_is_charged_by_its_size(formula):
    value, elapsed = _timed(formula)

    assert value == "#VALUE"
    assert _within_budget_time(elapsed, expressions.MAX_FORMULA_STEPS)


def test_a_large_plugin_string_is_charged_the_same():
    big = ("abcdefgh," * 7000)[:-1]
    engine = TemplateEngine.__new__(TemplateEngine)
    engine._plugin_registry = None
    line = f'{{{{= COUNT(FILTER({A}, COUNT(SORT(SPLIT(p.s, ","))) > 0)) }}}}'

    started = time.perf_counter()
    rows = engine.render_lines([line], {"p": {"s": big}}).split("\n")

    assert rows[0].strip() == "#VALUE"
    assert _within_budget_time(time.perf_counter() - started, expressions.MAX_FORMULA_STEPS)


def test_work_is_charged_by_size_not_only_by_node():
    """One SPLIT of 57 KB costs more than one step; one of 9 bytes costs one."""
    assert expressions.count_steps(f'SPLIT({B64K}, ",")') > expressions.count_steps('SPLIT("a,b,c,d,e", ",")') + 100


# ── W2: a wall-clock deadline, for slow hardware ────────────────────────────


class _FakeClock:
    def __init__(self, step: float):
        self.now = 0.0
        self.step = step

    def __call__(self) -> float:
        self.now += self.step
        return self.now


def test_a_formula_past_one_second_took_too_long(monkeypatch):
    monkeypatch.setattr(expressions, "_eval_clock", _FakeClock(0.3))

    failure = _failure(f"COUNT(FILTER({A}, TRUE))")

    assert failure.code == "#VALUE"
    assert "took too long" in failure.message


def test_iferror_cannot_trap_the_deadline(monkeypatch):
    monkeypatch.setattr(expressions, "_eval_clock", _FakeClock(0.3))

    assert evaluate(f'IFERROR(COUNT(FILTER({A}, TRUE)), "fine")') == "#VALUE"


def test_a_render_past_three_seconds_stops_its_remaining_formulas(monkeypatch):
    """Each formula alone stays under a second; together they pass three."""
    monkeypatch.setattr(expressions, "_eval_clock", _FakeClock(0.1))
    engine = TemplateEngine.__new__(TemplateEngine)
    engine._plugin_registry = None
    line = '{{= COUNT(FILTER(SPLIT(REPT(REPT("a,",1000),2), ","), TRUE)) }}'

    rows = engine.render_lines([line] * 12, {}, device_type="panel", grid_rows=12, grid_cols=40).split("\n")

    assert rows[0].strip() == "2001"
    assert rows[-1].strip() == "#VALUE"


def test_ordinary_formulas_never_see_the_deadline(monkeypatch):
    monkeypatch.setattr(expressions, "_eval_clock", time.monotonic)

    assert evaluate(f"COUNT(FILTER({A}, TRUE))") == "32769"
