"""``PageService`` renders flexible pages (plan Task 13).

A flexible page renders against a board: the layout engine draws a
full-frame image for a pixel board, delivered as one opaque full-frame layer,
with the page's real text at the board's character grid underneath; a
split-flap board gets the cells alone. Every compromise rides on the result
as ``layout_issues``.

The plan's end-to-end tests run the real expansion and fit. The service's
dispatch is also pinned against the stand-in expansion
:mod:`tests.layout.test_engine` uses, and a stand-in ``flexible_plugin_ids``.
"""

# ruff: noqa: F811  (the tests take the fixtures imported from test_engine)

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from src.devices import size_key
from src.layout.engine import layout_flexible_page
from src.layout.target import flex_target_for
from src.led.matrix import LedLayoutOptions, LedMatrixSpec, layout_message, rasterize
from src.outputs.cells import frame_layers, project_for_output
from src.outputs.physical_frames import physical_frame_layer
from src.outputs.plugin_driver import OutputPluginDriver
from src.pages import service as service_module
from src.pages.models import Page
from src.pages.service import PageService, page_plugin_ids
from src.pages.storage import PageStorage
from src.settings.service import get_settings_service
from tests.canvas.test_output_layers import LED_3X5, Sign
from tests.layout.devices import SAMPLE, SAMPLE_CTX, profile
from tests.layout.test_engine import stub_expand  # noqa: F401

CTX = {"clock": {"time": "12:45"}}

PIXOO_BOARD = {
    "id": "pixoo",
    "name": "Pixoo",
    "device_type": "panel",
    "grid_rows": 10,
    "grid_cols": 16,
    "device_model": "divoom_pixoo64",
}
FLAGSHIP_BOARD = {"id": "flag", "name": "Flagship", "device_type": "flagship"}
NOTE_BOARD = {"id": "note", "name": "Note", "device_type": "note"}
STRIP_BOARD = {
    "id": "strip",
    "name": "Strip",
    "device_type": "panel",
    "grid_rows": 1,
    "grid_cols": 5,
    "device_model": "ulanzi_tc001_awtrix",
}


@pytest.fixture
def pixoo_display():
    return profile("divoom_pixoo64", "3x5")


@pytest.fixture
def service(tmp_path) -> PageService:
    return PageService(PageStorage(str(tmp_path / "pages.json")))


@pytest.fixture
def stub_refs(monkeypatch: pytest.MonkeyPatch) -> list[Page]:
    """Replace the service's ``flexible_plugin_ids`` with one that answers ``{"clock"}``."""
    calls: list[Page] = []

    def flexible_plugin_ids(page):
        calls.append(page)
        return {"clock"}

    monkeypatch.setattr(service_module, "flexible_plugin_ids", flexible_plugin_ids)
    return calls


def flex(*blocks: dict[str, Any], **fields: Any) -> Page:
    return Page.model_validate({"name": "Flex", "type": "flexible", "blocks": list(blocks), **fields})


def text(bid: str, value: str) -> dict[str, Any]:
    return {"id": bid, "kind": "text", "text": value}


def red_band() -> Page:
    return flex({"id": "s", "kind": "spacer", "style": {"height": 4, "background": "#ff0000"}})


def rgba_at(layer, x: int, y: int) -> bytes:
    i = (y * layer.w + x) * 4
    return layer.rgba[i : i + 4]


# --- the plan's end-to-end tests ---------------------------------------------


def test_cells_under_the_frame_are_real_text_at_the_boards_grid(service, pixoo_display):
    r = service.render_page(Page.model_validate(SAMPLE), context=SAMPLE_CTX, display=pixoo_display, board=PIXOO_BOARD)
    assert len(r.formatted.split("\n")) == 10 and "12:45" in r.formatted


def test_pixel_render_labels_text_as_an_alternate_projection(service, pixoo_display):
    r = service.render_page(Page.model_validate(SAMPLE), context=SAMPLE_CTX, display=pixoo_display, board=PIXOO_BOARD)
    assert r.raw["text_representation"] == "cell_projection"
    assert r.raw["surface"] == {"kind": "pixels", "width": 64, "height": 64}


