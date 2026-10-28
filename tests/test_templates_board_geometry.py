"""A render targeted at a board (``board_id``) renders at that board's grid.

``POST /templates/render`` with only ``board_id`` for a 10x16 Pixoo panel
answered 6 lines of 22 tiles (Flagship's default) while the engine drew the
page at 10x16: the endpoint used the board for its character set and the
request's (absent) geometry for its size.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

PANEL = {
    "id": "panel-1",
    "name": "Panel",
    "device_type": "panel",
    "output": "fiestapanel",
    "grid_rows": 10,
    "grid_cols": 16,
}


@pytest.fixture
def client(_isolated_data_dir):
    from src.api_server import app
    from src.settings.service import get_settings_service

    get_settings_service().set_boards([PANEL])
    return TestClient(app)


@pytest.mark.parametrize("path", ["/templates/render", "/templates/render/live"])
def test_a_render_for_a_board_uses_the_boards_grid(client, path):
    response = client.post(path, json={"template": ["{{filled:-}}"], "board_id": "panel-1"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["line_count"] == 10, "the board is 10 rows, not Flagship's 6"
    assert body["lines"][0] == "-" * 16, "the board is 16 tiles wide, not Flagship's 22"


def test_an_explicit_geometry_still_wins_over_the_boards(client):
    response = client.post(
        "/templates/render",
        json={"template": ["{{filled:-}}"], "board_id": "panel-1", "device_type": "note"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["lines"][0] == "-" * 15
