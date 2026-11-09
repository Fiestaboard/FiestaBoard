"""No formula may build a string longer than ``MAX_STRING_LENGTH``.

``REPT`` capped its count (1024) but not its string, so nesting multiplied:
``{{= REPT(REPT(REPT("A",1024),1024),1024) }}`` (about 60 bytes) made
``POST /templates/render`` spend about 78 s building a 1 GiB string, and a
Raspberry Pi hub would be killed for memory. Any signed-in session or a
phone's ``control`` scope can send it.

The bound is on the result, at one choke point (every node the evaluator
returns), plus a check *before* building in each function that can grow a
string by a large factor in one step (``REPT``, ``CONCAT``, ``JOIN``,
``FOREACH``, ``REPLACE``, ``REGEXREPLACE``, the pad family, ``FIXED``) and in
the ``|pad:N`` / ``|zeropad:N`` filters. Past the bound a formula is
``#VALUE``, like any other value it cannot produce. 64 KB is far beyond any
board (the largest grid is 128 x 128 tiles).
"""

from __future__ import annotations

import time
import tracemalloc

import pytest
from fastapi.testclient import TestClient

from src.templates import expressions
from src.templates.engine import TemplateEngine
from src.templates.expressions import evaluate

#: Read without failing the import, so a missing cap fails each test on its behaviour.
MAX_STRING_LENGTH = getattr(expressions, "MAX_STRING_LENGTH", 65_536)

A_1K = 'REPT("A",1024)'
A_64K = f"REPT({A_1K},64)"


def test_the_limit_is_far_above_any_board():
    assert expressions.MAX_STRING_LENGTH == 65_536
    assert MAX_STRING_LENGTH > 128 * 128


# ── REPT ────────────────────────────────────────────────────────────────────


def test_rept_up_to_the_limit_still_works():
    assert evaluate(f"LEN({A_64K})") == "65536"


def test_rept_past_the_limit_is_value():
    assert evaluate(f"REPT({A_1K},65)") == "#VALUE"


def test_nested_rept_is_value_not_a_megabyte():
    assert evaluate(f"REPT({A_1K},1024)") == "#VALUE"


def test_triple_nested_rept_is_value():
    assert evaluate(f"REPT(REPT({A_1K},1024),16)") == "#VALUE"


# ── concatenation and the other builders ────────────────────────────────────


def test_a_concatenation_chain_past_the_limit_is_value():
    assert evaluate(f"LEN(REPT({A_1K},63) & {A_1K})") == "65536"
    assert evaluate(f'REPT({A_1K},63) & {A_1K} & "B"') == "#VALUE"


def test_a_long_concat_is_value():
    assert evaluate("CONCAT(" + ", ".join([A_1K] * 65) + ")") == "#VALUE"


def test_join_past_the_limit_is_value():
    assert evaluate(f'JOIN(SPLIT(REPT("a,",1000), ","), {A_1K})') == "#VALUE"


def test_foreach_past_the_limit_is_value():
    assert evaluate(f'FOREACH(SPLIT(REPT("a,",1000), ","), {A_1K})') == "#VALUE"


@pytest.mark.parametrize("name", ["PAD", "PADLEFT", "CENTER", "ZEROPAD"])
def test_a_huge_pad_width_is_value(name):
    started = time.perf_counter()
    assert evaluate(f'{name}("A", 100000000)') == "#VALUE"
    assert time.perf_counter() - started < 5  # loose: parallel workers; the value or length is the real check


def test_replace_that_would_grow_past_the_limit_is_value():
    assert evaluate(f'REPLACE({A_1K}, "A", {A_1K})') == "#VALUE"
    assert evaluate(f'REPLACE("AB", "", {A_64K})') == "#VALUE"
    assert evaluate('REPLACE("A-B", "-", "+")') == "A+B"


def test_regexreplace_that_would_grow_past_the_limit_is_value():
    assert evaluate(f'REGEXREPLACE({A_1K}, "A", REPT("B",100))') == "#VALUE"
    assert evaluate('REGEXREPLACE("a1b2", "[0-9]", "#")') == "a#b#"


def test_fixed_with_a_huge_precision_is_value():
    started = time.perf_counter()
    assert evaluate("FIXED(1, 100000000)") == "#VALUE"
    assert time.perf_counter() - started < 5  # loose: parallel workers; the value or length is the real check
    assert evaluate("FIXED(3.14159, 2)") == "3.14"


def test_iferror_cannot_hide_the_work():
    """A capped result is an error like any other, and its cost is already bounded."""
    started = time.perf_counter()
    assert evaluate(f'IFERROR(REPT(REPT({A_1K},1024),64), "x")') in {"x", "#VALUE"}
    assert time.perf_counter() - started < 5  # loose: parallel workers


# ── filters ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("flt", ["pad", "zeropad"])
def test_a_huge_filter_width_is_bounded(flt):
    started = time.perf_counter()
    out = TemplateEngine().render(f"{{{{d.x|{flt}:100000000}}}}", {"d": {"x": "7"}})
    assert len(out) <= MAX_STRING_LENGTH
    assert time.perf_counter() - started < 5  # loose: parallel workers; the value or length is the real check


# ── the bound in time and memory, end to end ────────────────────────────────

ATTACK = f"{{{{= REPT(REPT({A_1K},1024),1024) }}}}"


def test_the_attack_evaluates_in_bounded_time_and_memory():
    tracemalloc.start()
    started = time.perf_counter()
    try:
        assert evaluate(ATTACK[4:-3]) == "#VALUE"
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert elapsed < 1
    assert peak < 16 * 1024 * 1024


def test_render_answers_the_attack_quickly_and_small(_isolated_data_dir):
    from src.api_server import app

    client = TestClient(app)
    started = time.perf_counter()
    response = client.post("/templates/render", json={"template": [ATTACK]})
    elapsed = time.perf_counter() - started

    assert response.status_code == 200, response.text
    assert elapsed < 3
    assert len(response.content) < 4096
    assert response.json()["lines"][0].strip() == "#VALUE"


# ── each builder checks before it builds, not one step after ────────────────
#
# The choke point alone would stop each of these, but only after building a
# string many times the limit. Each function's own check keeps the work near
# the limit: the peak allocation stays a few megabytes.

X64 = f"LET(x, {A_64K}, {{}})"
ITEMS = 'SPLIT(REPT(REPT("a,",1000),30), ",")'


@pytest.mark.parametrize(
    "formula",
    [
        f"REPT({A_64K}, 1024)",
        X64.format("CONCAT(" + ", ".join(["x"] * 200) + ")"),
        f'REPLACE({A_64K}, "A", {A_1K})',
        f'REGEXREPLACE({A_64K}, "A", REPT("B",1000))',
        f"JOIN({ITEMS}, {A_1K})",
        f'FOREACH({ITEMS}, item & REPT("x",1000))',
        "FIXED(1, 100000000)",
        'PAD("A", 100000000)',
    ],
    ids=["rept", "concat", "replace", "regexreplace", "join", "foreach", "fixed", "pad"],
)
def test_a_builder_stops_before_it_builds_past_the_limit(formula):
    tracemalloc.start()
    try:
        assert evaluate(formula) == "#VALUE"
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 8 * 1024 * 1024