def test_character_render_labels_text_as_the_visible_cell_grid(service):
    r = service.render_page(Page.model_validate(SAMPLE), context=SAMPLE_CTX, board=FLAGSHIP_BOARD)
    assert r.raw["text_representation"] == "visible_cells"
    assert r.raw["surface"] == {"kind": "cells", "rows": 6, "cols": 22}


def test_layout_issues_of_a_crowded_strip_are_on_the_display_result(service):
    strip = profile("ulanzi_tc001_awtrix")
    r = service.render_page(Page.model_validate(SAMPLE), context=SAMPLE_CTX, display=strip, board=STRIP_BOARD)
    assert any(i.code == "dropped" for i in r.layout_issues)


# --- dispatch, against the stand-in expansion ---------------------------------


def test_flexible_render_on_pixel_board_carries_one_full_frame_layer(service, stub_expand, stub_refs, pixoo_display):
    r = service.render_page(red_band(), context=CTX, display=pixoo_display, board=PIXOO_BOARD)
    assert r.available and [(la.x, la.y, la.w, la.h) for la in r.layers] == [(0, 0, 64, 64)]


def test_full_frame_layer_is_opaque(service, stub_expand, stub_refs, pixoo_display):
    r = service.render_page(red_band(), context=CTX, display=pixoo_display, board=PIXOO_BOARD)
    layer = r.layers[0]
    assert all(layer.rgba[i] == 255 for i in range(3, len(layer.rgba), 4))


def test_full_frame_layer_is_the_laid_out_frame(service, stub_expand, stub_refs, pixoo_display):
    r = service.render_page(red_band(), context=CTX, display=pixoo_display, board=PIXOO_BOARD)
    expected = layout_flexible_page(red_band(), flex_target_for(PIXOO_BOARD, pixoo_display), CTX).frame
    assert r.layers == [physical_frame_layer(expected)]
    assert (rgba_at(r.layers[0], 0, 0), rgba_at(r.layers[0], 0, 4)) == (b"\xff\x00\x00\xff", b"\x00\x00\x00\xff")


def test_flexible_mono_delivery_matches_the_laid_out_frame(service):
    display = profile("max7219_4in1")
    board = {**STRIP_BOARD, "device_model": "max7219_4in1", "grid_cols": display.cols}
    page = flex(text("t", "HI"), style={"size": "small"})
    expected = layout_flexible_page(page, flex_target_for(board, display), {}).frame
    result = service.render_page(page, context={}, display=display, board=board)
    final = rasterize(
        layout_message(
            result.formatted,
            LedMatrixSpec(display.width, display.height, display.font),
            LedLayoutOptions(monochrome=display.monochrome),
            layers=result.layers,
        )
    )
    assert result.available and any(expected.pixels)
    assert final.pixels == expected.pixels


def test_cells_under_the_frame_are_at_the_boards_grid(service, stub_expand, stub_refs, pixoo_display):
    r = service.render_page(red_band(), context=CTX, display=pixoo_display, board=PIXOO_BOARD)
    assert r.formatted.split("\n") == [" " * 16] * 10


def test_flexible_render_on_flagship_is_cells_only(service, stub_expand, stub_refs):
    r = service.render_page(flex(text("t", "HELLO")), context=CTX, board=FLAGSHIP_BOARD)
    assert r.layers == [] and r.formatted.split("\n") == ["HELLO" + " " * 17] + [" " * 22] * 5


def test_flexible_result_names_the_page_and_the_blocks_shown(service, stub_expand, stub_refs):
    page = flex(text("t", "HELLO"), {"id": "c", "kind": "canvas", "canvas": {}})
    r = service.render_page(page, context=CTX, board=FLAGSHIP_BOARD)
    assert (r.display_type, r.available, r.raw) == (
        "page:flexible",
        True,
        {
            "page_id": page.id,
            "shown": ["t"],
            "text_representation": "visible_cells",
            "surface": {"kind": "cells", "rows": 6, "cols": 22},
        },
    )


def test_layout_issues_are_on_the_display_result(service, stub_expand, stub_refs):
    r = service.render_page(flex({"id": "c", "kind": "canvas", "canvas": {}}), context=CTX, board=FLAGSHIP_BOARD)
    assert [(i.path, i.code) for i in r.layout_issues] == [(("blocks", "c"), "canvas_not_drawn")]


