"""A board write is held to its model's grid floor.

The LED floor of 1 x 5 belongs to LED boards measured in pixels only (a
32 x 8 Ulanzi TC001 is a 1 x 8 board). Every other model keeps the 3 x 15
Note floor: a FiestaPanel, or an output plugin's board on a ``panel`` model,
written at 1 x 5 is refused (400, nothing saved), never stored. A board
already stored below its floor (settings written before this check) keeps
loading as it is, and a write that leaves its grid alone still saves.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from src.plugins.loader import PluginLoader

FIXTURE = Path(__file__).parent / "fixtures" / "plugins" / "recording_output"
PLUGIN_ID = "recording_output"

#: An output plugin's model sized per board, like a TV: the Note floor applies.
PANEL_MODEL = {
    "id": "recording_tv",
    "label": "Recording TV",
    "technology": "split_flap",
    "family": "recording",
    "geometry": {"kind": "panel"},
    "color": {"kind": "tiles"},
    "charset": "vestaboard_v2",
    "animation": {"delivery": "stream", "maxFps": 10},
}


@pytest.fixture
def recording_output(tmp_path):
    """The recording output offering the built-in TC001 and a panel-kind model."""
    target = tmp_path / "plugins" / PLUGIN_ID
    shutil.copytree(FIXTURE, target, ignore=shutil.ignore_patterns("__pycache__"))
    (target / "output" / "device-models.json").write_text(json.dumps(["ulanzi_tc001_awtrix", PANEL_MODEL]), "utf-8")
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    del manifest["output"]["character_set"]
    manifest["data_files"] = ["output/device-models.json"]
    manifest_path.write_text(json.dumps(manifest), "utf-8")
    (target / "output" / "character-set.json").unlink()
    loader = PluginLoader(plugins_dir=tmp_path / "plugins", external_dirs=[])
    assert loader.load_plugin(PLUGIN_ID) is not None, loader.load_errors
    yield loader
    loader.unload_plugin(PLUGIN_ID)


@pytest.fixture
def client():
    from src.api_server import app

    with (
        mock.patch("src.settings.routes.release_board_frames"),
        mock.patch("src.settings.routes.reinitialize_board_clients"),
    ):
        yield TestClient(app)


def _settings():
    from src.settings.service import get_settings_service

    return get_settings_service()


def _stored_boards() -> list[dict]:
    return [dict(b) for b in _settings().get_board_settings().boards]


def _fiestapanel(rows: int, cols: int) -> dict:
    return {
        "id": "tv-1",
        "name": "Living room TV",
        "device_type": "panel",
        "api_mode": "virtual",
        "grid_rows": rows,
        "grid_cols": cols,
    }


def _plugin_board(device_model: str, rows: int, cols: int, **config) -> dict:
    return {
        "id": "plugin-1",
        "name": "Shelf sign",
        "output": PLUGIN_ID,
        "device_model": device_model,
        "device_type": "panel",
        "grid_rows": rows,
        "grid_cols": cols,
        "output_config": {"host": "192.0.2.50", **config},
    }


def _put(client, *extra: dict):
    return client.put("/settings/board", json={"boards": [*_stored_boards(), *extra]})


def _grid(board_id: str) -> tuple:
    (board,) = [b for b in _stored_boards() if b["id"] == board_id]
    return board["grid_rows"], board["grid_cols"]


class TestFiestaPanelKeepsTheNoteFloor:
    def test_a_new_fiestapanel_board_at_1x5_is_refused_and_nothing_is_saved(self, client):
        before = _stored_boards()

        response = _put(client, _fiestapanel(1, 5))

        assert response.status_code == 400
        assert "3x15" in response.json()["detail"]
        assert _stored_boards() == before

    def test_shrinking_a_stored_fiestapanel_below_3x15_is_refused(self, client):
        assert _put(client, _fiestapanel(5, 15)).status_code == 200
        boards = _stored_boards()
        for board in boards:
            if board["id"] == "tv-1":
                board["grid_rows"], board["grid_cols"] = 3, 10

        response = client.put("/settings/board", json={"boards": boards})

        assert response.status_code == 400
        assert _grid("tv-1") == (5, 15)

    def test_a_fiestapanel_at_exactly_3x15_saves(self, client):
        assert _put(client, _fiestapanel(3, 15)).status_code == 200
        assert _grid("tv-1") == (3, 15)

    def test_add_board_refuses_a_fiestapanel_at_1x5(self):
        # POST /settings/board/add takes hardware shapes only; panels and
        # output plugins reach add_board directly.
        with pytest.raises(ValueError, match="3x15"):
            _settings().add_board(_fiestapanel(1, 5))

        assert "tv-1" not in {b["id"] for b in _stored_boards()}


class TestOutputPluginBoards:
    def test_a_panel_kind_plugin_board_at_1x5_is_refused(self, client, recording_output):
        response = _put(client, _plugin_board("recording_tv", 1, 5))

        assert response.status_code == 400
        assert "3x15" in response.json()["detail"]
        assert "plugin-1" not in {b["id"] for b in _stored_boards()}

    def test_a_tc001_board_at_1x8_saves(self, client, recording_output):
        response = _put(client, _plugin_board("ulanzi_tc001_awtrix", 1, 8, font="3x5"))

        assert response.status_code == 200, response.text
        assert _grid("plugin-1") == (1, 8)


class TestStoredBoardsBelowTheFloor:
    """Settings written before the check: loaded as they are, never rewritten."""

    @pytest.fixture
    def legacy_settings(self, _isolated_data_dir):
        # Raw, as an older release wrote it: no ``output``, just api_mode.
        _isolated_data_dir.mkdir(parents=True, exist_ok=True)
        path = _isolated_data_dir / "settings.json"
        path.write_text(json.dumps({"board": {"board_type": "black", "boards": [_fiestapanel(1, 5)]}}), "utf-8")
        return path

    def test_a_stored_1x5_fiestapanel_loads_unchanged(self, legacy_settings):
        from src.settings.service import SettingsService

        service = SettingsService(settings_file=str(legacy_settings))

        (board,) = service.get_board_settings().boards
        assert (board["grid_rows"], board["grid_cols"]) == (1, 5)

    def test_renaming_a_stored_1x5_fiestapanel_still_saves(self, legacy_settings):
        from src.settings.service import SettingsService

        service = SettingsService(settings_file=str(legacy_settings))
        (board,) = [dict(b) for b in service.get_board_settings().boards]
        board["name"] = "Den TV"

        (saved,) = service.set_boards([board]).boards

        assert saved["name"] == "Den TV"
        assert (saved["grid_rows"], saved["grid_cols"]) == (1, 5)
