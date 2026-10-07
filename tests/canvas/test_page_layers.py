"""Page renders draw canvases into layers for pixel boards only (design §3 steps 2-3)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.displays.service import DisplayResult
from src.fiestaui import builtin_device_models
from src.led.charsets import resolve_character_set
from src.outputs.display_profile import display_profile_for_client
from src.pages.models import Page
from src.pages.service import PageService, page_plugin_ids
from src.pages.storage import PageStorage
from src.plugins.manifest import VARIABLE_FORMATS, PluginManifest, validate_manifest
from src.templates.engine import TemplateEngine

MODELS = builtin_device_models()


def _display(model_id, charset=None):
    return display_profile_for_client(
        SimpleNamespace(
            plugin=SimpleNamespace(device_model=MODELS[model_id], config={}),
            character_set=resolve_character_set(charset) if charset else None,
        )
    )


PIXOO = _display("divoom_pixoo64", "led_3x5")  # 64 x 64, 3x5 face: a 10 x 16 grid
FLAGSHIP = _display("vestaboard_flagship")
RED = {"background": "#ff0000"}


@pytest.fixture
def service(tmp_path):
    return PageService(storage=PageStorage(storage_file=str(tmp_path / "pages.json")))


def _page(canvases, template=("HELLO WORLD",), **kw) -> Page:
    geometry = {"device_type": "panel", "grid_rows": 10, "grid_cols": 16}
    geometry.update(kw)
    return Page(name="P", type="template", template=list(template), canvases=canvases, **geometry)


def _canvas(content=None, source=None, **area):
    a = {"row": 1, "col": 1, "rows": 1, "cols": 2}
    a.update(area)
    data = {"id": "c", "area": a}
    if content is not None:
        data["content"] = content
    if source is not None:
        data["source"] = source
    return data


def _opaque_colors(layer) -> set[bytes]:
    return {layer.rgba[i : i + 3] for i in range(0, len(layer.rgba), 4) if layer.rgba[i + 3]}


def test_a_pixel_board_gets_one_layer_per_canvas(service):
    result = service.render_page(_page([_canvas(RED)]), context={}, display=PIXOO)
    assert len(result.layers) == 1
    layer = result.layers[0]
    assert (layer.x, layer.y) == (0, 2)  # the 10 x 16 grid's origin on a 64 x 64 panel
    assert _opaque_colors(layer) == {bytes([255, 0, 0])}
    assert result.canvas_issues == []


def test_a_split_flap_board_or_no_board_gets_no_layers_but_the_cells_are_blank(service):
    page = _page([_canvas(RED, cols=5)], template=["HELLO WORLD"], device_type="flagship")
    for display in (None, FLAGSHIP):
        result = service.render_page(page, context={}, display=display)
        assert result.layers == []
        assert result.formatted.split("\n")[0].startswith("      WORLD")


def test_hide_blanks_covered_cells_on_an_led_board_too(service):
    result = service.render_page(_page([_canvas(RED, cols=5)]), context={}, display=PIXOO, extended_markup=True)
    assert result.formatted.split("\n")[0].startswith("      WORLD")
    assert len(result.layers) == 1


def test_a_page_without_canvases_renders_exactly_as_before(service):
    page = _page(None)
    a = service.render_page(page, context={}, display=PIXOO)
    assert a.layers == [] and a.content_key() == a.formatted


def test_the_content_key_changes_when_only_a_canvas_changes(service):
    red = service.render_page(_page([_canvas(RED)]), context={}, display=PIXOO)
    blue = service.render_page(_page([_canvas({"background": "#0000ff"})]), context={}, display=PIXOO)
    assert red.formatted == blue.formatted
    assert red.content_key() != blue.content_key()
    again = service.render_page(_page([_canvas(RED)]), context={}, display=PIXOO)
    assert again.content_key() == red.content_key()


def test_content_key_without_layers_is_the_formatted_text():
    assert DisplayResult("page", "AB", {}, True).content_key() == "AB"


def test_a_canvas_source_reads_a_plugin_dict_natively(service):
    context = {"art": {"canvas": {"background": "#00ff00"}}}
    result = service.render_page(_page([_canvas(source="{{art.canvas}}")]), context=context, display=PIXOO)
    assert result.canvas_issues == []
    assert _opaque_colors(result.layers[0]) == {bytes([0, 255, 0])}


def test_a_missing_source_falls_back_to_content_and_reports_an_issue(service):
    result = service.render_page(_page([_canvas(RED, source="{{art.canvas}}")]), context={}, display=PIXOO)
    assert _opaque_colors(result.layers[0]) == {bytes([255, 0, 0])}
    assert [i.path for i in result.canvas_issues] == ["source"]


def test_canvas_expressions_count_toward_the_plugins_a_page_fetches():
    page = _page([_canvas(source="{{Art.canvas}}")], template=["{{weather.temp}}"])
    assert page_plugin_ids(page) == {"weather", "art"}
    formula = _page([_canvas(RED | {"shapes": [{"type": "rect", "x": "{{= 1 + 1 }}", "y": 0, "w": 1, "h": 1}]})])
    assert page_plugin_ids(formula) is None


# --- "format": "canvas" plugin variables -----------------------------------------


def test_canvas_is_a_variable_format():
    assert "canvas" in VARIABLE_FORMATS
    ok, errors = validate_manifest(
        {"id": "art", "name": "Art", "version": "1.0.0", "variables": {"simple": {"canvas": {"format": "canvas"}}}}
    )
    assert ok, errors


def test_a_canvas_variable_in_a_template_line_renders_as_empty_text():
    manifest = PluginManifest.from_dict(
        {"id": "art", "name": "Art", "version": "1.0.0", "variables": {"simple": {"canvas": {"format": "canvas"}}}}
    )
    engine = TemplateEngine()
    engine._plugin_registry = SimpleNamespace(get_manifest=lambda pid: manifest if pid == "art" else None)
    context = {"art": {"canvas": {"background": "#00ff00"}, "title": "SUNSET"}}
    assert engine.render("A{{art.canvas}}B {{art.title}}", context) == "AB SUNSET"


def test_an_oversized_area_is_clamped_to_the_board_at_render(service):
    whole = _canvas(RED, rows=96, cols=128)
    pixel = service.render_page(_page([whole]), context={}, display=PIXOO)
    layer = pixel.layers[0]
    assert (layer.x, layer.y, layer.w) == (0, 2, 63)  # the whole 16-column grid, trailing gutter excluded
    flap = service.render_page(_page([whole], device_type="flagship"), context={})
    assert flap.formatted == "\n".join([" " * 22] * 6)