def test_grid_page_result_has_no_layout_issues(service):
    r = service.render_page(Page(name="G", type="template", template=["HI"]))
    assert r.layout_issues == []


def test_without_a_board_a_flexible_page_renders_against_the_primary_board(service, stub_expand, stub_refs):
    get_settings_service().set_boards([NOTE_BOARD, FLAGSHIP_BOARD])
    r = service.render_page(flex(text("t", "HI")), context=CTX)
    assert len(r.formatted.split("\n")) == 3


def test_without_any_board_a_flexible_page_renders_flagship_cells(service, stub_expand, stub_refs):
    with patch("src.pages.service._find_board", return_value=None):
        r = service.render_page(flex(text("t", "HI")), context=CTX)
    assert len(r.formatted.split("\n")) == 6


def test_given_context_reaches_the_layout(service, stub_expand, stub_refs):
    service.render_page(flex(text("t", "HI")), context=CTX, board=FLAGSHIP_BOARD)
    assert stub_expand[0]["context"]["clock"] is CTX["clock"]


def test_shared_contexts_are_keyed_by_the_boards_size_and_display(service, stub_expand, stub_refs, pixoo_display):
    shared = {"clock": {"time": "09:00"}}
    contexts = {f"{size_key('panel', 1, 1, 10, 16)}|{pixoo_display.key}": shared}
    service.render_page(red_band(), contexts=contexts, display=pixoo_display, board=PIXOO_BOARD)
    assert stub_expand[0]["context"]["clock"] is shared["clock"]


def test_without_a_shared_context_the_context_is_built_for_the_board(service, stub_expand, stub_refs, pixoo_display):
    with patch("src.pages.service.get_template_engine") as engine:
        engine.return_value.build_context.return_value = CTX
        service.render_page(red_band(), display=pixoo_display, board=PIXOO_BOARD)
    (board,), kw = engine.return_value.build_context.call_args
    assert (board.rows, board.cols, board.display, kw["plugin_ids"]) == (10, 16, pixoo_display, {"clock"})
    assert stub_expand[0]["context"]["clock"] is CTX["clock"]


def test_a_failed_layout_is_an_unavailable_result(service, stub_expand, stub_refs):
    with patch("src.pages.service.layout_flexible_page", side_effect=RuntimeError("boom")):
        r = service.render_page(flex(text("t", "HI")), context=CTX, board=FLAGSHIP_BOARD)
    assert (r.available, r.display_type) == (False, "page:flexible") and "boom" in r.error


def test_page_plugin_ids_of_a_flexible_page_are_its_flexible_plugin_ids(stub_refs):
    assert page_plugin_ids(flex(text("t", "{{clock.time}}"))) == {"clock"}


def test_projected_rich_cells_carry_the_layer(service, stub_expand, stub_refs, pixoo_display):
    r = service.render_page(red_band(), context=CTX, display=pixoo_display, board=PIXOO_BOARD)
    driver = OutputPluginDriver(Sign(), character_set=LED_3X5)
    _chars, kw = project_for_output(driver, r.formatted, 10, 16, layers=r.layers)
    assert frame_layers(kw["cells"]) == tuple(r.layers)


# --- previews ------------------------------------------------------------------


def test_preview_page_renders_against_the_given_board(service, stub_expand, stub_refs):
    page = service.storage.create(flex(text("t", "HI")))
    with patch("src.plugins.registry.get_plugin_registry"):
        r = service.preview_page(page.id, context=CTX, board=NOTE_BOARD)
    assert len(r.formatted.split("\n")) == 3


def test_cell_surface_metadata_uses_the_resolved_display_grid(service, stub_expand, stub_refs, pixoo_display):
    from dataclasses import replace

    display = replace(pixoo_display, technology="split_flap", width=None, height=None, rows=3, cols=15)
    result = service.render_page(flex(text("t", "HI")), context=CTX, display=display, board=PIXOO_BOARD)
    assert result.available
    assert result.raw["surface"] == {"kind": "cells", "rows": 3, "cols": 15}


