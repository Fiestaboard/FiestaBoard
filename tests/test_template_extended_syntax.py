"""Template authoring forms for extended markup, and data-vs-markup (plan D19).

FiestaUI's TemplateEditor writes spans, blocks and icons in the template's
double-brace style: ``{{red:HOT}}``, ``{{black/white:OPEN}}``,
``{{icon:sun}}``. With ``extended_markup`` on, the engine normalises them to
the single-brace markup the parser reads. The head grammar is closed, so
everything else (``{{weather:sf.temperature}}``, ``{{filled:-}}``) stays a
variable. Off (the default), these forms are untouched.

Substituted variable values are data in every mode: only base-grammar tiles
and end tags survive; every other brace becomes a parenthesis.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.markup import neutralize_data
from src.plugins.manifest import PluginManifest
from src.templates.engine import TemplateEngine

CTX = {
    "demo": {
        "temp": "72",
        "row": "{red}{red}{orange}",
        "tag": "{red}HOT{/red}",
        "raw": "a{b}c",
        "span": "{icon:sun}",
        "art": "{red:HOT}",
    },
    "demo:sf": {"temp": "55"},
}


@pytest.fixture
def engine():
    return TemplateEngine()


def ext(engine: TemplateEngine, template: str) -> str:
    return engine.render(template, CTX, extended_markup=True)


# --- authoring forms -----------------------------------------------------------


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("{{red:HOT}}", "{red:HOT}"),
        ("{{Red:HOT}}", "{Red:HOT}"),
        ("{{63:HOT}}", "{63:HOT}"),
        ("{{70:HOT}}", "{70:HOT}"),
        ("{{#ff8800:HOT}}", "{#ff8800:HOT}"),
        ("{{black/white:OPEN}}", "{black/white:OPEN}"),
        ("{{#000000/63:OPEN}}", "{#000000/63:OPEN}"),
        ("{{icon:sun}}", "{icon:sun}"),
        ("A {{red:HOT}} B {{icon:up}}", "A {red:HOT} B {icon:up}"),
    ],
)
def test_authoring_form_normalises_to_markup_with_extended_markup(engine, template, expected):
    assert ext(engine, template) == expected


@pytest.mark.parametrize("template", ["{{red:HOT}}", "{{black/white:OPEN}}", "{{icon:sun}}", "{{red:{{demo.temp}}}}"])
def test_authoring_form_is_untouched_with_extended_markup_off(engine, template):
    # What the engine produced before this change: an unknown variable.
    expected = {"{{red:{{demo.temp}}}}": "{{red:72}}"}.get(template, "???")
    assert engine.render(template, CTX) == expected


@pytest.mark.parametrize("template", ["{{filled:HOT}}", "{{71:HOT}}", "{{red/filled:HOT}}", "{{foo:HOT}}"])
def test_head_outside_the_closed_grammar_stays_a_variable(engine, template):
    assert ext(engine, template) == engine.render(template, CTX)


def test_instance_key_variable_still_resolves_with_extended_markup(engine):
    assert ext(engine, "{{demo:sf.temp}}") == "55"


def test_filled_fill_space_form_still_works_with_extended_markup(engine):
    assert ext(engine, "{{filled:-}}") == engine.render("{{filled:-}}", CTX)


# --- nesting -------------------------------------------------------------------


def test_variable_inside_a_span_is_rendered_then_wrapped(engine):
    assert ext(engine, "{{red:{{demo.temp}}°}}") == "{red:72°}"


def test_formula_inside_a_span_is_rendered_then_wrapped(engine):
    assert ext(engine, "{{green:{{= 1 + 1 }} UP}}") == "{green:2 UP}"


def test_colour_tile_inside_a_span_is_rendered_then_wrapped(engine):
    assert ext(engine, "{{red:A{{green}}B}}") == "{red:A{66}B}"


def test_span_inside_a_block_is_rendered_then_wrapped(engine):
    assert ext(engine, "{{black/white:A{{red:B}}C}}") == "{black/white:A{red:B}C}"


def test_data_inside_a_span_cannot_open_markup(engine):
    assert ext(engine, "{{red:{{demo.span}}}}") == "{red:(icon:sun)}"


# --- data vs markup (every mode) ---------------------------------------------------


@pytest.mark.parametrize("extended_markup", [False, True])
def test_tile_row_from_data_passes_through(engine, extended_markup):
    assert engine.render("{{demo.row}}", CTX, extended_markup=extended_markup) == "{red}{red}{orange}"


@pytest.mark.parametrize("extended_markup", [False, True])
def test_tile_and_end_tag_from_data_render_as_today(engine, extended_markup):
    assert engine.render("{{demo.tag}}", CTX, extended_markup=extended_markup) == "{red}HOT{/red}"


@pytest.mark.parametrize("extended_markup", [False, True])
def test_span_from_data_is_neutralised(engine, extended_markup):
    assert engine.render("{{demo.art}}", CTX, extended_markup=extended_markup) == "(red:HOT)"


def test_stray_braces_from_data_become_parentheses(engine):
    assert engine.render("{{demo.raw}}", CTX) == "a(b)c"


def test_filtered_value_is_neutralised(engine):
    assert engine.render("{{demo.art|upper}}", CTX) == "(RED:HOT)"


def _markup_manifest(fmt: str) -> PluginManifest:
    return PluginManifest.from_dict(
        {
            "id": "demo",
            "name": "Demo",
            "version": "1.0.0",
            "variables": {"simple": {"art": {"format": fmt}, "temp": {}}},
        }
    )


@pytest.mark.parametrize("extended_markup", [False, True])
def test_variable_declared_as_markup_passes_through(engine, monkeypatch, extended_markup):
    monkeypatch.setattr(engine._plugin_registry, "get_manifest", lambda pid: _markup_manifest("markup"))
    assert engine.render("{{demo.art}}", CTX, extended_markup=extended_markup) == "{red:HOT}"


def test_variable_declared_as_text_is_neutralised(engine, monkeypatch):
    monkeypatch.setattr(engine._plugin_registry, "get_manifest", lambda pid: _markup_manifest("text"))
    assert engine.render("{{demo.art}}", CTX) == "(red:HOT)"


def test_markup_variable_of_a_plugin_instance_passes_through(engine, monkeypatch):
    seen = []

    def get_manifest(pid):
        seen.append(pid)
        return _markup_manifest("markup")

    monkeypatch.setattr(engine._plugin_registry, "get_manifest", get_manifest)
    ctx = {"demo:sf": {"art": "{red:HOT}"}}
    assert engine.render("{{demo:sf.art}}", ctx) == "{red:HOT}"
    assert "demo" in seen


# --- byte identity against the engine before this change ----------------------------------

GOLDEN = json.loads(
    (Path(__file__).parent / "fixtures" / "templates" / "engine_data_golden.json").read_text(encoding="utf-8")
)


def _golden_ctx(value: str) -> dict:
    return {"demo": {"value": value, "temp": "72"}}


@pytest.mark.parametrize("case", [pytest.param(c, id=f"{i}") for i, c in enumerate(GOLDEN["cases"])])
def test_output_equals_the_old_engine_fed_neutralised_data(engine, case):
    assert engine.render(case["template"], _golden_ctx(case["value"])) == case["old_neutralised"]


@pytest.mark.parametrize(
    "case",
    [pytest.param(c, id=f"{i}") for i, c in enumerate(GOLDEN["cases"]) if neutralize_data(c["value"]) == c["value"]],
)
def test_output_is_byte_identical_when_data_has_only_base_grammar(engine, case):
    assert engine.render(case["template"], _golden_ctx(case["value"])) == case["old"]


def test_golden_covers_data_that_changes():
    assert any(c["old"] != c["old_neutralised"] for c in GOLDEN["cases"])
