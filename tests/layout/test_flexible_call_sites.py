"""Every page geometry call site routes flexible pages explicitly (plan Task 14).

A flexible page has no grid, so ``geometry_of`` raises for it
(``FlexiblePageGeometryError``). Each site that receives a page either takes
its geometry from the board the page shows on, skips flexible pages, or never
reaches the grid code for them. One test per site, named for the behaviour;
``geometry_call_sites.json`` names the test that covers each page site.

The layout engine's expansion (plan Task 6) and plugin references are stood
in for exactly as in ``tests/layout/test_flexible_render.py``.
"""

# ruff: noqa: F811  (the tests take fixtures imported from other test modules)

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import patch

import pytest

from src.led.page_frame import is_full_frame_layer
from src.main import DisplayService
from src.pages.fit import PageFit, page_fit_for_board
from src.pages.models import Page, PageCreate, PageUpdate
from src.pages.service import (
    PageService,
    check_ref_board_compatibility,
    find_incompatible_board_references,
    find_incompatible_references,
    get_page_service,
)
from src.settings.service import get_settings_service
from tests.layout.test_engine import stub_expand  # noqa: F401
from tests.layout.test_flexible_render import stub_refs  # noqa: F401
from tests.test_engine_page_face import BOARD as PIXOO_8X10
from tests.test_engine_page_face import Engine
from tests.test_led_text_size import _board, pixoo_output  # noqa: F401
from tests.test_routes_page_face import ENDPOINTS, LEGACY_ENDPOINTS, _last_cells, _send
from tests.test_routes_page_face import board as pixoo_route_board  # noqa: F401
from tests.test_v1_contract import client  # noqa: F401

FLAGSHIP_BOARD = {"id": "board-flagship", "name": "Kitchen", "device_type": "flagship"}
NOTE_BOARD = {"id": "board-note", "name": "Office", "device_type": "note"}
NO_GRID = "A flexible page has no grid; it fits every board"


def flex(*blocks: dict[str, Any], **fields: Any) -> Page:
    blocks = blocks or ({"id": "t", "kind": "text", "text": "HI"},)
    return Page.model_validate({"name": "Flex", "type": "flexible", "blocks": list(blocks), **fields})


def red_band(**fields: Any) -> Page:
    return flex({"id": "s", "kind": "spacer", "style": {"height": 4, "background": "#ff0000"}}, **fields)


def grid_page(name: str = "Grid", **fields: Any) -> Page:
    return Page(name=name, type="template", template=[name.upper()], **fields)


def stored(page: Page) -> Page:
    return get_page_service().storage.create(page)


# --- the display engine (src/main.py) -----------------------------------------


@pytest.fixture
def engine(pixoo_output, monkeypatch, stub_expand, stub_refs):
    """The 8 x 10 Pixoo engine of ``tests/test_engine_page_face.py``, laying out flexible pages."""
    return Engine(monkeypatch)


def test_engine_sends_flexible_page_at_board_grid(engine):
    engine.tick(active=red_band(id="flex-1"))
    cells = engine.plugin.last_cells
    assert (len(cells), len(cells[0])) == (8, 10)
    assert len(cells.layers) == 1 and is_full_frame_layer(cells.layers[0], 64, 64)


def test_engine_lays_a_flexible_page_out_for_the_board_it_sends_to(engine):
    with patch.object(PageService, "_render_flexible", autospec=True, side_effect=PageService._render_flexible) as spy:
        engine.tick(active=red_band(id="flex-1"))
    assert spy.call_args.kwargs["board"]["id"] == PIXOO_8X10["id"]


def test_engine_sends_flexible_page_with_the_boards_device_type(engine):
    engine.tick(active=red_band(id="flex-1"))
    assert engine.client_render_kwargs["device_type"] == "panel"


def test_engine_skips_a_flexible_page_its_targets_exclude_with_the_reason_logged(engine, caplog):
    page = red_band(id="flex-1", targets={"technology": ["split_flap"]})
    with caplog.at_level(logging.WARNING, logger="src.main"):
        assert engine.tick(active=page) is False
    assert "This page is set to show only on split-flap boards" in caplog.text


def test_silence_page_may_be_flexible(engine):
    engine.tick(silence_page=red_band(id="flex-silence"))
    cells = engine.plugin.last_cells
    assert (len(cells), len(cells[0])) == (8, 10) and len(cells.layers) == 1


