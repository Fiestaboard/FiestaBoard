"""Block expansion for flexible layout (plan Task 6, spec section 5 step 1).

Each block's text goes through the template engine's expansion only (never
the grid render); width-dependent fills become sentinels the layout resolves
in pixels or tiles; ``if`` hides a block; case and the board's charset
fallback are applied before measuring, so the frame and the hidden cells
agree.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.layout.expand import (
    FILL_SENTINEL_BASE,
    ExpandedBlock,
    FillSpec,
    expand_blocks,
    markup_with_fills,
)
from src.layout.refs import flexible_plugin_ids
from src.layout.style import resolve_block_style
from src.layout.target import FlexTarget
from src.led.charsets import CharsetLookup, charset_fallback
from src.markup import map_text_case, parse_line
from src.outputs.cells import project_message
from src.pages.models import Page
from src.templates.engine import get_template_engine
from tests.layout.devices import golden_target

PIXOO = golden_target("pixoo64_3x5")
FLAGSHIP = golden_target("flagship")

SENTINEL = chr(FILL_SENTINEL_BASE)


def page_with(text: str, *, if_: str | None = None, color: str | None = None, **block: Any) -> Page:
    body: dict[str, Any] = {"id": "b1", "kind": "text", "text": text, **block}
    if if_ is not None:
        body["if"] = if_
    if color is not None:
        body["style"] = {**body.get("style", {}), "color": color}
    return Page.model_validate({"name": "P", "type": "flexible", "blocks": [body]})


def styles_for(page: Page, target: FlexTarget) -> dict[str, Any]:
    return {
        b.id: resolve_block_style([b.style.model_dump(exclude_none=True) if b.style else None], target, {}, path=())[0]
        for b in page.blocks
    }


def expand(page: Page, target: FlexTarget = PIXOO, context: dict | None = None, **kw: Any):
    return expand_blocks(page, target, context or {}, styles_for(page, target), **kw)


def values(block: ExpandedBlock) -> str:
    return "".join(t.value for t in block.tokens)


# --- expansion ---------------------------------------------------------------


def test_expansion_uses_render_not_render_lines(monkeypatch):
    engine = get_template_engine()
    monkeypatch.setattr(engine, "render_lines", lambda *a, **k: pytest.fail("grid render"))
    blocks, _ = expand(page_with("{{x.y}} OK"), context={"x": {"y": "72"}}, engine=engine)
    assert values(blocks[0]) == "72 OK"


def test_large_plugin_text_is_bounded_before_markup_tokenization():
    blocks, issues = expand(page_with("{{feed.text}}"), context={"feed": {"text": "X" * 100_000}})
    assert len(blocks[0].tokens) <= 4096
    assert any(i.code == "truncated" and i.path == ("blocks", "b1", "text") for i in issues)


def test_large_authored_text_remains_in_document_but_render_is_bounded():
    page = page_with("X" * 100_000)
    blocks, issues = expand(page)
    assert len(page.blocks[0].text) == 100_000
    assert len(blocks[0].tokens) <= 4096
    assert any(i.code == "truncated" for i in issues)


def test_expanded_block_carries_its_page_position():
    p = Page.model_validate(
        {
            "name": "P",
            "type": "flexible",
            "blocks": [
                {"id": "a", "kind": "spacer"},
                {"id": "b", "kind": "text", "text": "HI", "priority": 4},
            ],
        }
    )
    blocks, _ = expand(p)
    assert [(b.id, b.kind, b.index, b.priority, b.block.id) for b in blocks] == [
        ("a", "spacer", 0, None, "a"),
        ("b", "text", 1, 4, "b"),
    ]


def test_icon_shortcut_expands_to_an_icon_token():
    blocks, _ = expand(page_with("{sun} HI"))
    assert blocks[0].tokens[0].icon == "sun"


def test_fill_space_becomes_sentinel_not_padding():
    b, _ = expand(page_with("A{{fill_space}}B"))
    assert b[0].fills == (FillSpec(None),) and b[0].markup == "A" + SENTINEL + "B"


def test_fill_inside_colour_span_keeps_span_on_both_sides():
    b, _ = expand(page_with("{red:A{{filled:-}}B}"))
    assert b[0].tokens[0].color and b[0].tokens[-1].color and b[0].fills == (FillSpec("-"),)


def test_second_fill_is_the_next_sentinel():
    b, _ = expand(page_with("A{{fill_space}}B{{filled:=}}C"))
    assert b[0].fills == (FillSpec(None), FillSpec("=")) and chr(FILL_SENTINEL_BASE + 1) in b[0].markup


def test_markup_with_fills_turns_sentinels_into_text():
    b, _ = expand(page_with("A{{fill_space}}B{{filled:=}}C"))
    assert markup_with_fills(b[0], lambda spec: f"<{spec.pattern}>") == "A<None>B<=>C"


# --- if ----------------------------------------------------------------------


def test_false_if_hides_block_silently_and_error_reports():
    shown, issues = expand(page_with("HI", if_="{{= 1 > 2 }}"))
    assert shown == [] and issues == []
    shown, issues = expand(page_with("HI", if_="{{= NOPE( }}"))
    assert shown == [] and issues[0].code == "if_failed" and issues[0].path == ("blocks", "b1", "if")


def test_true_if_shows_block():
    shown, issues = expand(page_with("HI", if_="{{x.up}}"), context={"x": {"up": True}})
    assert [b.id for b in shown] == ["b1"] and issues == []


def test_if_without_braces_is_a_formula():
    shown, _ = expand(page_with("HI", if_="1 > 2"))
    assert shown == []


# --- kinds -------------------------------------------------------------------


def test_unknown_block_kind_is_skipped_with_issue():
    p = Page.model_validate({"name": "P", "type": "flexible", "blocks": [{"id": "m", "kind": "marquee"}]})
    shown, issues = expand(p)
    assert shown == [] and [(i.path, i.code, i.severity) for i in issues] == [
        (("blocks", "m"), "block_kind_unsupported", "warning")
    ]


def test_spacer_and_canvas_have_no_text():
    p = Page.model_validate(
        {
            "name": "P",
            "type": "flexible",
            "blocks": [{"id": "s", "kind": "spacer"}, {"id": "c", "kind": "canvas", "canvas": {}}],
        }
    )
    shown, _ = expand(p)
    assert [(b.markup, b.tokens, b.fills) for b in shown] == [("", (), ()), ("", (), ())]


# --- case and charset fallback -------------------------------------------------


def test_upper_case_style_uppercases_text_not_markup():
    b, _ = expand(page_with("{red:hot} day", style={"case": "upper"}))
    assert b[0].markup == "{red:HOT} DAY" and b[0].tokens[0].color == "red"


def test_lower_case_style_on_a_mixed_case_board():
    b, _ = expand(page_with("HELLO", style={"case": "lower"}))
    assert values(b[0]) == "hello"


def test_board_without_lowercase_draws_capitals():
    b, _ = expand(page_with("hello"), FLAGSHIP)
    assert values(b[0]) == "HELLO" and b[0].markup == "HELLO"


def test_unsupported_characters_fall_back_identically_to_cells():  # [RF-2]
    b, _ = expand(page_with("café ✨ ok"), FLAGSHIP)
    projected = project_message(b[0].markup.replace(SENTINEL, ""), 1, 22, None)
    assert [t.flap_code for t in b[0].tokens] == projected.characters[0][: len(b[0].tokens)]


def test_unsupported_characters_on_a_pixoo_fall_back_identically_to_cells():  # [RF-2]
    charset = PIXOO.display.character_set
    assert "é" not in CharsetLookup(charset).chars  # the premise: led_3x5 has no é
    b, _ = expand(page_with("café ok"), PIXOO)
    projected = project_message(b[0].markup, 1, 16, charset)
    assert list(b[0].tokens) == projected.cells[0][: len(b[0].tokens)]
    assert b[0].tokens[3] == charset_fallback(charset, parse_line("é", extended_markup=True, preserve_case=True)[0])


def test_fill_sentinels_survive_charset_fallback():
    b, _ = expand(page_with("A{{fill_space}}B"))
    assert [t.value for t in b[0].tokens] == ["A", SENTINEL, "B"]


# --- map_text_case -------------------------------------------------------------


def test_map_text_case_keeps_span_heads_and_icons():
    assert map_text_case("{red:hot} {icon:sun} x", str.upper) == "{red:HOT} {icon:sun} X"


def test_map_text_case_plain_text():
    assert map_text_case("Hello", str.lower) == "hello"


# --- plugin references ---------------------------------------------------------


def test_flexible_plugin_ids_cover_text_if_colour_and_canvas():
    assert flexible_plugin_ids(page_with("{{weather.temp}}", if_="{{stocks.up}}", color="{{air.color}}")) == {
        "weather",
        "stocks",
        "air",
    }


def test_flexible_plugin_ids_cover_canvas_and_page_style():
    p = Page.model_validate(
        {
            "name": "P",
            "type": "flexible",
            "style": {"background": "{{sky.color}}"},
            "blocks": [{"id": "c", "kind": "canvas", "canvas": {"source": "{{art.canvas}}"}}],
        }
    )
    assert flexible_plugin_ids(p) == {"sky", "art"}


def test_flexible_plugin_ids_unwrapped_if_counts():
    assert flexible_plugin_ids(page_with("HI", if_="stocks.up")) == {"stocks"}


@pytest.mark.parametrize("condition", ["weather.temp > stocks.limit", "{{ weather.temp > stocks.limit }}"])
def test_condition_dependencies_include_both_operands(condition):
    assert flexible_plugin_ids(page_with("HI", if_=condition)) == {"weather", "stocks"}


def test_clock_only_condition_cannot_use_a_constant_input_fingerprint():
    assert flexible_plugin_ids(page_with("HI", if_="HOUR(NOW()) >= 9")) is None


def test_flexible_plugin_ids_with_a_formula_is_unknown():
    assert flexible_plugin_ids(page_with("{{= UPPER(weather.temp) }}")) is None


def test_flexible_plugin_ids_of_an_empty_page():
    assert flexible_plugin_ids(Page.model_validate({"name": "P", "type": "flexible", "blocks": []})) == set()


# --- the engine's public fill resolver ------------------------------------------


def test_engine_resolve_fill_fills_to_width():
    assert get_template_engine().resolve_fill("A\x00FILL_SPACE\x00B", width=5) == "A   B"


def test_engine_resolve_fill_repeats_a_pattern():
    assert get_template_engine().resolve_fill("A\x00FILL_SPACE_REPEAT:-\x00B", width=5) == "A---B"
