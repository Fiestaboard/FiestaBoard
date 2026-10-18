"""Page message and pin endpoints preserve canvas-only changes through dispatch."""

from unittest.mock import Mock, patch

import pytest

from src.canvas import CanvasLayer
from src.outputs.plugin_driver import OutputPluginDriver
from src.pages.models import Page
from src.pages.service import get_page_service
from src.settings.service import get_settings_service
from tests.canvas.test_output_layers import LED_3X5, Sign
from tests.test_v1_contract import client  # noqa: F401


@pytest.mark.parametrize("endpoint", ["message", "active-page"])
def test_page_send_preserves_canvas_layers_and_canvas_only_changes(client, endpoint):  # noqa: F811
    settings = get_settings_service()
    settings.set_boards(
        [
            {
                "id": "pixels",
                "name": "Pixels",
                "device_type": "panel",
                "grid_rows": 10,
                "grid_cols": 16,
                "device_model": "divoom_pixoo64",
                "output": "divoom_pixoo",
                "output_config": {"font": "3x5", "host": "192.0.2.50"},
            }
        ]
    )
    plugin = Sign()
    driver = OutputPluginDriver(plugin, character_set=LED_3X5)
    service = Mock(vb_client=driver)
    service.get_board_client.return_value = driver
    pages = get_page_service()
    previous_grid = None
    with (
        patch("src.api_server.get_service", return_value=service),
        patch("src.display_runtime.get_service", return_value=service),
    ):
        for color, rgba in [("#ff0000", bytes([255, 0, 0, 255])), ("#0000ff", bytes([0, 0, 255, 255]))]:
            page = Page(
                name="Canvas",
                type="template",
                device_type="panel",
                grid_rows=10,
                grid_cols=16,
                template=["HELLO"],
                transition_strategy="none",
                canvases=[
                    {"id": "art", "area": {"row": 1, "col": 1, "rows": 1, "cols": 2}, "content": {"background": color}}
                ],
            )
            pages.storage.create(page)
            if endpoint == "message":
                response = client.post(
                    "/v1/boards/pixels/message", json={"page_id": page.id, "transition": {"strategy": "none"}}
                )
            else:
                response = client.put("/v1/boards/pixels/active-page", json={"page_id": page.id})
            assert response.status_code == 200, response.text
            expected = CanvasLayer(x=0, y=2, w=7, h=5, rgba=rgba * 35)
            assert plugin.calls[-1][-1].layers == (expected,)
            assert driver._frames.last_cells_shaped(10, 16).layers == (expected,)
            grid = driver._frames.characters
            if previous_grid is not None:
                assert grid == previous_grid
            previous_grid = grid
        assert len(plugin.calls) == 2
