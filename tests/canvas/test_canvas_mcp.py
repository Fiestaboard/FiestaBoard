"""MCP page tools speak canvases (design §6): create, update, read, preview, validate."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("mcp", reason="mcp package not installed")

from src.plugins.loader import PluginLoader

FIXTURE = Path(__file__).parents[1] / "fixtures" / "plugins" / "recording_output"
PLUGIN_ID = "recording_output"
PIXOO = {
    "id": "pixoo-1",
    "name": "Pixoo",
    "device_type": "panel",
    "grid_rows": 10,
    "grid_cols": 16,
    "output": PLUGIN_ID,
    "device_model": "divoom_pixoo64",
    "output_config": {"host": "192.0.2.50"},
}
HALL = {"id": "hall-1", "name": "Hall", "device_type": "flagship", "code62_glyph": "degree"}
CANVAS = {"id": "sun", "area": {"row": 1, "col": 1, "rows": 1, "cols": 2}, "content": {"background": "#ff0000"}}
PANEL = {"device_type": "panel", "grid_rows": 10, "grid_cols": 16}


def _call(mcp, tool, /, **kwargs):
    return mcp._tool_manager._tools[tool].fn(**kwargs)


def _error(mcp, tool, /, **kwargs) -> str:
    from mcp.server.mcpserver.exceptions import ToolError

    with pytest.raises(ToolError) as excinfo:
        _call(mcp, tool, **kwargs)
    return str(excinfo.value)


@pytest.fixture(scope="module")
def mcp():
    from src.mcp_server import _build_mcp_server

    return _build_mcp_server()


@pytest.fixture
def boards(tmp_path):
    """A pixel board (a Pixoo on an LED output) and a split-flap board."""
    from src.settings.service import get_settings_service

    root = tmp_path / "plugins"
    shutil.copytree(FIXTURE, root / PLUGIN_ID, ignore=shutil.ignore_patterns("__pycache__"))
    manifest_path = root / PLUGIN_ID / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["output"].pop("character_set")
    manifest_path.write_text(json.dumps(manifest), "utf-8")
    loader = PluginLoader(plugins_dir=root, external_dirs=[])
    assert loader.load_plugin(PLUGIN_ID) is not None, loader.load_errors
    get_settings_service().set_boards([HALL, PIXOO])
    yield
    loader.unload_plugin(PLUGIN_ID)


@pytest.fixture
def pages(tmp_path):
    from src.pages.service import PageService
    from src.pages.storage import PageStorage

    service = PageService(PageStorage(str(tmp_path / "pages.json")))
    with patch("src.pages.service.get_page_service", return_value=service):
        yield service


# --- create / update / get ------------------------------------------------------------------


def test_create_page_stores_the_canvases_it_is_given(mcp, pages):
    result = _call(mcp, "create_page", name="Sun", template_lines=["HELLO"], canvases=[CANVAS], **PANEL)
    stored = pages.get_page(result["page_id"])
    assert [c.id for c in stored.canvases] == ["sun"]


def test_create_page_refuses_an_invalid_canvas_and_says_why(mcp, pages):
    bad = {**CANVAS, "content": {"background": "sky blue"}}
    message = _error(mcp, "create_page", name="Sun", template_lines=["HELLO"], canvases=[bad], **PANEL)
    assert "not a colour" in message
    assert pages.list_pages() == []


def test_update_page_replaces_the_canvases(mcp, pages):
    page_id = _call(mcp, "create_page", name="Sun", template_lines=["HELLO"], canvases=[CANVAS], **PANEL)["page_id"]
    moon = {**CANVAS, "id": "moon"}
    _call(mcp, "update_page", page_id=page_id, canvases=[moon])
    assert [c.id for c in pages.get_page(page_id).canvases] == ["moon"]


def test_update_page_with_an_empty_list_removes_every_canvas(mcp, pages):
    page_id = _call(mcp, "create_page", name="Sun", template_lines=["HELLO"], canvases=[CANVAS], **PANEL)["page_id"]
    _call(mcp, "update_page", page_id=page_id, canvases=[])
    assert not pages.get_page(page_id).canvases


def test_update_page_without_canvases_leaves_them_alone(mcp, pages):
    page_id = _call(mcp, "create_page", name="Sun", template_lines=["HELLO"], canvases=[CANVAS], **PANEL)["page_id"]
    _call(mcp, "update_page", page_id=page_id, name="Renamed")
    assert [c.id for c in pages.get_page(page_id).canvases] == ["sun"]


def test_get_page_returns_canvases_in_their_json_form(mcp, pages):
    shape = {"type": "rect", "x": 0, "y": 0, "w": 2, "h": 2, "fill": "red", "if": "{{= 1 }}"}
    canvas = {**CANVAS, "content": {"shapes": [shape]}}
    page_id = _call(mcp, "create_page", name="Sun", template_lines=["HELLO"], canvases=[canvas], **PANEL)["page_id"]
    got = _call(mcp, "get_page", page_id=page_id)["canvases"][0]["content"]["shapes"][0]
    assert got["if"] == "{{= 1 }}" and "if_" not in got


# --- render_page_preview ---------------------------------------------------------------------


def test_render_page_preview_for_a_pixel_board_summarises_the_layers(mcp, boards):
    result = _call(mcp, "render_page_preview", template_lines=["HELLO"], canvases=[CANVAS], board_id="pixoo-1", **PANEL)
    assert result["layer_count"] == 1
    assert set(result["layers"][0]) == {"x", "y", "width", "height"}
    assert result["canvas_issues"] == []


def test_render_page_preview_includes_the_pixels_only_when_asked(mcp, boards):
    result = _call(
        mcp,
        "render_page_preview",
        template_lines=["HELLO"],
        canvases=[CANVAS],
        board_id="pixoo-1",
        include_layer_pixels=True,
        **PANEL,
    )
    assert set(result["layers"][0]) == {"x", "y", "width", "height", "rgba"}


def test_render_page_preview_reports_canvas_issues(mcp, boards):
    sourced = {**CANVAS, "source": "{{= 5 }}"}
    result = _call(
        mcp, "render_page_preview", template_lines=["HELLO"], canvases=[sourced], board_id="pixoo-1", **PANEL
    )
    assert [(i["canvas_id"], i["path"]) for i in result["canvas_issues"]] == [("sun", "source")]


def test_render_page_preview_blanks_text_under_a_canvas_on_any_board(mcp, boards):
    result = _call(mcp, "render_page_preview", template_lines=["HELLO"], canvases=[CANVAS], board_id="hall-1")
    assert result["rendered"].split("\n")[0].startswith("  LLO")
    assert result["layers"] is None


def test_render_page_preview_refuses_invalid_canvases(mcp):
    message = _error(mcp, "render_page_preview", template_lines=["HELLO"], canvases=[{**CANVAS, "scale": 99}], **PANEL)
    assert "scale" in message


# --- validate_template ----------------------------------------------------------------------


def test_validate_template_accepts_valid_canvases(mcp):
    result = _call(mcp, "validate_template", template=["HELLO"], canvases=[CANVAS])
    assert result["valid"] is True and result["errors"] == []


def test_validate_template_reports_a_bad_canvas_with_its_path(mcp):
    bad = {**CANVAS, "content": {"shapes": [{"type": "rect", "x": 0, "y": 0, "w": 1, "h": 1, "fill": "sky"}]}}
    result = _call(mcp, "validate_template", template=["HELLO"], canvases=[bad])
    assert result["valid"] is False
    [error] = result["errors"]
    assert error["path"] == "canvases[0].content.shapes[0].fill"
    assert "not a colour" in error["message"]


def test_validate_template_reports_an_area_that_starts_off_the_grid(mcp):
    off = {**CANVAS, "area": {"row": 7, "col": 1, "rows": 1, "cols": 1}}
    result = _call(mcp, "validate_template", template=["HELLO"], canvases=[off])
    assert result["valid"] is False
    assert result["errors"][0]["path"] == "canvases[0].area"
