"""Offline regression contracts for the MCP display and plugin audit."""

from types import SimpleNamespace

from src.led.charsets import resolve_character_set
from src.outputs.cells import project_message
from src.outputs.display_profile import display_profile_for_board
from tests import test_led_board_layout as layout
from tests import test_mcp_state_effects as sibling
from tests.test_mcp_state_effects import call

mcp = sibling.mcp
services = sibling.services
two_boards = sibling.two_boards
engine = sibling.engine
output_plugin = layout.output_plugin


def test_summary_identifies_the_led_pixel_display(mcp, two_boards, output_plugin):
    two_boards.set_boards([layout.HALL, layout.PIXOO])
    profile = display_profile_for_board(two_boards.get_board_settings().boards[1])
    assert profile is not None and profile.supports("pixels")
    assert (profile.width, profile.height) == (64, 64)

    board = next(b for b in call(mcp, "get_settings_summary")["boards"] if b["id"] == "pixoo-1")
    assert board.get("output") == "recording_output", board
    assert board.get("device_model") == "divoom_pixoo64", board
    assert board.get("charset") == "led_3x5", board


def test_summary_recognizes_configured_plugin_host_and_credentials(mcp, two_boards, output_plugin):
    pixoo = {**layout.PIXOO, "output_config": {"host": "192.0.2.50", "token": "audit-secret"}}
    two_boards.set_boards([layout.HALL, pixoo])
    board = next(b for b in call(mcp, "get_settings_summary")["boards"] if b["id"] == "pixoo-1")
    assert board["has_host"] is True, board
    assert board["has_credentials"] is True, board
    assert "audit-secret" not in str(board)


def test_detect_size_accepts_a_valid_12_by_29_fiestapanel(mcp, two_boards, monkeypatch):
    from src.devices import dimensions_of

    panel = {
        "id": "matrix-panel",
        "name": "Matrix",
        "output": "fiestapanel",
        "device_type": "panel",
        "grid_rows": 12,
        "grid_cols": 29,
        "output_config": {},
    }
    two_boards.set_boards([panel])
    assert dimensions_of(two_boards.get_board_settings().boards[0]) == (12, 29)
    probe = SimpleNamespace(read_current_message=lambda: [[0] * 29 for _ in range(12)])
    monkeypatch.setattr("src.settings.routes._live_board_driver", lambda board_id: probe)
    result = call(mcp, "detect_board_size", board_id="matrix-panel")
    assert (result["rows"], result["cols"]) == (12, 29)


def test_board_content_keeps_the_led_cells_it_already_has(mcp, engine):
    from src.board_state import read_board_state

    frame = project_message("{red:hello} {icon:sun}", 6, 22, resolve_character_set("led_3x5"))
    runtime = engine.runtimes["board-main"]
    runtime.output.frames.record_sent(frame.characters, cells=frame.cells)
    state = read_board_state("board-main", want="board", service=engine)
    assert state.cells is not None and state.cells[0][0].value == "h"

    result = call(mcp, "get_board_content", board_id="board-main")
    assert "hello" in result["message"] or result.get("cells"), result


def test_update_board_does_not_report_success_for_an_ignored_host_edit(mcp, two_boards, output_plugin, monkeypatch):
    two_boards.set_boards([layout.HALL, layout.PIXOO])
    monkeypatch.setattr("src.settings.routes.reinitialize_board_clients", lambda: None)

    result = call(mcp, "update_board", board_id="pixoo-1", host="192.0.2.99")
    stored = next(b for b in two_boards.get_board_settings().boards if b["id"] == "pixoo-1")
    assert result["status"] != "success" or stored["output_config"]["host"] == "192.0.2.99", (result, stored)


def test_update_board_reports_when_a_resize_breaks_the_active_page(mcp, services, two_boards, monkeypatch):
    from src.pages.service import find_incompatible_board_references

    monkeypatch.setattr("src.settings.routes.reinitialize_board_clients", lambda: None)
    created = call(mcp, "create_page", name="Main", template_lines=["hello"] * 6, device_type="flagship")
    two_boards.set_active_page_id(created["page_id"], board_id="board-main")

    result = call(mcp, "update_board", board_id="board-main", device_type="note")
    board = next(b for b in two_boards.get_board_settings().boards if b["id"] == "board-main")
    warnings = find_incompatible_board_references(board)
    assert any(ref["page_id"] == created["page_id"] for ref in warnings)
    assert result.get("incompatible_references"), result


def test_send_message_itself_preserves_led_lowercase_colors_and_icons(mcp, engine):
    engine.vb_client.character_set = resolve_character_set("led_3x5")
    result = call(mcp, "send_message", text="{red:hello} {icon:sun}")
    assert result["status"] == "success", result
    cells = engine.vb_client.render_kwargs[-1]["cells"]
    assert cells[0][0].value == "h" and cells[0][0].color == "red"
    assert cells[0][6].icon == "sun"


def test_omitted_preview_target_uses_the_primary_led_character_set(mcp, two_boards, output_plugin):
    two_boards.set_boards([layout.PIXOO])
    geometry = {"device_type": "panel", "grid_rows": 10, "grid_cols": 16}
    explicit = call(mcp, "render_page_preview", template_lines=["{red:hello}"], board_id="pixoo-1", **geometry)
    implicit = call(mcp, "render_page_preview", template_lines=["{red:hello}"], **geometry)
    assert explicit["charset"] == "led_3x5"
    assert implicit.get("charset") == explicit["charset"], implicit
