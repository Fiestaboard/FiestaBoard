"""Live canvas edits reach the output and its cached frame, even without text."""

from unittest.mock import Mock, patch

import pytest

from src.canvas import CanvasLayer
from src.outputs.plugin_driver import OutputPluginDriver
from src.settings.service import get_settings_service
from tests.canvas.test_output_layers import LED_3X5, Sign
from tests.test_v1_contract import client  # noqa: F401


@pytest.mark.parametrize("template", [["HELLO"], [""]])
def test_live_canvas_changes_and_removal_reach_output(client, template):  # noqa: F811
    get_settings_service().set_boards(
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
    service.runtime_for.return_value = Mock(client=driver)
    with patch("src.display_runtime.get_service", return_value=service):
        for color, pixel in [("#ff0000", bytes([255, 0, 0, 255])), ("#0000ff", bytes([0, 0, 255, 255])), (None, None)]:
            canvases = (
                []
                if color is None
                else [
                    {"id": "art", "area": {"row": 1, "col": 1, "rows": 1, "cols": 2}, "content": {"background": color}}
                ]
            )
            response = client.post(
                "/templates/render/live", json={"template": template, "board_id": "pixels", "canvases": canvases}
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["sent_to_board"] is True
            expected = () if pixel is None else (CanvasLayer(x=0, y=2, w=7, h=5, rgba=pixel * 35),)
            assert body.get("layers") == [layer.to_json() for layer in expected]
            assert plugin.calls[-1][-1].layers == expected
            assert driver._frames.last_cells_shaped(10, 16).layers == expected
        assert len(plugin.calls) == 3
