"""Panel lifecycle and runtime models agree with the authoring geometry."""

import pytest
from fastapi.testclient import TestClient

from src.outputs.board_profile import board_character_set, board_led_layout, board_model_spec, board_profile
from src.panels.models import Panel
from src.panels.reconcile import reconcile_panel_boards
from src.panels.service import get_panel_service
from src.settings.service import get_settings_service


@pytest.fixture
def api():
    from src.api_server import app

    return TestClient(app)


def board_for(panel):
    return next(b for b in get_settings_service().get_board_settings().boards if b["id"] == panel["board_id"])


def test_create_led_panel_uses_screen_pixels_everywhere(api):
    response = api.post("/panels", json={"name": "LED", "render_style": "led_matrix", "matrix_font": "3x5"})
    assert response.status_code == 201, response.text
    panel = response.json()
    assert (panel["rows"], panel["cols"]) == (18, 48)
    public = api.get(f"/panel/{panel['id']}").json()
    board = board_for(panel)
    model = board_model_spec(board)
    assert model == public["device_model_spec"]
    assert model["geometry"] == {"kind": "pixels", "width": 192, "height": 108}
    assert board_profile(board).charset == "led_3x5"
    assert board_character_set(board)["id"] == "led_3x5"
    assert board_led_layout(board)["font"] == "3x5"
    assert api.get(f"/panel/{panel['id']}/frame").json()["geometry_key"] == public["geometry_key"]
    assert reconcile_panel_boards() == 0


def test_new_panel_switches_sizing_policies_on_style_change(api):
    p = api.post("/panels", json={"name": "TV"}).json()
    assert (p["rows"], p["cols"]) == (12, 29)
    p = api.patch(f"/panels/{p['id']}", json={"render_style": "led_matrix"}).json()
    assert (p["rows"], p["cols"]) == (13, 32)
    p = api.patch(f"/panels/{p['id']}", json={"screen_diagonal_inches": 85}).json()
    assert (p["rows"], p["cols"]) == (13, 32)
    p = api.patch(f"/panels/{p['id']}", json={"render_style": "split_flap"}).json()
    assert (p["rows"], p["cols"]) == (18, 45)


def test_legacy_led_panel_does_not_resize_on_restart_or_cosmetic_save(api):
    settings = get_settings_service()
    settings.add_board({"id": "old", "device_type": "panel", "api_mode": "virtual", "grid_rows": 12, "grid_cols": 29})
    p = get_panel_service().storage.create(Panel(name="Old", board_id="old", render_style="led_matrix"))
    assert reconcile_panel_boards() == 0
    response = api.patch(f"/panels/{p.id}", json={"name": "Renamed", "screen_diagonal_inches": 85})
    assert response.status_code == 200
    assert (response.json()["rows"], response.json()["cols"]) == (12, 29)
    public = api.get(f"/panel/{p.id}").json()
    assert public["device_model_spec"]["geometry"] == {"kind": "pixels", "width": 174, "height": 96}


def test_draft_and_save_use_same_geometry_without_mutating_draft(api):
    p = api.post("/panels", json={"name": "TV"}).json()
    draft = {
        "panel_id": p["id"],
        "render_style": "led_matrix",
        "matrix_layout": "screen",
        "screen_aspect_w": 9,
        "screen_aspect_h": 16,
    }
    response = api.post("/panels/geometry", json=draft)
    assert response.status_code == 200, response.text
    assert (response.json()["rows"], response.json()["cols"]) == (24, 18)
    assert api.get(f"/panel/{p['id']}").json()["render_style"] == "split_flap"
    saved = api.patch(f"/panels/{p['id']}", json={k: v for k, v in draft.items() if k != "panel_id"})
    assert saved.status_code == 200, saved.text
    public = api.get(f"/panel/{p['id']}").json()
    assert response.json()["device_model_spec"] == public["device_model_spec"]
    assert response.json()["geometry_key"] == public["geometry_key"]


def test_invalid_prospective_geometry_does_not_change_panel_or_board(api):
    p = api.post("/panels", json={"name": "TV"}).json()
    before = api.get(f"/panel/{p['id']}").json()
    board = board_for(p)
    response = api.patch(
        f"/panels/{p['id']}", json={"render_style": "led_matrix", "screen_aspect_w": 100, "screen_aspect_h": 1}
    )
    assert response.status_code == 422
    assert api.get(f"/panel/{p['id']}").json() == before
    assert board_for(p) == board


