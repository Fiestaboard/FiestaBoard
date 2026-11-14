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

import json
import shutil

import pytest
from fastapi.testclient import TestClient

from src.outputs.display_profile import FEATURES, display_profile_for_board
from src.plugins.loader import PluginLoader
from tests import test_led_board_layout as layout

output_plugin = layout.output_plugin


@pytest.fixture
def small_led_output(tmp_path):
    """The recording output offering a TC001 (32 x 8, RGB) and a MAX7219 (32 x 8, one lit colour)."""
    root = tmp_path / "plugins"
    target = root / layout.PLUGIN_ID
    shutil.copytree(layout.FIXTURE, target, ignore=shutil.ignore_patterns("__pycache__"))
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["output"].pop("character_set")
    manifest_path.write_text(json.dumps(manifest), "utf-8")
    models_path = target / "output" / "device-models.json"
    models = json.loads(models_path.read_text("utf-8"))
    models_path.write_text(json.dumps([models[0], "ulanzi_tc001_awtrix", "max7219_4in1"]), "utf-8")
    loader = PluginLoader(plugins_dir=root, external_dirs=[])
    assert loader.load_plugin(layout.PLUGIN_ID) is not None, loader.load_errors
    yield loader
    loader.unload_plugin(layout.PLUGIN_ID)


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


def test_a_tc001_reports_its_wide_pixel_size(client, small_led_output):
    tc001 = {**layout.PIXOO, "id": "tc001-1", "device_model": "ulanzi_tc001_awtrix", "grid_rows": 1, "grid_cols": 8}
    boards = _set_boards([layout.HALL, tc001])

    drawing = _drawing(client, boards[1]["id"])

    assert (drawing["pixel_width"], drawing["pixel_height"]) == (32, 8)
    assert drawing["features"]["pixels"] is True


def test_a_single_colour_panel_reports_its_lit_colour(client, small_led_output):
    sign = {**layout.PIXOO, "id": "max-1", "device_model": "max7219_4in1", "grid_rows": 1, "grid_cols": 8}
    boards = _set_boards([layout.HALL, sign])
    profile = display_profile_for_board(boards[1])
    assert profile is not None and profile.monochrome

    drawing = _drawing(client, boards[1]["id"])

    assert (drawing["color"], drawing["monochrome"]) == ("mono", profile.monochrome)
    assert drawing["features"]["rgb"] is False


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
