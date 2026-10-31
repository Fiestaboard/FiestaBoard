"""Flexible pixel pages must not silently lose their full-frame layer."""

# ruff: noqa: F811

from unittest.mock import Mock

import pytest

from src.devices import dimensions_of
from src.main import _project_page
from src.outputs.display_profile import render_kw
from src.outputs.plugin_base import OutputPluginBase
from src.pages.fit import PageFit
from src.pages.service import get_page_service
from tests.layout.test_flexible_call_sites import red_band, stored
from tests.test_led_text_size import pixoo_output  # noqa: F401
from tests.test_routes_page_face import BOARD, Sign
from tests.test_routes_page_face import board as pixel_board  # noqa: F401
from tests.test_v1_contract import client  # noqa: F401


@pytest.mark.parametrize("route", ["legacy", "v1"])
def test_pixel_page_refuses_an_output_without_a_rich_frame_writer(client, pixel_board, monkeypatch, route):
    plugin, _ = pixel_board
    monkeypatch.setattr(Sign, "write_cells", OutputPluginBase.write_cells)
    page = stored(red_band())
    if route == "legacy":
        response = client.post(f"/pages/{page.id}/send", params={"board_id": BOARD["id"], "target": "board"})
    else:
        response = client.post(f"/v1/boards/{BOARD['id']}/message", json={"page_id": page.id})
    assert response.status_code == 503
    assert "cannot receive flexible pixel frames" in response.json()["detail"]
    assert plugin.calls == []


@pytest.mark.parametrize("route", ["legacy", "v1"])
def test_direct_send_refuses_a_flexible_page_excluded_by_targets(client, pixel_board, route):
    plugin, _ = pixel_board
    page = stored(red_band(targets={"boards": ["another-install"]}))
    if route == "legacy":
        response = client.post(f"/pages/{page.id}/send", params={"board_id": BOARD["id"], "target": "board"})
    else:
        response = client.post(f"/v1/boards/{BOARD['id']}/message", json={"page_id": page.id})
    assert response.status_code == 422
    assert "only on the boards it lists" in response.json()["detail"]
    assert plugin.calls == []


def test_engine_projection_refuses_a_pixel_frame_that_the_driver_would_drop(client, pixel_board, monkeypatch):
    from src.outputs.plugin_driver import OutputPluginDriver

    plugin, _ = pixel_board
    monkeypatch.setattr(Sign, "write_cells", OutputPluginBase.write_cells)
    driver = OutputPluginDriver(plugin, character_set=plugin.character_set)
    page = stored(red_band())
    result = get_page_service().render_page(page, board=BOARD, **render_kw(driver))
    assert result.available and result.layers
    with pytest.raises(ValueError, match="cannot receive flexible pixel frames"):
        _project_page(driver, result, page, dimensions_of(BOARD), PageFit(True, None, None))
    assert plugin.calls == []


def test_native_frame_path_requires_a_character_set_that_keeps_layers():
    from src.displays.service import DisplayResult
    from src.outputs.plugin_driver import OutputPluginDriver
    from src.pages.board_render import flexible_frame_error
    from tests.test_native_playlist import NativeSign

    result = DisplayResult("page:flexible", "", {}, True, layers=[object()])
    driver = OutputPluginDriver(NativeSign())
    assert driver.native_rotation_enabled
    assert flexible_frame_error(red_band(), result, driver, native=True) is not None


@pytest.mark.parametrize("restriction", ["targets", "writer"])
def test_held_page_revalidates_target_and_frame_support(client, pixel_board, monkeypatch, restriction):
    from src.main import BoardRuntime, DisplayService
    from src.outputs.plugin_driver import OutputPluginDriver
    from src.silence_queue import HeldSend

    plugin, _ = pixel_board
    if restriction == "writer":
        monkeypatch.setattr(Sign, "write_cells", OutputPluginBase.write_cells)
    driver = OutputPluginDriver(plugin, character_set=plugin.character_set)
    page = stored(red_band(**({"targets": {"boards": ["another-install"]}} if restriction == "targets" else {})))
    service = DisplayService()
    monkeypatch.setattr(service, "_board_dict_for", lambda _: BOARD)
    runtime = BoardRuntime(client=driver, board_id=BOARD["id"])
    assert service._held_page_render(HeldSend.page(page.id, board_id=BOARD["id"]), runtime) is None
    assert plugin.calls == []


def test_unsupported_silence_page_falls_back_to_indicator(client, pixel_board, monkeypatch):
    from src.main import BoardRuntime, DisplayService
    from src.outputs.plugin_driver import OutputPluginDriver

    plugin, _ = pixel_board
    monkeypatch.setattr(Sign, "write_cells", OutputPluginBase.write_cells)
    driver = OutputPluginDriver(plugin, character_set=plugin.character_set)
    page = stored(red_band())
    service = DisplayService()
    indicator = Mock(return_value=True)
    monkeypatch.setattr(service, "_send_silence_indicator", indicator)
    assert service._send_silence_page(
        BoardRuntime(client=driver, board_id=BOARD["id"]),
        {"page_id": page.id},
        device_type="panel",
        grid_rows=8,
        grid_cols=10,
        board=BOARD,
    )
    indicator.assert_called_once()
    assert plugin.calls == []
