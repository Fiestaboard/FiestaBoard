"""Display-targeted MCP previews use effective geometry unless explicitly overridden."""

from tests import test_led_board_layout as layout
from tests import test_mcp_state_effects as sibling
from tests.test_mcp_state_effects import call, call_expect_error

mcp = sibling.mcp
services = sibling.services
two_boards = sibling.two_boards
output_plugin = layout.output_plugin


def test_preview_uses_primary_pixel_display_geometry(mcp, services, two_boards, output_plugin):
    two_boards.set_boards([layout.PIXOO])
    result = call(mcp, "render_page_preview", template_lines=["hello"])
    assert result["device_type"] == "panel"
    assert (result["rows"], result["cols"]) == (10, 16)
    assert result["charset"] == "led_3x5"


def test_preview_can_explicitly_preview_a_different_page_geometry(mcp, services, two_boards, output_plugin):
    two_boards.set_boards([layout.PIXOO])
    result = call(mcp, "render_page_preview", template_lines=["hello"], device_type="note")
    assert (result["rows"], result["cols"]) == (3, 15)


def test_invalid_explicit_geometry_is_not_silently_flagship(mcp, services):
    message = call_expect_error(mcp, "render_page_preview", template_lines=["hello"], device_type="invalid")
    assert "geometry" in message


def test_canvas_validation_uses_primary_display_height(mcp, services, two_boards, output_plugin):
    two_boards.set_boards([layout.PIXOO])
    canvas = {"id": "art", "area": {"row": 11, "col": 1, "rows": 1, "cols": 1}, "content": {}}
    result = call(mcp, "validate_template", template=[""], canvases=[canvas])
    assert result["valid"] is False
    assert any(e.get("path") == "canvases[0].area" for e in result["errors"])


def test_invalid_canvas_structure_is_a_validation_result(mcp, services):
    result = call(mcp, "validate_template", template=[""], canvases=[{"id": "missing-area"}])
    assert result["valid"] is False
    assert any("area" in e.get("path", "") for e in result["errors"])
