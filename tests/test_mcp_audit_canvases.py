"""Isolated audit reproductions; writes only reach an in-memory recording output."""

from unittest.mock import patch

import pytest

from tests.canvas import test_canvas_mcp as canvas_fixtures
from tests.canvas.test_canvas_mcp import CANVAS, PANEL, _call

mcp = canvas_fixtures.mcp
boards = canvas_fixtures.boards
pages = canvas_fixtures.pages


def test_saved_pixel_preview_exposes_the_same_canvas_layers_as_unsaved(mcp, boards, pages):
    page_id = _call(mcp, "create_page", name="Art", template_lines=["HELLO"], canvases=[CANVAS], **PANEL)["page_id"]
    unsaved = _call(
        mcp, "render_page_preview", template_lines=["HELLO"], canvases=[CANVAS], board_id="pixoo-1", **PANEL
    )
    saved = _call(mcp, "preview_saved_page", page_id=page_id, board_id="pixoo-1")
    assert unsaved["layer_count"] == 1
    assert saved.get("layer_count") == 1


def test_saved_pixel_preview_supplies_the_board_to_plugins(mcp, boards, pages):
    from src.templates.engine import get_template_engine

    page_id = _call(mcp, "create_page", name="Art", template_lines=["HELLO"], canvases=[CANVAS], **PANEL)["page_id"]
    engine = get_template_engine()
    with patch.object(engine, "_build_context", return_value={}) as build:
        _call(mcp, "preview_saved_page", page_id=page_id, board_id="pixoo-1")
    board_context = build.call_args.args[0]
    assert board_context.display is not None
    assert board_context.display.supports("pixels")


def test_unsaved_preview_only_fetches_plugins_its_content_references(mcp):
    from src.templates.engine import get_template_engine

    engine = get_template_engine()
    with patch.object(engine, "_build_context", return_value={}) as build:
        _call(mcp, "render_page_preview", template_lines=["HELLO"])
    assert build.call_args.kwargs.get("plugin_ids") == set()


def test_validate_canvases_rejects_malformed_shape_expressions(mcp, boards):
    canvas = {
        **CANVAS,
        "content": {"shapes": [{"type": "rect", "x": "{{= 1 + }}", "y": 0, "w": 1, "h": 1, "fill": "red"}]},
    }
    result = _call(mcp, "validate_template", template=[""], canvases=[canvas])
    preview = _call(mcp, "render_page_preview", template_lines=[""], canvases=[canvas], board_id="pixoo-1", **PANEL)
    assert preview["canvas_issues"][0]["path"] == "shapes[0].x"
    assert "#SYNTAX" in preview["canvas_issues"][0]["message"]
    assert result["valid"] is False


def test_validate_note_array_canvases_rejects_rows_outside_default_height(mcp, pages):
    from mcp.server.mcpserver.exceptions import ToolError

    canvas = {**CANVAS, "area": {"row": 4, "col": 1, "rows": 1, "cols": 1}}
    result = _call(mcp, "validate_template", template=[""], device_type="note_array", canvases=[canvas])
    with pytest.raises(ToolError, match="outside"):
        _call(mcp, "create_page", name="Bad", template_lines=[""], device_type="note_array", canvases=[canvas])
    assert result["valid"] is False


def test_html_preview_uses_the_saved_panel_geometry(mcp, pages):
    from src.board_html_renderer import render_page_preview_html

    page_id = _call(mcp, "create_page", name="Panel", template_lines=["HELLO"], **PANEL)["page_id"]
    preview = render_page_preview_html(pages.get_page(page_id))
    assert preview.count('class="row"') == PANEL["grid_rows"]
    assert preview.count('class="tile"') == PANEL["grid_rows"] * PANEL["grid_cols"]


def test_html_preview_does_not_draw_extended_markup_as_literal_characters(mcp, pages):
    from src.board_html_renderer import render_page_preview_html

    page_id = _call(mcp, "create_page", name="Colored", template_lines=["{{red:HOT}}"])["page_id"]
    preview = render_page_preview_html(pages.get_page(page_id))
    assert ">{</span>" not in preview
    assert ">}</span>" not in preview


def test_current_display_returns_canvases_needed_to_start_a_new_page(mcp, boards, pages):
    from src.settings.service import get_settings_service

    page_id = _call(mcp, "create_page", name="Art", template_lines=["HELLO"], canvases=[CANVAS], **PANEL)["page_id"]
    settings = get_settings_service()
    settings.set_schedule_enabled(False, board_id="pixoo-1")
    settings.set_active_page_id(page_id, board_id="pixoo-1")
    current = _call(mcp, "get_current_display", board_id="pixoo-1")
    assert current["page_id"] == page_id
    assert current.get("canvases") == pages.get_page(page_id).model_dump()["canvases"]


@pytest.mark.asyncio
async def test_selecting_canvas_page_delivers_art_on_the_first_write(mcp, boards, pages, monkeypatch):
    from src.led import LedMatrixSpec, layout_message, rasterize
    from src.outputs.display_profile import display_profile_for_client
    from src.plugins import WriteResult
    from tests.canvas.test_canvas_mcp import PIXOO
    from tests.live_boards import install_live_boards

    service = install_live_boards([PIXOO])
    driver = service.get_board_client("pixoo-1")
    profile = display_profile_for_client(driver)
    assert profile.supports("pixels")
    delivered = []

    def write_cells(_self, cells, *, native, cancel):
        spec = LedMatrixSpec(profile.width, profile.height, profile.font)
        delivered.append(rasterize(layout_message(cells, spec, layers=getattr(cells, "layers", ()))).pixels)
        return WriteResult(True, True)

    monkeypatch.setattr(type(driver.plugin), "write_cells", write_cells)
    monkeypatch.setattr("src.settings.routes.get_page_service", lambda: pages)
    monkeypatch.setattr("src.main.get_page_service", lambda: pages)
    canvas = {**CANVAS, "area": {"row": 1, "col": 1, "rows": 10, "cols": 16}, "bleed": ["all"]}
    page_id = _call(mcp, "create_page", name="Red", template_lines=[""], canvases=[canvas], **PANEL)["page_id"]
    response = await mcp._tool_manager._tools["set_active_page"].fn(page_id=page_id, board_id="pixoo-1")
    assert response["sent_to_board"] is True
    assert len(delivered) == 1
    first = delivered[0]
    assert service.take_wake() is True
    # Drive precisely the pass wake() requests, without starting a background loop.
    service.check_and_send_active_page()
    assert len(delivered) == 2
    expected = bytes([255, 0, 0]) * (profile.width * profile.height)
    assert delivered[1] == expected
    assert first == expected
