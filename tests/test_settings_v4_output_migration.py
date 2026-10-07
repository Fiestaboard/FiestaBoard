"""Settings v4: every board stores its ``output`` and ``output_config`` (plan D8).

What this module pins, in order:

1. the v3 -> v4 migration — one test per ``output`` precedence branch, the
   field move, idempotence, and the per-board count it logs;
2. every upgrade fixture lands on disk in the v4 shape, and a migrated file
   run through the migration again is unchanged;
3. secrets: a GET -> PUT round trip of a masked board keeps every credential
   (board keys, note-array token, per-tile keys) and never returns one, in
   either the flat half or ``output_config``;
4. compatibility: every read still answers in the flat shape, and every write
   API accepts the flat shape, the v4 shape, and both at once — whichever
   half the client changed wins;
5. ``_config_signature`` follows ``output`` + ``output_config``;
6. a settings backup taken on v3 restores onto this build and migrates on load.
"""

from __future__ import annotations

import copy
import json
import logging
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.settings.board_shape import board_view, merge_board_write, migrate_board_to_v4
from src.settings.service import CURRENT_SETTINGS_SCHEMA_VERSION, _migrate_v3_to_v4

UPGRADE_FIXTURES = Path(__file__).parent / "fixtures" / "upgrade"
FLAT = ("api_mode", "host", "port", "local_api_key", "cloud_key", "note_array_token", "tiles")

LOCAL_KEY = "test_local_key_v4"
CLOUD_KEY = "test_cloud_key_v4"
TOKEN = "test_array_token_v4"
TILE_KEYS = ("test_tile_key_a", "test_tile_key_b")


def _v3_board(**overrides) -> dict:
    """A board exactly as settings v3 stored it (BoardInstance.to_dict order)."""
    board = {
        "id": "b1",
        "name": "Living Room",
        "device_type": "flagship",
        "board_color": "black",
        "code62_glyph": "degree",
        "enabled": True,
        "paused": False,
        "schedule_enabled": False,
        "api_mode": "local",
        "host": "192.0.2.10",
        "port": 7000,
        "local_api_key": LOCAL_KEY,
        "cloud_key": "",
        "note_array_token": "",
        "notes_wide": 1,
        "notes_tall": 1,
        "grid_rows": None,
        "grid_cols": None,
        "tiles": [],
    }
    board.update(overrides)
    return board


# ---------------------------------------------------------------------------
# 1. The migration
# ---------------------------------------------------------------------------


class TestMigrationPrecedence:
    def test_an_explicit_output_wins_over_a_virtual_api_mode(self):
        board = _v3_board(api_mode="virtual", output="divoom_pixoo", output_config={"host": "192.0.2.40"})
        assert migrate_board_to_v4(board)
        assert board["output"] == "divoom_pixoo"
        assert board["output_config"] == {"host": "192.0.2.40"}, "a plugin keeps its own config"
        assert not set(FLAT) & set(board), "flat fields mean nothing to a plugin and are dropped"

    def test_an_explicit_vestaboard_keeps_its_connection_even_when_virtual(self):
        board = _v3_board(api_mode="virtual", output="vestaboard")
        migrate_board_to_v4(board)
        assert board["output"] == "vestaboard"
        assert board["output_config"]["api_mode"] == "virtual"

    def test_a_virtual_board_is_a_fiestapanel_with_no_config(self):
        board = _v3_board(
            device_type="panel", api_mode="virtual", host="", local_api_key="", grid_rows=12, grid_cols=29
        )
        migrate_board_to_v4(board)
        assert (board["output"], board["output_config"]) == ("fiestapanel", {})
        assert (board["device_type"], board["grid_rows"], board["grid_cols"]) == ("panel", 12, 29)

    def test_a_legacy_virtual_note_array_panel_is_a_fiestapanel(self):
        board = _v3_board(device_type="note_array", api_mode="virtual", notes_wide=1, notes_tall=4)
        migrate_board_to_v4(board)
        assert board["output"] == "fiestapanel"
        assert (board["device_type"], board["notes_tall"]) == ("note_array", 4)

    def test_everything_else_is_a_vestaboard_whose_connection_moves_into_output_config(self):
        board = _v3_board()
        migrate_board_to_v4(board)
        assert board["output"] == "vestaboard"
        assert board["output_config"] == {
            "api_mode": "local",
            "host": "192.0.2.10",
            "port": 7000,
            "local_api_key": LOCAL_KEY,
            "cloud_key": "",
            "note_array_token": "",
            "tiles": [],
        }
        assert list(board) == [
            "id",
            "name",
            "device_type",
            "board_color",
            "code62_glyph",
            "enabled",
            "paused",
            "schedule_enabled",
            "notes_wide",
            "notes_tall",
            "grid_rows",
            "grid_cols",
            "output",
            "output_config",
        ], "identity, display, flags and geometry stay top-level, in place"

    def test_a_v3_board_without_an_api_mode_is_a_vestaboard(self):
        board = {"id": "b1", "device_type": "note_array", "note_array_token": TOKEN}
        migrate_board_to_v4(board)
        assert board == {
            "id": "b1",
            "device_type": "note_array",
            "output": "vestaboard",
            "output_config": {"note_array_token": TOKEN},
        }

    def test_a_flat_value_wins_over_an_output_config_value(self):
        """v2->v3 imports legacy credentials flat onto a default board that is
        already v4-shaped; the import is the newer value."""
        board = {"id": "b1", "output": "vestaboard", "output_config": {"local_api_key": ""}, "local_api_key": LOCAL_KEY}
        migrate_board_to_v4(board)
        assert board["output_config"]["local_api_key"] == LOCAL_KEY