def test_conversion_copies_referenced_content_and_keeps_original(api):
    from src.pages.service import get_page_service

    p = api.post("/panels", json={"name": "TV"}).json()
    original = api.post(
        "/pages",
        json={
            "name": "Shared page",
            "type": "template",
            "device_type": "panel",
            "grid_rows": 12,
            "grid_cols": 29,
            "template": ["          RIGHT"],
            "canvases": [
                {
                    "id": "portrait",
                    "area": {"row": 1, "col": 1, "rows": 9, "cols": 9},
                    "content": {"background": "#ff0000"},
                }
            ],
        },
    ).json()
    pages = get_page_service().storage
    before = pages.get(original["id"]).model_dump(mode="json")
    settings = get_settings_service()
    settings.set_active_page_id(original["id"], board_id=p["board_id"])
    response = api.patch(f"/panels/{p['id']}", json={"render_style": "led_matrix", "copy_content": True})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["matrix_sizing"] == "fill_tv"
    assert len(result["content_copies"]["page_copies"]) == 1
    copy_id = result["content_copies"]["page_copies"][0]["to_id"]
    copied = pages.get(copy_id)
    assert (copied.grid_rows, copied.grid_cols) == (13, 32)
    assert copied.canvases == pages.get(original["id"]).canvases
    assert settings.get_active_page_id(p["board_id"]) == copy_id
    assert pages.get(original["id"]).model_dump(mode="json") == before


@pytest.mark.parametrize("copy_content", [False, True])
def test_failed_geometry_save_restores_exact_panel_and_board(api, monkeypatch, copy_content):
    p = api.post("/panels", json={"name": "TV"}).json()
    panels = get_panel_service()
    before_panel = panels.get_panel(p["id"]).model_dump()
    before_board = dict(board_for(p))
    from src.display_runtime import get_service

    characters = [[1] * p["cols"] for _ in range(p["rows"])]
    get_service().get_runtime(p["board_id"]).output.frames.record_sent(characters)
    settings = get_settings_service()
    save = settings.set_boards
    attempts = 0

    def fail_once(boards):
        nonlocal attempts
        attempts += 1
        save(boards)  # Also exercise a failure after in-memory and disk mutation.
        if attempts == 1:
            raise OSError("injected save failure")

    monkeypatch.setattr(settings, "set_boards", fail_once)
    response = api.patch(f"/panels/{p['id']}", json={"render_style": "led_matrix", "copy_content": copy_content})
    assert response.status_code >= 500, (response.status_code, response.text, attempts)
    assert panels.get_panel(p["id"]).model_dump() == before_panel
    assert board_for(p) == before_board
    assert api.get(f"/panel/{p['id']}/frame").json()["characters"] == characters


def test_oversized_legacy_grid_reports_actionable_error_and_can_convert(api):
    settings = get_settings_service()
    settings.add_board(
        {"id": "large-old", "device_type": "panel", "api_mode": "virtual", "grid_rows": 18, "grid_cols": 45}
    )
    p = get_panel_service().storage.create(Panel(name="Old 85 inch", board_id="large-old", render_style="led_matrix"))
    public = api.get(f"/panel/{p.id}").json()
    assert "256" in public["geometry_error"]
    assert (public["rows"], public["cols"]) == (18, 45)
    response = api.patch(f"/panels/{p.id}", json={"matrix_layout": "screen"})
    assert response.status_code == 200, response.text
    public = api.get(f"/panel/{p.id}").json()
    assert public["geometry_error"] is None
    assert (public["rows"], public["cols"]) == (13, 32)


def test_same_cell_grid_conversion_rebuilds_pixel_runtime_and_caches(api):
    from tests.live_boards import install_live_boards

    board = {"id": "same-grid", "device_type": "panel", "api_mode": "virtual", "grid_rows": 13, "grid_cols": 32}
    panel = get_panel_service().storage.create(Panel(name="Legacy", board_id=board["id"], render_style="led_matrix"))
    service = install_live_boards([board])
    old = service.get_runtime(board["id"])
    old.last_active_page_content = "cached content"
    old.last_render = ("fingerprint", "cached content", "page")
    assert api.get(f"/panel/{panel.id}").json()["device_model_spec"]["geometry"]["height"] == 104
    response = api.patch(f"/panels/{panel.id}", json={"matrix_layout": "screen"})
    assert response.status_code == 200
    new = service.get_runtime(board["id"])
    assert new is not old
    assert new.last_active_page_content is None
    assert new.last_render is None
    assert api.get(f"/panel/{panel.id}").json()["device_model_spec"]["geometry"]["height"] == 108


def test_layout_and_display_role_changes_do_not_share_a_partial_transaction(api):
    first = api.post("/panels", json={"name": "First"}).json()
    second = api.post("/panels", json={"name": "Second"}).json()
    api.patch(f"/panels/{first['id']}", json={"is_display": True}).raise_for_status()
    response = api.patch(
        f"/panels/{second['id']}", json={"render_style": "led_matrix", "is_display": True, "copy_content": True}
    )
    assert response.status_code == 422
    assert get_panel_service().get_panel(first["id"]).is_display is True
    assert get_panel_service().get_panel(second["id"]).render_style == "split_flap"
