"""H3: what a display can draw, on ``GET /v1/boards/{board}`` as ``drawing``.

The web editor's touch toolbar (and the phone's after it) picks its tools
from :meth:`DisplayProfile.supports`. Until now the profile was served only by
``GET /outputs/boards/{id}``, which the phone's ``control`` scope can't reach,
so a client had to re-derive it from the ``charset`` id. Pinned here:

- ``drawing.features`` is exactly :data:`FEATURES`, each answered by
  ``supports()`` (one definition, server-side);
- the facts the toolbar's sheets need: colour model, lit colour, LED face,
  icon names and a pixel matrix's size;
- a board whose device is unknown reads the split-flap baseline with
  ``source: "baseline"`` (reads fall back; never a 500);
- it is on the board resource only: not the list, not ``GET /status``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.outputs.display_profile import FEATURES, display_profile_for_board
from tests import test_led_board_layout as layout

output_plugin = layout.output_plugin

DRAWING_KEYS = {
    "source",
    "technology",
    "color",
    "monochrome",
    "font",
    "icons",
    "pixel_width",
    "pixel_height",
    "features",
}

BASELINE_FEATURES = {feature: feature == "tiles" for feature in FEATURES}


@pytest.fixture
def client(_isolated_data_dir):
    from src.api_server import app

    return TestClient(app)


def _set_boards(boards: list[dict]) -> list[dict]:
    from src.settings.service import get_settings_service

    return get_settings_service().set_boards(boards).boards


def _drawing(client: TestClient, board_id: str) -> dict:
    response = client.get(f"/v1/boards/{board_id}")
    assert response.status_code == 200, response.text
    return response.json()["drawing"]


def test_a_flagship_draws_capitals_and_colour_tiles_only(client):
    (board,) = _set_boards([{"device_type": "flagship", "name": "Kitchen"}])

    assert _drawing(client, board["id"]) == {
        "source": "device",
        "technology": "split_flap",
        "color": "tiles",
        "monochrome": None,
        "font": None,
        "icons": [],
        "pixel_width": None,
        "pixel_height": None,
        "features": BASELINE_FEATURES,
    }


def test_a_pixoo_reports_what_its_output_declares(client, output_plugin):
    boards = _set_boards([layout.HALL, layout.PIXOO])
    pixoo = boards[1]
    profile = display_profile_for_board(pixoo)
    assert profile is not None

    drawing = _drawing(client, pixoo["id"])

    assert drawing["source"] == "device"
    assert (drawing["technology"], drawing["color"], drawing["monochrome"]) == ("led_matrix", "rgb", None)
    assert drawing["font"] == "3x5"
    assert (drawing["pixel_width"], drawing["pixel_height"]) == (64, 64)
    assert drawing["icons"] == list(profile.icons) and "sun" in drawing["icons"]
    assert drawing["features"] == {feature: profile.supports(feature) for feature in FEATURES}
    assert drawing["features"]["lowercase"] and drawing["features"]["pixels"] and drawing["features"]["rgb"]


def test_the_seamless_tile_style_draws_solid_shapes(client, output_plugin):
    fill = {**layout.PIXOO, "output_config": {**layout.PIXOO["output_config"], "tile_gap": "fill"}}
    boards = _set_boards([layout.HALL, fill])

    assert _drawing(client, boards[1]["id"])["features"]["solid_shapes"] is True


def test_a_display_whose_output_is_not_installed_reads_the_split_flap_baseline(client, monkeypatch):
    (board,) = _set_boards([{"device_type": "flagship", "name": "Kitchen"}])
    monkeypatch.setattr("src.v1.routes_boards.display_profile_for_board", lambda _board: None)

    drawing = _drawing(client, board["id"])

    assert drawing["source"] == "baseline"
    assert drawing["technology"] == "split_flap" and drawing["color"] == "tiles"
    assert drawing["features"] == BASELINE_FEATURES


def test_a_profile_that_raises_reads_the_baseline_not_a_500(client, monkeypatch):
    (board,) = _set_boards([{"device_type": "flagship", "name": "Kitchen"}])

    def boom(_board):
        raise RuntimeError("bad device model")

    monkeypatch.setattr("src.v1.routes_boards.display_profile_for_board", boom)

    drawing = _drawing(client, board["id"])

    assert drawing["source"] == "baseline"
    assert drawing["features"] == BASELINE_FEATURES


def test_the_shape_is_exactly_the_documented_one(client):
    (board,) = _set_boards([{"device_type": "flagship", "name": "Kitchen"}])

    drawing = _drawing(client, board["id"])

    assert set(drawing) == DRAWING_KEYS
    assert set(drawing["features"]) == set(FEATURES)


def test_patch_answers_with_drawing_but_the_list_and_status_do_not(client):
    (board,) = _set_boards([{"device_type": "flagship", "name": "Kitchen"}])

    patched = client.patch(f"/v1/boards/{board['id']}", json={"name": "Den"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["drawing"]["features"] == BASELINE_FEATURES

    listed = client.get("/v1/boards").json()["boards"]
    assert all("drawing" not in entry for entry in listed)

    status = client.get("/status").json()
    for entry in (status.get("boards") or {}).values():
        assert "drawing" not in entry