class TestMigrationRun:
    def _data(self) -> dict:
        return {
            "schema_version": 3,
            "board": {
                "board_type": "black",
                "boards": [
                    _v3_board(),
                    _v3_board(id="b2", device_type="panel", api_mode="virtual", grid_rows=12, grid_cols=29),
                ],
            },
        }

    def test_it_counts_the_boards_it_changed(self):
        assert _migrate_v3_to_v4(self._data()) == 2

    def test_it_is_idempotent(self):
        data = self._data()
        _migrate_v3_to_v4(data)
        once = copy.deepcopy(data)
        assert _migrate_v3_to_v4(data) == 0
        assert data == once

    def test_a_devices_era_section_needs_nothing(self):
        assert _migrate_v3_to_v4({"board": {"board_type": "black", "devices": ["flagship"]}}) == 0

    def test_the_run_logs_its_count_and_backs_up_the_v3_file(self, tmp_path, caplog):
        from src.settings.service import SettingsService

        path = tmp_path / "settings.json"
        path.write_text(json.dumps(self._data()))
        v3 = path.read_bytes()
        with caplog.at_level(logging.INFO, logger="src.settings.service"):
            SettingsService(settings_file=str(path))
        assert "Settings schema migration v3->v4: 2 change(s) applied" in caplog.text
        assert (tmp_path / "settings.json.v3_backup").read_bytes() == v3
        assert json.loads(path.read_text())["schema_version"] == CURRENT_SETTINGS_SCHEMA_VERSION

    def test_the_default_board_is_born_in_the_v4_shape(self):
        from src.settings.service import BoardSettings

        (board,) = BoardSettings().boards
        assert board["output"] == "vestaboard"
        assert board["output_config"]["api_mode"] == "local"
        assert not set(FLAT) & set(board)


# ---------------------------------------------------------------------------
# 2. Every upgrade fixture lands in the v4 shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label", sorted(p.name for p in UPGRADE_FIXTURES.iterdir() if p.is_dir()))
def test_every_upgrade_fixture_is_stored_in_the_v4_shape_and_migrates_once(label, _isolated_data_dir):
    from tests.test_upgrade_fixtures import boot

    boot(label, _isolated_data_dir)
    on_disk = json.loads((_isolated_data_dir / "settings.json").read_text())

    assert on_disk["schema_version"] == CURRENT_SETTINGS_SCHEMA_VERSION
    for board in on_disk["board"]["boards"]:
        assert isinstance(board["output"], str) and isinstance(board["output_config"], dict), board
        assert not set(FLAT) & set(board), f"{label}: flat fields left at the top level of {board['id']}"
    again = copy.deepcopy(on_disk)
    assert _migrate_v3_to_v4(again) == 0
    assert again == on_disk, "a migrated file run through the migration again is unchanged"


