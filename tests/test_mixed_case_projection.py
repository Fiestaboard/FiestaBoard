"""Case on the render path: uppercasing belongs to the flap projection only.

FiestaUI's TemplateEditor (FiestaUI PR #332) saves lowercase exactly as
typed for a ``mixedCase`` character set (the LED sets, ``led_5x7`` and
``led_3x5``); flap sets and boards with no set still uppercase. So:

- the template engine never uppercases text (only the explicit ``|upper``
  filter does);
- a board whose set is ``mixedCase`` receives lowercase cells for lowercase
  text; a rich set without ``mixedCase`` gets them uppercased by projection;
- a split-flap board's grid is ``text_to_board_array``'s, byte for byte.

And what a set lacks (a span, an icon) stays as markup in the stored
template: only the projection falls back. Core never rewrites a template.
"""

from __future__ import annotations

import pytest

from src.led.charsets import BUILTIN_CHARACTER_SETS
from src.outputs.cells import project_message
from src.text_to_board import text_to_board_array

LED_5X7 = BUILTIN_CHARACTER_SETS["led_5x7"]
LED_3X5 = BUILTIN_CHARACTER_SETS["led_3x5"]
V1 = BUILTIN_CHARACTER_SETS["vestaboard_v1"]
V2 = BUILTIN_CHARACTER_SETS["vestaboard_v2"]

#: A rich set (block spans) that does not draw lowercase.
UPPER_ONLY = {
    "id": "upper_sign_v1",
    "label": "Upper sign",
    "version": 1,
    "chars": [*"ABCDEFGHIJKLMNOPQRSTUVWXYZ", "0", "1"],
    "tiles": False,
    "icons": [],
    "mixedCase": False,
    "colorSpans": False,
    "blockSpans": True,
}

LOWERCASE = ["hello world", "Mixed Case {red:hot} {icon:sun}", "abc\ndef\nghi", "°♥ lower ~ é"]


def _values(row):
    return "".join(cell.value for cell in row if cell.type == "char").rstrip()


@pytest.mark.parametrize("charset", [LED_5X7, LED_3X5], ids=["led_5x7", "led_3x5"])
def test_a_mixed_case_board_receives_lowercase_cells(charset):
    cells = project_message("hello World", 1, 16, charset).cells
    assert _values(cells[0]) == "hello World"


def test_a_rich_set_without_mixed_case_gets_uppercase_cells():
    cells = project_message("hello", 1, 6, UPPER_ONLY).cells
    assert _values(cells[0]) == "HELLO"


@pytest.mark.parametrize("charset", [None, V1, V2], ids=["none", "vestaboard_v1", "vestaboard_v2"])
@pytest.mark.parametrize("message", LOWERCASE)
def test_a_split_flap_board_is_uppercased_byte_for_byte(charset, message):
    frame = project_message(message, 6, 22, charset)
    assert frame.characters == text_to_board_array(message, rows=6, cols=22)
    assert frame.characters == text_to_board_array(message.upper(), rows=6, cols=22)
    assert frame.cells is None


def test_the_template_engine_keeps_lowercase_as_typed():
    from src.templates.engine import TemplateEngine

    engine = TemplateEngine()
    for extended in (False, True):
        kw = {"extended_markup": True} if extended else {}
        assert engine.render_lines(["hello {{red:hot}}"], context={}, **kw).split("\n")[0].startswith("hello")


def test_an_led_board_driven_by_the_engine_receives_lowercase_cells():
    from tests.test_rich_cell_projection import _engine_send

    client, _pages = _engine_send("hello world", LED_5X7)
    cells = client.render.call_args.kwargs["cells"]
    assert _values(cells[0]) == "hello world"


def test_a_split_flap_board_driven_by_the_engine_is_unchanged():
    from tests.test_rich_cell_projection import _engine_send

    client, _pages = _engine_send("hello world", None)
    assert client.render.call_args.args[0] == text_to_board_array("HELLO WORLD", rows=6, cols=22)
    assert "cells" not in client.render.call_args.kwargs


def test_markup_a_set_lacks_is_projected_by_fallback_and_never_rewritten(tmp_path):
    """Spans and an icon the board's set cannot draw: the cells fall back
    (icon to its registry fallback, spans dropped), the stored template keeps
    every piece of markup exactly as written."""
    from src.pages.models import PageCreate
    from src.pages.service import PageService
    from src.pages.storage import PageStorage

    template = ["{{red:hot}} {{icon:sun}}", "{{black/white:OPEN}}"]
    service = PageService(PageStorage(str(tmp_path / "pages.json")))
    page = service.create_page(PageCreate(name="Hot", type="template", template=template))

    rendered = service.preview_page(page.id, extended_markup=True).formatted
    assert [line.rstrip() for line in rendered.split("\n")[:2]] == [
        "{red:hot} {icon:sun}",
        "{black/white:OPEN}",
    ]  # markup kept as written
    first, second = project_message(rendered, 2, 12, UPPER_ONLY).cells
    assert [c.to_dict() for c in first[:3]] == [{"type": "char", "value": c} for c in "HOT"]  # colour span dropped
    assert first[4].icon is None  # the set has no icons: the registry fallback, not the icon
    assert second[0].to_dict() == {"type": "char", "value": "O", "background": "white"}  # block span kept

    assert service.get_page(page.id).template == template
    reloaded = PageService(PageStorage(str(tmp_path / "pages.json"))).get_page(page.id)
    assert reloaded.template == template