def test_silence_page_lays_out_for_the_board_it_silences(engine):
    with patch.object(PageService, "_render_flexible", autospec=True, side_effect=PageService._render_flexible) as spy:
        engine.tick(silence_page=red_band(id="flex-silence"))
    assert spy.call_args.kwargs["board"]["id"] == PIXOO_8X10["id"]


def test_render_fingerprint_never_reads_a_flexible_pages_geometry(caplog, stub_refs):
    # The fingerprint sizes a flexible page by the board it lays out for
    # (Task 15), never as a 6 x 22 grid page; it swallows any error, so the
    # debug log is what tells.
    page = red_band(id="flex-1")
    with caplog.at_level(logging.DEBUG, logger="src.main"):
        fingerprint = DisplayService._render_fingerprint(page, page.id, PageService(), {}, override_active=False)
    assert "Render fingerprint unavailable" not in caplog.text
    assert fingerprint is not None


# --- sends and previews over the API ------------------------------------------


@pytest.mark.parametrize("endpoint", ENDPOINTS + LEGACY_ENDPOINTS)
def test_a_flexible_page_sent_by_any_route_arrives_at_the_boards_grid_under_one_full_frame(
    client, pixoo_route_board, stub_expand, stub_refs, endpoint
):
    plugin, _ = pixoo_route_board
    _send(client, endpoint, stored(red_band()).id)
    cells = _last_cells(plugin)
    assert (len(cells), len(cells[0])) == (8, 10)
    assert len(cells.layers) == 1 and is_full_frame_layer(cells.layers[0], 64, 64)


@pytest.mark.parametrize("endpoint", LEGACY_ENDPOINTS)
def test_a_legacy_flexible_page_send_names_the_primary_boards_device_type(
    client, pixoo_route_board, stub_expand, stub_refs, endpoint
):
    _, render = pixoo_route_board
    _send(client, endpoint, stored(red_band()).id)
    assert render.call_args.kwargs["device_type"] == "panel"


def test_batch_preview_of_a_flexible_page_on_an_led_board_is_its_full_frame(
    client, pixoo_route_board, stub_expand, stub_refs
):
    page_id = stored(red_band()).id
    response = client.post("/pages/preview/batch", json={"page_ids": [page_id], "board_id": PIXOO_8X10["id"]})
    preview = response.json()["previews"][page_id]
    assert preview["available"] and len(preview["lines"]) == 8


def test_current_display_for_flexible_page_returns_rendered_lines(client, stub_expand, stub_refs):
    get_settings_service().set_boards([NOTE_BOARD])
    page = stored(flex())
    get_settings_service().set_active_page_id(page.id)
    body = client.get("/pages/current-display").json()
    assert body["template"] == ["HI" + " " * 13, " " * 15, " " * 15]


def test_current_display_for_flexible_page_has_the_primary_boards_geometry(client, stub_expand, stub_refs):
    get_settings_service().set_boards([NOTE_BOARD])
    page = stored(flex())
    get_settings_service().set_active_page_id(page.id)
    body = client.get("/pages/current-display").json()
    assert body["device_type"] == "note"


def test_put_device_type_on_flexible_page_is_400(client):
    page = stored(flex())
    response = client.put(f"/pages/{page.id}", json={"device_type": "note"})
    assert (response.status_code, response.json()["detail"]) == (400, NO_GRID)


def test_put_renaming_a_flexible_page_reports_no_incompatible_references(client):
    page = stored(flex())
    response = client.put(f"/pages/{page.id}", json={"name": "Renamed"})
    assert response.status_code == 200 and response.json()["incompatible_references"] == []


# --- PageService ---------------------------------------------------------------


def test_a_geometry_update_to_a_flexible_page_is_refused():
    page = stored(flex())
    with pytest.raises(ValueError, match=NO_GRID):
        get_page_service().update_page(page.id, PageUpdate(grid_rows=8))


def test_flexible_render_never_reaches_the_grid_render_paths(stub_expand, stub_refs):
    service = PageService()
    refuse = AssertionError("a flexible page reached a grid render path")
    with (
        patch.object(PageService, "_render_template", side_effect=refuse),
        patch.object(PageService, "_render_composite", side_effect=refuse),
        patch.object(PageService, "_render_single", side_effect=refuse),
        patch.object(PageService, "_apply_canvases", side_effect=refuse),
        patch.object(PageService, "_board_for_page", side_effect=refuse),
    ):
        result = service.render_page(flex(), context={}, board=FLAGSHIP_BOARD)
    assert result.available


def test_delete_last_flexible_page_creates_flagship_welcome():
    page = stored(flex())
    result = get_page_service().delete_page(page.id)
    welcome = get_page_service().get_page(result.new_page_id)
    assert (welcome.type, welcome.device_type, welcome.name) == ("template", "flagship", "Welcome")