def test_a_migrated_data_dir_boots_again_without_rewriting_settings(_isolated_data_dir):
    from tests.conftest import _drop_all_singletons
    from tests.test_upgrade_fixtures import Booted, boot

    boot("v9_10_schema3_multi_board", _isolated_data_dir)
    first = (_isolated_data_dir / "settings.json").read_bytes()
    _drop_all_singletons()
    Booted(_isolated_data_dir)
    assert (_isolated_data_dir / "settings.json").read_bytes() == first


# ---------------------------------------------------------------------------
# 3. Secrets: GET -> PUT keeps them and never returns them
# ---------------------------------------------------------------------------


@pytest.fixture
def api(monkeypatch) -> TestClient:
    from src.api_server import app

    monkeypatch.setattr("src.settings.routes.reinitialize_board_clients", lambda: None)
    monkeypatch.setattr("src.config_api.routes.reinitialize_board_clients", lambda: None)
    return TestClient(app)


def _settings():
    from src.settings.service import get_settings_service

    return get_settings_service()


def _secret_boards() -> list[dict]:
    tiles = [
        {"row": 0, "col": 0, "host": "192.0.2.21", "port": 7000, "local_api_key": TILE_KEYS[0], "enabled": True},
        {"row": 0, "col": 1, "host": "192.0.2.22", "port": 7000, "local_api_key": TILE_KEYS[1], "enabled": True},
    ]
    return [
        {"id": "local", "name": "Local", "device_type": "flagship", "api_mode": "local", "host": "192.0.2.10",
         "local_api_key": LOCAL_KEY},
        {"id": "cloud", "name": "Cloud", "device_type": "note", "api_mode": "cloud", "cloud_key": CLOUD_KEY},
        {"id": "array", "name": "Array", "device_type": "note_array", "api_mode": "cloud", "notes_wide": 2,
         "note_array_token": TOKEN},
        {"id": "tiles", "name": "Tiles", "device_type": "note_array", "api_mode": "local", "notes_wide": 2,
         "tiles": tiles},
    ]  # fmt: skip


def _stored() -> list[dict]:
    return copy.deepcopy(_settings().get_board_settings().to_dict(mask_secrets=False)["boards"])


class TestSecretsRoundTrip:
    def test_get_never_returns_a_credential_in_either_half(self, api):
        _settings().set_boards(_secret_boards())
        body = api.get("/settings/board").text
        for secret in (LOCAL_KEY, CLOUD_KEY, TOKEN, *TILE_KEYS):
            assert secret not in body
        boards = {b["id"]: b for b in api.get("/settings/board").json()["boards"]}
        assert boards["local"]["local_api_key"] == boards["local"]["output_config"]["local_api_key"] == "***"
        assert boards["array"]["output_config"]["note_array_token"] == "***"
        assert [t["local_api_key"] for t in boards["tiles"]["output_config"]["tiles"]] == ["***", "***"]

    def test_echoing_get_back_keeps_every_credential(self, api):
        """The golden round trip: GET -> PUT changes nothing stored."""
        _settings().set_boards(_secret_boards())
        before = _stored()
        boards = api.get("/settings/board").json()["boards"]
        assert api.put("/settings/board", json={"boards": boards}).status_code == 200
        assert _stored() == before

    def test_echoing_only_the_v4_half_keeps_every_credential(self, api):
        _settings().set_boards(_secret_boards())
        before = _stored()
        boards = [{k: v for k, v in b.items() if k not in FLAT} for b in api.get("/settings/board").json()["boards"]]
        assert api.put("/settings/board", json={"boards": boards}).status_code == 200
        assert _stored() == before

    def test_moved_tiles_keep_their_keys_through_output_config(self, api):
        """Tiles carry no id: a masked key follows its board by host:port."""
        _settings().set_boards(_secret_boards())
        board = next(b for b in api.get("/settings/board").json()["boards"] if b["id"] == "tiles")
        config = board["output_config"]
        config["tiles"][0]["col"], config["tiles"][1]["col"] = 1, 0
        update = {k: v for k, v in board.items() if k not in FLAT}
        others = [b for b in api.get("/settings/board").json()["boards"] if b["id"] != "tiles"]
        assert api.put("/settings/board", json={"boards": [*others, update]}).status_code == 200
        stored = next(b for b in _stored() if b["id"] == "tiles")
        by_host = {t["host"]: t["local_api_key"] for t in stored["output_config"]["tiles"]}
        assert by_host == {"192.0.2.21": TILE_KEYS[0], "192.0.2.22": TILE_KEYS[1]}


