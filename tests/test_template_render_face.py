"""The page editor draws and sends a grid page at its own text size.

An 8 x 10 Pixoo 64 (the 5x7 face) also produces 10 x 16 (the 3x5 face). A
10 x 16 page edited for it renders at that face (``POST /templates/render``
answers ``face`` and its canvases on the face grid, which the editor draws
client-side), and a live send (``POST /templates/render/live``) reaches the
board as cells at its own 8 x 10 grid under one opaque full-frame layer
(design section 7).
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from src.led.page_frame import is_full_frame_layer
from src.outputs.plugin_driver import OutputPluginDriver
from src.settings.service import get_settings_service
from tests.test_led_text_size import pixoo_output  # noqa: F401
from tests.test_routes_page_face import BOARD, CANVAS, LED_5X7, Sign
from tests.test_v1_contract import client  # noqa: F401

FACE_PAGE = {"device_type": "panel", "grid_rows": 10, "grid_cols": 16}
OWN_PAGE = {"device_type": "panel", "grid_rows": 8, "grid_cols": 10}


@pytest.fixture
def board(client, pixoo_output):  # noqa: F811
    """The 8 x 10 Pixoo as the only board, its live client a driver over :class:`Sign`."""
    get_settings_service().set_boards([BOARD])
    plugin = Sign()
    driver = OutputPluginDriver(plugin, character_set=LED_5X7)
    service = Mock(vb_client=driver)
    service.get_board_client.return_value = driver
    service.runtime_for.return_value = Mock(client=driver)
    with (
        patch("src.api_server.get_service", return_value=service),
        patch("src.display_runtime.get_service", return_value=service),
    ):
        yield plugin


def _render(client, geometry: dict, **fields) -> dict:  # noqa: F811
    body = {"template": ["HELLO"], "board_id": BOARD["id"], **geometry, **fields}
    response = client.post("/templates/render", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _live(client, geometry: dict, **fields) -> dict:  # noqa: F811
    body = {"template": ["HELLO"], "board_id": BOARD["id"], **geometry, **fields}
    response = client.post("/templates/render/live", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _last_cells(plugin):
    return plugin.calls[-1][-1]


def test_the_editor_renders_a_10x16_page_on_an_8x10_board_at_3x5(client, board):  # noqa: F811
    assert _render(client, FACE_PAGE)["face"] == "3x5"


def test_the_editor_draws_a_face_pages_canvases_on_the_face_grid(client, board):  # noqa: F811
    r = _render(client, FACE_PAGE, canvases=[CANVAS])
    assert [(layer["x"], layer["y"]) for layer in r["layers"]] == [(0, 2)]


def test_the_editor_checks_a_face_page_against_the_faces_character_set(client, board):  # noqa: F811
    assert _render(client, FACE_PAGE)["charset"] == "led_3x5"


def test_the_editor_renders_a_page_at_the_boards_own_size_without_a_face(client, board):  # noqa: F811
    assert "face" not in _render(client, OWN_PAGE)


def test_a_live_send_of_a_face_page_arrives_as_one_full_frame(client, board):  # noqa: F811
    _live(client, FACE_PAGE)
    layers = _last_cells(board).layers
    assert len(layers) == 1 and is_full_frame_layer(layers[0], 64, 64)


def test_a_live_send_of_a_face_page_with_canvases_arrives_as_one_full_frame(client, board):  # noqa: F811
    _live(client, FACE_PAGE, canvases=[CANVAS])
    layers = _last_cells(board).layers
    assert len(layers) == 1 and is_full_frame_layer(layers[0], 64, 64)


def test_the_cells_under_a_live_face_frame_carry_the_page_text_at_the_boards_grid(client, board):  # noqa: F811
    _live(client, FACE_PAGE)
    cells = _last_cells(board)
    assert (len(cells), len(cells[0])) == (8, 10)
    assert "".join(t.value or "" for t in cells[0]).startswith("HELLO")


def test_a_live_send_answers_the_face_and_the_canvases_on_the_face_grid(client, board):  # noqa: F811
    r = _live(client, FACE_PAGE, canvases=[CANVAS])
    assert r["face"] == "3x5" and [(layer["x"], layer["y"]) for layer in r["layers"]] == [(0, 2)]


def test_a_live_send_of_a_page_at_the_boards_own_size_is_cells_only(client, board):  # noqa: F811
    r = _live(client, OWN_PAGE)
    assert _last_cells(board).layers == () and r["face"] is None
