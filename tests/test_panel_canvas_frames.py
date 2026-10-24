"""Native TV viewers receive the same pixel canvases as LED hardware."""

import base64

import pytest
from fastapi.testclient import TestClient

from src.canvas.layer import CanvasLayer
from src.outputs.cells import project_message
from src.panels.models import PanelCreate, PanelUpdate
from src.panels.service import get_panel_service
from tests.live_boards import install_live_boards


@pytest.fixture
def panel_frame():
    from src.api_server import app

    board = {
        "id": "pixel-tv",
        "name": "Pixel TV",
        "api_mode": "virtual",
        "device_type": "panel",
        "grid_rows": 13,
        "grid_cols": 32,
    }
    panel = get_panel_service().create_panel(PanelCreate(name="Pixel TV"), board_id=board["id"])
    service = install_live_boards([board])
    api = TestClient(app)
    # Match the UI: creation builds a split-flap runtime before the user
    # selects LED. The PATCH must update the live driver's capabilities.
    changed = api.patch(f"/panels/{panel.id}", json={"render_style": "led_matrix"})
    assert changed.status_code == 200
    return api, panel, service.get_runtime(board["id"]).output.frames, board


def send(frames, layers=(), rows=13, cols=32):
    characters = [[0] * cols for _ in range(rows)]
    cells = project_message("", rows, cols, "led_5x7", layers=layers).cells
    frames.record_sent(characters, cells=cells)


def test_pixel_only_updates_and_removal_reach_tv_frames(panel_frame):
    api, panel, frames, _ = panel_frame
    url = f"/panel/{panel.id}/frame"
    for rgba in [b"\xff\x00\x00\xff", b"\x00\xff\x00\x01"]:
        send(frames, [CanvasLayer(x=7, y=9, w=1, h=1, rgba=rgba)])
        response = api.get(url)
        assert response.status_code == 200
        assert response.json()["layers"] == [
            {
                "x": 7,
                "y": 9,
                "width": 1,
                "height": 1,
                "rgba": base64.b64encode(rgba).decode("ascii"),
            }
        ]
        assert response.json()["characters"] == [[0] * 32 for _ in range(13)]
    send(frames)
    assert api.get(url).json()["layers"] == []


def test_layer_order_and_transparent_pixels_survive_serialization(panel_frame):
    api, panel, frames, _ = panel_frame
    send(
        frames,
        [
            CanvasLayer(x=-1, y=0, w=2, h=1, rgba=b"\x01\x02\x03\x00\x04\x05\x06\xff"),
            CanvasLayer(x=0, y=0, w=1, h=1, rgba=b"\x07\x08\x09\x80"),
        ],
    )
    layers = api.get(f"/panel/{panel.id}/frame").json()["layers"]
    assert [(layer["x"], layer["width"]) for layer in layers] == [(-1, 2), (0, 1)]
    assert [base64.b64decode(layer["rgba"]) for layer in layers] == [
        b"\x01\x02\x03\x00\x04\x05\x06\xff",
        b"\x07\x08\x09\x80",
    ]


@pytest.mark.parametrize("state", ["never-sent", "stale-shape", "cleared"])
def test_missing_frames_never_leak_old_canvas_layers(panel_frame, state):
    api, panel, frames, _ = panel_frame
    if state != "never-sent":
        send(frames, [CanvasLayer(x=0, y=0, w=1, h=1, rgba=b"\xff" * 4)], rows=1, cols=1)
    if state == "cleared":
        frames.clear()
    frame = api.get(f"/panel/{panel.id}/frame").json()
    assert frame["characters"] is None
    assert frame["layers"] == []


def test_split_flap_frame_keeps_legacy_contract(panel_frame):
    api, panel, frames, _ = panel_frame
    get_panel_service().update_panel(panel.id, PanelUpdate(render_style="split_flap"))
    send(frames, [CanvasLayer(x=0, y=0, w=1, h=1, rgba=b"\xff" * 4)])
    frame = api.get(f"/panel/{panel.id}/frame").json()
    assert "layers" not in frame
    assert frame["characters"] is not None


def test_page_canvases_reach_the_tv_through_real_output_delivery(panel_frame):
    api, panel, _, board = panel_frame
    previous_characters = None
    for color in ["#ff0000", "#0000ff", None]:
        canvases = (
            []
            if color is None
            else [
                {
                    "id": "art",
                    "area": {"row": 1, "col": 1, "rows": 1, "cols": 1},
                    "content": {"background": color},
                }
            ]
        )
        created = api.post(
            "/pages",
            json={
                "name": "Pixel art",
                "type": "template",
                "device_type": "panel",
                "grid_rows": 13,
                "grid_cols": 32,
                "template": [""],
                "canvases": canvases,
            },
        )
        assert created.status_code == 201, created.text
        sent = api.post(
            f"/v1/boards/{board['id']}/message",
            json={
                "page_id": created.json()["id"],
                "transition": {"strategy": "none"},
            },
        )
        assert sent.status_code == 200, sent.text
        frame = api.get(f"/panel/{panel.id}/frame").json()
        if color is None:
            assert frame["layers"] == []
        else:
            assert len(frame["layers"]) == 1
            layer = frame["layers"][0]
            assert (layer["x"], layer["y"], layer["width"], layer["height"]) == (0, 2, 5, 7)
            expected = bytes.fromhex(color[1:] + "ff") * 35
            assert base64.b64decode(layer["rgba"]) == expected
        if previous_characters is not None:
            assert frame["characters"] == previous_characters
        previous_characters = frame["characters"]


def test_style_round_trip_rebinds_delivery_but_sizing_keeps_the_runtime(panel_frame):
    from src.display_runtime import get_service

    api, panel, _, board = panel_frame
    service = get_service()
    led_runtime = service.get_runtime(board["id"])
    api.patch(f"/panels/{panel.id}", json={"matrix_sizing": "fit_panel"}).raise_for_status()
    assert service.get_runtime(board["id"]) is led_runtime

    page = api.post(
        "/pages",
        json={
            "name": "Style switch",
            "type": "template",
            "device_type": "panel",
            "grid_rows": 13,
            "grid_cols": 32,
            "template": [""],
            "canvases": [
                {"id": "art", "area": {"row": 1, "col": 1, "rows": 1, "cols": 1}, "content": {"background": "#ff0000"}}
            ],
        },
    )
    assert page.status_code == 201
    for style in ["split_flap", "led_matrix"]:
        api.patch(f"/panels/{panel.id}", json={"render_style": style}).raise_for_status()
        sent = api.post(f"/v1/boards/{board['id']}/message", json={"page_id": page.json()["id"]})
        assert sent.status_code == 200
        assert sent.json()["sent"] is True
        frame = api.get(f"/panel/{panel.id}/frame").json()
        if style == "led_matrix":
            assert len(frame["layers"]) == 1
        else:
            assert "layers" not in frame