# ---------------------------------------------------------------------------
# 4. Compatibility: flat reads, writes in either shape
# ---------------------------------------------------------------------------


class TestFlatReads:
    def test_settings_get_answers_in_the_v3_flat_shape(self, api):
        _settings().set_boards([_v3_board(local_api_key="")])
        (board,) = api.get("/settings/board").json()["boards"]
        assert {k: board[k] for k in FLAT} == {
            "api_mode": "local",
            "host": "192.0.2.10",
            "port": 7000,
            "local_api_key": "",
            "cloud_key": "",
            "note_array_token": "",
            "tiles": [],
        }
        assert board["output"] == "vestaboard"

    def test_a_panel_reads_virtual(self, api):
        _settings().set_boards([{"id": "p", "device_type": "panel", "output": "fiestapanel"}])
        (board,) = api.get("/settings/board").json()["boards"]
        assert (board["api_mode"], board["output"], board["output_config"]) == ("virtual", "fiestapanel", {})

    def test_the_legacy_config_board_view_reads_output_config(self, api):
        _settings().set_boards([_v3_board(api_mode="cloud", cloud_key=CLOUD_KEY)])
        config = api.get("/config/board").json()["config"]
        assert (config["api_mode"], config["cloud_key"]) == ("cloud", "***")

    def test_the_mcp_board_projection_reads_output_config(self):
        from src.ops.executors import board_public_view

        _settings().set_boards([_v3_board()])
        view = board_public_view(_settings().get_board_settings().boards[0])
        assert (view["api_mode"], view["has_host"], view["has_credentials"]) == ("local", True, True)

    def test_board_view_is_idempotent(self):
        stored = _settings().set_boards([_v3_board()]).boards[0]
        assert board_view(board_view(stored)) == board_view(stored)


class TestWritesInEitherShape:
    def _put_one(self, api, board: dict) -> dict:
        response = api.put("/settings/board", json={"boards": [board]})
        assert response.status_code == 200, response.text
        return _stored()[0]["output_config"]

    def test_a_flat_edit_wins_over_an_echoed_stale_output_config(self, api):
        _settings().set_boards([_v3_board()])
        (board,) = api.get("/settings/board").json()["boards"]
        board["host"] = "192.0.2.99"  # today's form edits the flat field
        assert self._put_one(api, board)["host"] == "192.0.2.99"

    def test_an_output_config_edit_wins_over_echoed_stale_flat_fields(self, api):
        _settings().set_boards([_v3_board()])
        (board,) = api.get("/settings/board").json()["boards"]
        board["output_config"]["host"] = "192.0.2.98"  # a v4 form edits output_config
        assert self._put_one(api, board)["host"] == "192.0.2.98"

    def test_a_flat_only_write_lands_in_output_config(self, api):
        _settings().set_boards([_v3_board()])
        config = self._put_one(api, {"id": "b1", "device_type": "flagship", "api_mode": "cloud", "cloud_key": "k2"})
        assert (config["api_mode"], config["cloud_key"]) == ("cloud", "k2")

    def test_a_v4_only_write_is_stored_as_given(self, api):
        _settings().set_boards([_v3_board()])
        config = self._put_one(
            api,
            {"id": "b1", "device_type": "flagship", "output": "vestaboard", "output_config": {"api_mode": "cloud",
             "cloud_key": "k3"}},
        )  # fmt: skip
        assert (config["api_mode"], config["cloud_key"], config["host"]) == ("cloud", "k3", "")

    def test_add_board_accepts_the_flat_shape(self, api):
        response = api.post("/settings/board/add", json={"device_type": "note", "api_mode": "cloud", "cloud_key": "k4"})
        assert response.status_code == 201
        assert _stored()[-1]["output_config"]["cloud_key"] == "k4"

    def test_add_board_accepts_the_v4_shape(self, api):
        body = {
            "device_type": "note",
            "output": "vestaboard",
            "output_config": {"api_mode": "cloud", "cloud_key": "k5"},
        }
        assert api.post("/settings/board/add", json=body).status_code == 201
        assert _stored()[-1]["output_config"]["cloud_key"] == "k5"

    def test_the_legacy_config_board_write_lands_in_output_config(self, api):
        _settings().set_boards([_v3_board()])
        response = api.put("/config/board", json={"host": "192.0.2.77", "local_api_key": "***"})
        assert response.status_code == 200, response.text
        config = _stored()[0]["output_config"]
        assert (config["host"], config["local_api_key"]) == ("192.0.2.77", LOCAL_KEY)

    def test_merge_without_a_stored_board_lets_the_flat_half_win(self):
        incoming = {"host": "192.0.2.1", "output_config": {"host": "192.0.2.2"}}
        assert merge_board_write(incoming, None) is incoming


