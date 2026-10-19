"""Built-in display descriptions teach only what their actual output delivers."""

from __future__ import annotations

import pytest

from src.outputs.display_profile import display_profile_for_board, display_profile_for_client
from tests import test_mcp_state_effects as sibling
from tests.test_mcp_state_effects import call

mcp = sibling.mcp
services = sibling.services


@pytest.fixture(params=["split_flap", "led_matrix"])
def panel_board(request, tmp_path, monkeypatch):
    from src.panels.models import PanelCreate, PanelUpdate
    from src.panels.service import PanelService
    from src.panels.storage import PanelStorage
    from src.settings.service import SettingsService

    panels = PanelService(PanelStorage(str(tmp_path / "panels.json")))
    panel = panels.create_panel(PanelCreate(name="Viewer"), board_id="builtin-panel")
    panels.update_panel(panel.id, PanelUpdate(render_style=request.param))
    monkeypatch.setattr("src.panels.service._panel_service", panels)
    settings = SettingsService(settings_file=str(tmp_path / "settings.json"))
    settings.set_boards(
        [
            {
                "id": "builtin-panel",
                "name": "Viewer",
                "output": "fiestapanel",
                "api_mode": "virtual",
                "device_type": "panel",
                "grid_rows": 6,
                "grid_cols": 22,
                "code62_glyph": "heart",
                "output_config": {},
            }
        ]
    )
    monkeypatch.setattr("src.settings.service._settings_service", settings)
    return settings.get_board_settings().boards[0]


def test_builtin_panel_profile_matches_the_integer_writer(panel_board):
    from src.outputs.registry import output_registry

    profile = display_profile_for_board(panel_board)
    assert profile is not None
    assert profile.charset == "vestaboard_v2"
    assert not any(
        profile.supports(feature) for feature in ("pixels", "lowercase", "color_text", "background", "icons", "rgb")
    )
    assert profile.supports("tiles")
    assert (profile.rows, profile.cols) == (6, 22)
    client = output_registry().get("fiestapanel").build(panel_board)
    try:
        assert client.character_set is None  # The existing integer delivery contract.
        assert display_profile_for_client(client) == profile
    finally:
        client.close()


def test_builtin_discovery_preview_and_ai_share_authoring_support(mcp, services, panel_board):
    from src.ai.page_routes import _display_for_board
    from src.ai.prompt_builder import build_prompt
    from src.templates.routes import _CharsetCheck

    profile = display_profile_for_board(panel_board)
    info = call(mcp, "get_display_info", board_id=panel_board["id"])
    assert info["display"] == profile.to_dict()
    assert info["charset"] == profile.charset
    check = _CharsetCheck(panel_board["id"])
    assert check.display == profile
    assert check.charset == profile.character_set
    assert check.result("a")["charset_issues"][0]["fallback"]["value"] == "A"
    preview = call(
        mcp,
        "render_page_preview",
        board_id=panel_board["id"],
        template_lines=["HELLO"],
        canvases=[
            {
                "id": "art",
                "area": {"row": 1, "col": 1, "rows": 1, "cols": 1},
                "content": {"background": "#ff0000"},
            }
        ],
    )
    assert preview.get("layer_count", 0) == 0
    # Existing page semantics reserve canvas cells on every display; the
    # integer-only panel must not claim to draw a bitmap in that space.
    assert preview["rendered"].split("\n")[0].startswith(" ELLO")
    assert preview["layers"] is None
    prompt = build_prompt("Improve", "panel", mode="chat", display=_display_for_board(panel_board["id"])).system_prompt
    assert "PIXEL CANVASES" not in prompt
    assert "Coloured text:" not in prompt