def test_deleting_the_legacy_active_flexible_page_activates_any_other_page():
    other = stored(grid_page("Note page", device_type="note"))
    page = stored(flex())
    settings = get_settings_service()
    settings.set_active_page_id(page.id)
    with patch.object(settings, "get_board_settings") as boards:
        boards.return_value.boards = []
        result = get_page_service().delete_page(page.id)
    assert result.new_active_page_id == other.id


# These scans swallow any error into "compatible", so each is pinned by the
# one flexible page that does NOT fit: one whose targets exclude the board.
LED_ONLY = {"technology": ["led_matrix"]}


def test_check_ref_board_compatibility_refuses_a_flexible_page_by_its_targets():
    get_settings_service().set_boards([NOTE_BOARD])
    page = stored(flex(targets=LED_ONLY))
    assert "This page is set to show only on LED displays" in check_ref_board_compatibility(page.id, "board-note").error


def test_a_flexible_page_is_an_incompatible_reference_only_where_its_targets_exclude_the_board():
    get_settings_service().set_boards([NOTE_BOARD])
    page = stored(flex(targets=LED_ONLY))
    get_settings_service().set_active_page_id(page.id, NOTE_BOARD["id"])
    assert [(r["board_id"], r["surface"]) for r in find_incompatible_references(page)] == [
        ("board-note", "active_page")
    ]


def test_a_boards_flexible_active_page_is_a_misfit_only_when_its_targets_exclude_the_board():
    get_settings_service().set_boards([NOTE_BOARD])
    page = stored(flex(targets=LED_ONLY))
    get_settings_service().set_active_page_id(page.id, NOTE_BOARD["id"])
    assert [r["page_id"] for r in find_incompatible_board_references(NOTE_BOARD)] == [page.id]


# --- fit, retarget, panel content resize, Fiestabot's prompt --------------------


def test_a_flexible_page_on_an_led_board_is_drawn_at_no_other_face(pixoo_output):
    assert page_fit_for_board(flex(), _board()) == PageFit(True, None, None)


def _note_array(notes_wide: int) -> dict:
    return {"id": "notes", "name": "Hall", "device_type": "note_array", "notes_wide": notes_wide, "notes_tall": 1}


def test_retarget_skips_flexible_pages():
    from src.pages.retarget import add_resize, retarget_pages

    flexible = stored(flex())
    stored(grid_page("Hall", device_type="note_array", notes_wide=2, notes_tall=1))
    resizes: dict = {}
    add_resize(resizes, _note_array(2), _note_array(3))
    moved = retarget_pages(resizes, {"note_array:3x45"})
    assert moved and all(m["page_id"] != flexible.id for m in moved)


def test_a_resize_never_leaves_a_flexible_page_behind():
    from src.pages.retarget import pages_left_behind

    stored(flex())
    left = pages_left_behind([(_note_array(2), _note_array(3))], set())
    assert left == []


def test_panel_content_resize_keeps_flexible_page_reference():
    from src.devices import DeviceDimensions
    from src.panels.content_resize import panel_content_resize

    settings = get_settings_service()
    tv = {"id": "tv", "name": "Living Room", "device_type": "panel", "output": "fiestapanel"}
    settings.set_boards([{**tv, "grid_rows": 12, "grid_cols": 29}])
    page = stored(flex())
    settings.set_active_page_id(page.id, board_id="tv")
    with panel_content_resize(settings.get_board_settings().boards[0], DeviceDimensions(13, 32), True) as summary:
        pass
    assert summary["page_copies"] == [] and settings.get_active_page_id("tv") == page.id


def test_prompt_builder_with_flexible_current_page_uses_board_geometry():
    from src.ai.prompt_builder import build_prompt

    current = flex().model_dump(mode="json")
    context = build_prompt("Improve this", "note", current_page=current)
    assert (context.rows, context.cols) == (3, 15)


# --- the ops layer (Fiestabot and MCP tools) -----------------------------------


def test_ops_update_page_renames_a_flexible_page_with_no_incompatible_references():
    from src.ops.executors import update_page

    page = get_page_service().create_page(
        PageCreate.model_validate(
            {"name": "Flex", "type": "flexible", "blocks": [{"id": "t", "kind": "text", "text": "HI"}]}
        )
    )
    result = update_page(page.id, name="Renamed", expected_revision=page.revision)
    assert result["status"] == "success" and result["incompatible_references"] == []
