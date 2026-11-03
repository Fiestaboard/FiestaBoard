"""Fiestabot (MCP tools and the ops layer) never reports a flexible page as a 6x22 flagship page.

A flexible page still carries the grid fields' defaults on the model object
(only ``model_dump`` strips them), so reading ``page.device_type`` directly
answers ``flagship``. Every surface answers the layout board's geometry
instead, as ``GET /pages/current-display`` does.
"""

from __future__ import annotations

import pytest

from src.devices import page_geometry_fields
from src.pages.models import Page, PageCreate
from src.settings.service import get_settings_service
from tests.canvas import test_canvas_mcp as canvas_fixtures
from tests.canvas.test_canvas_mcp import HALL, PIXOO, _call
from tests.layout.test_engine import stub_expand  # noqa: F401
from tests.layout.test_flexible_render import stub_refs  # noqa: F401

pytest.importorskip("mcp", reason="mcp package not installed")

mcp = canvas_fixtures.mcp
boards = canvas_fixtures.boards
pages = canvas_fixtures.pages

FLEX = {"name": "Flex", "type": "flexible", "blocks": [{"id": "t", "kind": "text", "text": "HI"}]}
HALL_GEOMETRY = {"device_type": "flagship", "notes_wide": 1, "notes_tall": 1, "grid_rows": None, "grid_cols": None}
PIXOO_GEOMETRY = {"device_type": "panel", "notes_wide": 1, "notes_tall": 1, "grid_rows": 10, "grid_cols": 16}


@pytest.fixture
def pixoo_primary(boards):
    get_settings_service().set_boards([PIXOO, HALL])


def _flex_page(pages) -> Page:
    return pages.create_page(PageCreate.model_validate(FLEX))


# --- the helper ----------------------------------------------------------------


def test_page_geometry_fields_of_a_flexible_page_is_the_boards():
    assert page_geometry_fields(Page.model_validate(FLEX), PIXOO) == PIXOO_GEOMETRY


def test_page_geometry_fields_of_a_flexible_page_defaults_to_the_primary_board(pixoo_primary):
    assert page_geometry_fields(Page.model_validate(FLEX)) == PIXOO_GEOMETRY


def test_page_geometry_fields_of_a_grid_page_is_its_own():
    page = Page(name="G", type="template", device_type="note", template=["X"])
    assert page_geometry_fields(page, PIXOO) == {
        "device_type": "note",
        "notes_wide": 1,
        "notes_tall": 1,
        "grid_rows": None,
        "grid_cols": None,
    }


# --- MCP tools -----------------------------------------------------------------


@pytest.mark.usefixtures("stub_expand", "stub_refs")
def test_mcp_get_current_display_of_a_flexible_page_on_a_pixoo_has_the_pixoos_geometry(mcp, pixoo_primary, pages):
    page = _flex_page(pages)
    settings = get_settings_service()
    settings.set_schedule_enabled(False, board_id="pixoo-1")
    settings.set_active_page_id(page.id, board_id="pixoo-1")
    current = _call(mcp, "get_current_display", board_id="pixoo-1")
    assert current["page_id"] == page.id
    assert {key: current[key] for key in PIXOO_GEOMETRY} == PIXOO_GEOMETRY


def test_mcp_get_active_page_of_a_flexible_page_on_a_pixoo_is_not_flagship(mcp, pixoo_primary, pages):
    page = _flex_page(pages)
    settings = get_settings_service()
    settings.set_schedule_enabled(False, board_id="pixoo-1")
    settings.set_active_page_id(page.id, board_id="pixoo-1")
    active = _call(mcp, "get_active_page", board_id="pixoo-1")
    assert active["page"]["id"] == page.id
    assert active["page"]["device_type"] == "panel"


@pytest.mark.usefixtures("stub_expand", "stub_refs")
def test_mcp_get_current_display_of_a_flexible_page_on_a_secondary_board_has_that_boards_geometry(
    mcp, pixoo_primary, pages
):
    page = _flex_page(pages)
    settings = get_settings_service()
    settings.set_schedule_enabled(False, board_id="hall-1")
    settings.set_active_page_id(page.id, board_id="hall-1")
    current = _call(mcp, "get_current_display", board_id="hall-1")
    assert current["page_id"] == page.id
    assert {key: current[key] for key in HALL_GEOMETRY} == HALL_GEOMETRY
    assert len(current["template"]) == 6  # laid out at the flagship's 6 rows, not the Pixoo's 10


def test_mcp_get_active_page_of_a_flexible_page_on_a_secondary_board_has_that_boards_device_type(
    mcp, pixoo_primary, pages
):
    page = _flex_page(pages)
    settings = get_settings_service()
    settings.set_schedule_enabled(False, board_id="hall-1")
    settings.set_active_page_id(page.id, board_id="hall-1")
    active = _call(mcp, "get_active_page", board_id="hall-1")
    assert active["page"]["device_type"] == "flagship"


@pytest.mark.usefixtures("stub_expand", "stub_refs")
def test_mcp_preview_saved_page_of_a_flexible_page_is_not_flagship(mcp, pixoo_primary, pages):
    page = _flex_page(pages)
    assert _call(mcp, "preview_saved_page", page_id=page.id)["device_type"] == "panel"


def test_mcp_export_page_of_a_flexible_page_is_not_flagship(mcp, pixoo_primary, pages):
    page = _flex_page(pages)
    assert _call(mcp, "export_page", page_id=page.id)["device_type"] == "panel"


@pytest.mark.asyncio
async def test_mcp_pages_resource_lists_a_flexible_page_without_flagship(mcp, pixoo_primary, pages):
    _flex_page(pages)
    resources = list(await mcp.read_resource("fiestaboard://pages"))
    listing = resources[0].content
    assert "flexible, panel" in listing and "flagship" not in listing


# --- the ops layer -------------------------------------------------------------


def test_ops_import_of_a_flexible_page_does_not_report_flagship(pixoo_primary, pages):
    from src.ops.executors import import_page
    from src.pages.share import encode_page

    result = import_page(encode_page(Page.model_validate(FLEX)))
    assert result["status"] == "success"
    assert result["device_type"] == "panel"


def test_ops_update_of_a_flexible_page_does_not_report_flagship(pixoo_primary, pages):
    from src.ops.executors import update_page

    page = _flex_page(pages)
    result = update_page(page.id, name="Renamed", expected_revision=page.revision)
    assert result["status"] == "success"
    assert result["device_type"] == "panel"


def test_ops_create_of_a_grid_page_still_reports_its_own_device_type(pixoo_primary, pages):
    from src.ops.executors import create_page

    result = create_page(name="Grid", template_lines=["HI"], device_type="note")
    assert result["status"] == "success"
    assert result["device_type"] == "note"
