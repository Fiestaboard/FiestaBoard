"""Page sends and previews over the API draw a grid page at its own text size.

An 8 x 10 Pixoo 64 (the 5x7 face) also produces 10 x 16 (the 3x5 face), so a
10 x 16 page sent to it by any route (``POST /v1/boards/{board}/message`` with
a ``page_id``, ``PUT /v1/boards/{board}/active-page``, ``POST
/pages/{id}/send``) reaches the board as cells at the board's own 8 x 10 grid
under one opaque full-frame layer (design section 7), and a per-cell
transition runs as a fade (design section 6). The batch preview answers such
a page at its own grid and face, with its canvases on the face grid, never
the full frame (thumbnails stay light).
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from src.led.charsets import BUILTIN_CHARACTER_SETS
from src.led.matrix import model_with_led_font
from src.led.page_frame import is_full_frame_layer
from src.outputs.plugin_driver import OutputPluginDriver
from src.pages.models import Page
from src.pages.service import get_page_service
from src.settings.service import get_settings_service
from tests.canvas.test_output_layers import Sign as _Sign
from tests.test_led_text_size import PIXOO, _board, pixoo_output  # noqa: F401
from tests.test_v1_contract import client  # noqa: F401

LED_5X7 = BUILTIN_CHARACTER_SETS["led_5x7"]
#: A Pixoo 64 that chose the 5x7 face: 8 x 10 cells on a 64 x 64 matrix.
PIXOO_5X7 = model_with_led_font(PIXOO, "5x7")
BOARD = _board(grid_rows=8, grid_cols=10, output_config={"host": "192.0.2.50", "font": "5x7"})
CANVAS = {"id": "art", "area": {"row": 1, "col": 1, "rows": 1, "cols": 2}, "content": {"background": "#ff0000"}}
ENDPOINTS = ["message", "active-page", "pages-send"]


class Sign(_Sign):
    """The recording LED plugin, bound to the 5x7 Pixoo."""

    def __init__(self):
        super().__init__()
        self.bind_board(device_model=PIXOO_5X7, character_set=LED_5X7, geometry=(8, 10))


@pytest.fixture
def board(client, pixoo_output):  # noqa: F811
    """The 8 x 10 Pixoo as the only board, its client a driver over :class:`Sign`."""
    get_settings_service().set_boards([BOARD])
    plugin = Sign()
    driver = OutputPluginDriver(plugin, character_set=LED_5X7)
    render = Mock(wraps=driver.render)
    driver.render = render
    service = Mock(vb_client=driver)
    service.get_board_client.return_value = driver
    with (
        patch("src.api_server.get_service", return_value=service),
        patch("src.display_runtime.get_service", return_value=service),
        patch("src.pages.routes.get_service", return_value=service),
    ):
        yield plugin, render


def _page(rows: int = 10, cols: int = 16, **fields) -> str:
    page = Page(
        name="Face",
        type="template",
        device_type="panel",
        grid_rows=rows,
        grid_cols=cols,
        template=["HELLO"],
        **{"transition_strategy": "none", **fields},
    )
    get_page_service().storage.create(page)
    return page.id


def _send(client, endpoint: str, page_id: str, strategy: str = "none"):  # noqa: F811
    if endpoint == "message":
        body = {"page_id": page_id, "transition": {"strategy": strategy}}
        response = client.post(f"/v1/boards/{BOARD['id']}/message", json=body)
    elif endpoint == "active-page":
        response = client.put(f"/v1/boards/{BOARD['id']}/active-page", json={"page_id": page_id})
    else:
        response = client.post(f"/pages/{page_id}/send", params={"board_id": BOARD["id"], "target": "board"})
    assert response.status_code == 200, response.text
    return response


def _last_cells(plugin):
    return plugin.calls[-1][-1]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_a_10x16_page_sent_to_an_8x10_board_arrives_as_one_full_frame(client, board, endpoint):  # noqa: F811
    plugin, _ = board
    _send(client, endpoint, _page())
    layers = _last_cells(plugin).layers
    assert len(layers) == 1 and is_full_frame_layer(layers[0], 64, 64)


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_the_cells_under_the_full_frame_carry_the_page_text_at_the_boards_grid(client, board, endpoint):  # noqa: F811
    plugin, _ = board
    _send(client, endpoint, _page())
    cells = _last_cells(plugin)
    assert (len(cells), len(cells[0])) == (8, 10)
    assert "".join(t.value or "" for t in cells[0]).startswith("HELLO")


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_a_page_at_the_boards_own_size_is_sent_as_cells_only(client, board, endpoint):  # noqa: F811
    plugin, _ = board
    _send(client, endpoint, _page(8, 10))
    assert _last_cells(plugin).layers == ()


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_a_flip_into_a_face_page_is_sent_as_a_fade(client, board, endpoint):  # noqa: F811
    _, render = board
    _send(client, endpoint, _page(transition_strategy="flip"), strategy="flip")
    assert render.call_args.kwargs["strategy"] == "fade"


@pytest.fixture
def preview(client, pixoo_output):  # noqa: F811
    get_settings_service().set_boards([BOARD])

    def _preview(page_id: str) -> dict:
        response = client.post("/pages/preview/batch", json={"page_ids": [page_id], "board_id": BOARD["id"]})
        assert response.status_code == 200, response.text
        return response.json()["previews"][page_id]

    return _preview


def test_the_batch_preview_draws_a_face_page_at_its_own_grid(preview):
    entry = preview(_page(canvases=[CANVAS]))
    assert entry["face"] == "3x5" and (len(entry["cells"]), len(entry["cells"][0])) == (10, 16)


def test_the_batch_preview_sends_a_face_pages_canvases_on_the_face_grid_not_the_full_frame(preview):
    entry = preview(_page(canvases=[CANVAS]))
    assert [(layer["x"], layer["y"]) for layer in entry["layers"]] == [(0, 2)]


def test_the_batch_preview_of_a_page_at_the_boards_own_size_has_no_face(preview):
    entry = preview(_page(8, 10))
    assert "face" not in entry and (len(entry["cells"]), len(entry["cells"][0])) == (8, 10)