def test_batch_preview_shares_context_by_board_size(service, stub_expand, stub_refs, pixoo_display):
    a = service.storage.create(red_band())
    b = service.storage.create(red_band())
    with patch("src.plugins.registry.get_plugin_registry") as registry:
        registry.return_value.build_template_contexts_for.return_value = {}
        service.preview_pages_batch([a.id, b.id], display=pixoo_display, board=PIXOO_BOARD)
    (boards,), _ = registry.return_value.build_template_contexts_for.call_args
    assert list(boards) == [f"{size_key('panel', 1, 1, 10, 16)}|{pixoo_display.key}"]


def test_batch_preview_renders_flexible_pages_with_the_shared_context(service, stub_expand, stub_refs, pixoo_display):
    a = service.storage.create(red_band())
    shared = {"clock": {"time": "09:00"}}
    key = f"{size_key('panel', 1, 1, 10, 16)}|{pixoo_display.key}"
    with patch("src.plugins.registry.get_plugin_registry") as registry:
        registry.return_value.build_template_contexts_for.return_value = {key: shared}
        results = service.preview_pages_batch([a.id], display=pixoo_display, board=PIXOO_BOARD)
    assert results[a.id].layers and stub_expand[0]["context"]["clock"] is shared["clock"]


def test_batch_preview_fetches_the_flexible_pages_plugins(service, stub_expand, stub_refs, pixoo_display):
    a = service.storage.create(red_band())
    with patch("src.plugins.registry.get_plugin_registry") as registry:
        registry.return_value.build_template_contexts_for.return_value = {}
        service.preview_pages_batch([a.id], display=pixoo_display, board=PIXOO_BOARD)
    _, kw = registry.return_value.build_template_contexts_for.call_args
    assert list(kw["plugin_ids"].values()) == [{"clock"}]


def test_batch_preview_renders_flexible_pages_against_the_given_board(service, stub_expand, stub_refs):
    a = service.storage.create(flex(text("t", "HI")))
    with patch("src.plugins.registry.get_plugin_registry") as registry:
        registry.return_value.build_template_contexts_for.return_value = {}
        results = service.preview_pages_batch([a.id], board=NOTE_BOARD)
    assert len(results[a.id].formatted.split("\n")) == 3


def test_batch_and_single_previews_of_a_flexible_page_build_the_same_board_context(
    service, stub_expand, stub_refs, pixoo_display, monkeypatch
):
    # No board or display named: both lay the page out for the primary board as it draws.
    monkeypatch.setattr(service_module, "_find_board", lambda board_id: PIXOO_BOARD)
    monkeypatch.setattr(service_module, "display_profile_for_board", lambda board: pixoo_display)
    page = service.storage.create(red_band())
    with patch("src.plugins.registry.get_plugin_registry") as registry:
        registry.return_value.build_template_contexts_for.return_value = {}
        service.preview_pages_batch([page.id], force_refresh=True)
    (boards,), _ = registry.return_value.build_template_contexts_for.call_args
    with patch.object(service_module, "get_template_engine") as engine:
        engine.return_value.build_context.return_value = {}
        service.preview_page(page.id, force_refresh=True)
    (single,), _ = engine.return_value.build_context.call_args
    assert list(boards) == [f"{size_key('panel', 1, 1, 10, 16)}|{pixoo_display.key}"]
    assert list(boards.values()) == [single]


def test_batch_preview_of_a_flexible_page_with_no_display_uses_the_shared_context(
    service, stub_expand, stub_refs, pixoo_display, monkeypatch
):
    monkeypatch.setattr(service_module, "_find_board", lambda board_id: PIXOO_BOARD)
    monkeypatch.setattr(service_module, "display_profile_for_board", lambda board: pixoo_display)
    page = service.storage.create(red_band())
    shared = {"clock": {"time": "09:00"}}
    key = f"{size_key('panel', 1, 1, 10, 16)}|{pixoo_display.key}"
    with patch("src.plugins.registry.get_plugin_registry") as registry:
        registry.return_value.build_template_contexts_for.return_value = {key: shared}
        results = service.preview_pages_batch([page.id], force_refresh=True)
    assert results[page.id].layers and stub_expand[0]["context"]["clock"] is shared["clock"]