# ---------------------------------------------------------------------------
# 5. The runtime signature follows output + output_config
# ---------------------------------------------------------------------------


class TestConfigSignature:
    def test_a_v3_flat_board_and_its_v4_form_sign_alike(self):
        from src.main import DisplayService

        v3 = _v3_board()
        v4 = copy.deepcopy(v3)
        migrate_board_to_v4(v4)
        assert DisplayService._config_signature(v3) == DisplayService._config_signature(v4)

    @pytest.mark.parametrize(
        ("key", "value"),
        [("host", "192.0.2.11"), ("port", 7001), ("local_api_key", "other"), ("api_mode", "cloud")],
    )
    def test_an_output_config_edit_rebuilds_the_runtime(self, key, value):
        from src.main import DisplayService

        board = _v3_board()
        migrate_board_to_v4(board)
        edited = copy.deepcopy(board)
        edited["output_config"][key] = value
        assert DisplayService._config_signature(board) != DisplayService._config_signature(edited)


# ---------------------------------------------------------------------------
# 6. A v3 settings backup restores onto v4 and migrates on load
# ---------------------------------------------------------------------------


def test_a_v3_backup_restores_onto_this_build_and_migrates_on_load(_isolated_data_dir, monkeypatch):
    from src.backup.service import BACKUP_FILE_MARKER, BACKUP_SCHEMA_VERSION, BackupService
    from src.settings.service import get_settings_service
    from tests.conftest import _drop_all_singletons

    fixture = UPGRADE_FIXTURES / "v9_10_schema3_multi_board"
    v3 = json.loads((fixture / "settings.json").read_text())
    _isolated_data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fixture / "config.json", _isolated_data_dir / "config.json")
    get_settings_service()  # a running v4 install
    backup = {BACKUP_FILE_MARKER: True, "schema_version": BACKUP_SCHEMA_VERSION, "data": {"settings": v3}}

    BackupService(data_dir=_isolated_data_dir).import_from_dict(backup, reinstall_plugins=False)
    _drop_all_singletons()
    boards = get_settings_service().get_board_settings().boards

    on_disk = json.loads((_isolated_data_dir / "settings.json").read_text())
    assert on_disk["schema_version"] == CURRENT_SETTINGS_SCHEMA_VERSION
    assert [b["output"] for b in boards] == ["vestaboard"] * 4 + ["fiestapanel"]
    flat = [board_view(b) for b in boards]
    want = [(b["api_mode"], b["host"], b["local_api_key"], b["cloud_key"], b["note_array_token"])
            for b in v3["board"]["boards"]]  # fmt: skip
    assert [(b["api_mode"], b["host"], b["local_api_key"], b["cloud_key"], b["note_array_token"]) for b in flat] == want
