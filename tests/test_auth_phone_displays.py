"""H21a: a phone adds, changes and removes displays, without moving a stored key.

Tier 1 for the phone (``control``): add a display (``/settings/board/add`` and
``/outputs/{id}/boards``, every display type), change displays
(``PUT /settings/board``), remove one, detect a board's size, and the display,
transition, polling and location settings.

The secret rule: a phone that changes a saved display's connection must type
its key again. Echoing ``"***"`` or leaving the key out is refused with
``400 key_required``, for a save and for a device action run on edited
settings. A browser keeps today's behaviour.
"""

import json

import pytest
from fastapi.testclient import TestClient

from src.ai.phone_tools import ALLOWED, DENIED, tier_for
from src.api_server import app
from src.auth import routes as routes_module
from src.auth import scopes
from src.auth import service as auth_module
from src.outputs import routes as output_routes
from src.settings.service import get_settings_service

PASSWORD = "correct-password"
IOS = {"client_id": "fiestaboard-ios", "device_name": "Maya's iPhone", "app_version": "1.0"}
TV = {"client_id": "fiestaboard-tvos", "device_name": "Living room", "app_version": "1.0"}
KEY = "test_local_key_stored"

KITCHEN = {
    "id": "kitchen",
    "name": "Kitchen",
    "device_type": "flagship",
    "api_mode": "local",
    "host": "192.168.1.20",
    "local_api_key": KEY,
}
HALL = {"id": "hall", "name": "Hall", "device_type": "flagship", "api_mode": "cloud"}

TIER1 = [
    ("GET", "/settings/board", None),
    ("POST", "/settings/board/add", {"device_type": "note", "name": "Office"}),
    ("DELETE", "/settings/board/hall", None),
    ("POST", "/settings/board/kitchen/detect-size", None),
    ("POST", "/outputs/vestaboard/boards", {"device_model": "flagship", "output_config": {}}),
    ("GET", "/settings/display", None),
    ("PUT", "/settings/display", {}),
    ("GET", "/settings/transitions", None),
    ("PUT", "/settings/transitions", {}),
    ("GET", "/settings/polling", None),
    ("PUT", "/settings/polling", {}),
    ("GET", "/settings/location", None),
    ("PUT", "/settings/location", {}),
]

STILL_DENIED = [
    ("POST", "/outputs/vestaboard/install", {}),
    ("GET", "/config/board", None),
    ("PUT", "/config/board", {}),
    ("DELETE", "/config/board", None),
    ("POST", "/config/board/scan", {}),
    ("POST", "/config/board/enable-local-api", {}),
    ("GET", "/settings/mqtt", None),
    ("PUT", "/settings/mqtt", {}),
    ("POST", "/settings/hdmi-kiosk", {}),
]


@pytest.fixture
def auth(tmp_path, monkeypatch):
    svc = auth_module.AuthService(tmp_path / "auth.json")
    svc.create_initial_user("admin", PASSWORD)
    svc.sessions.set_enrollment(True)
    monkeypatch.setattr(auth_module, "_service", svc)
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")
    monkeypatch.delenv("FIESTABOARD_MCP_TOKEN", raising=False)
    routes_module._FAILED_ATTEMPTS.clear()
    yield svc
    routes_module._FAILED_ATTEMPTS.clear()


@pytest.fixture
def boards(monkeypatch):
    monkeypatch.setattr("src.settings.routes.reinitialize_board_clients", lambda: None)
    monkeypatch.setattr(output_routes, "reinitialize_board_clients", lambda: None)
    get_settings_service().set_boards([dict(KITCHEN), dict(HALL)])
    return get_settings_service()


@pytest.fixture
def actions(monkeypatch):
    ran = []

    async def run_saved_action(board_id, action, *, inputs, output_config=None, client_hint=None):
        ran.append((board_id, action, output_config))
        return {"status": "ok", "message": "stubbed"}

    monkeypatch.setattr(output_routes, "run_saved_action", run_saved_action)
    return ran


def bearer(metadata):
    response = TestClient(app).post("/auth/device/login", json={**metadata, "username": "admin", "password": PASSWORD})
    token = response.json()["access_token"]
    return TestClient(app, headers={"Authorization": "Bearer " + token}, raise_server_exceptions=False)


@pytest.fixture
def phone(auth, boards):
    return bearer(IOS)


def stored(board_id="kitchen"):
    return next(b for b in get_settings_service().get_board_settings().boards if b.get("id") == board_id)


def stored_key():
    return json.dumps(stored())


def echoed_boards(client):
    """What a phone sends back after reading the list: masks included."""
    return client.get("/settings/board").json()["boards"]


# --- Reach ---------------------------------------------------------------------------


@pytest.mark.parametrize(("method", "path", "body"), TIER1)
def test_display_routes_are_tier_one(phone, method, path, body):
    response = phone.request(method, path, json=body)
    assert response.status_code not in (401, 403), (path, response.status_code, response.text)


@pytest.mark.parametrize(("method", "path", "body"), STILL_DENIED)
def test_outputs_install_and_raw_board_config_stay_browser_only(phone, method, path, body):
    assert phone.post("/auth/device/elevate", json={"password": PASSWORD}).status_code == 200
    response = phone.request(method, path, json=body)
    assert response.status_code == 403 and response.json()["error"] == "forbidden", path


def test_a_tv_reaches_none_of_it(auth, boards):
    tv = bearer(TV)
    for method, path, body in TIER1:
        assert tv.request(method, path, json=body).status_code == 403, path


def test_phone_adds_and_removes_a_display(phone):
    added = phone.post("/settings/board/add", json={"device_type": "note", "name": "Office"})
    assert added.status_code == 201, added.text
    new_id = next(b["id"] for b in added.json()["boards"] if b["name"] == "Office")
    assert phone.delete(f"/settings/board/{new_id}").status_code == 200
    assert all(b.get("id") != new_id for b in get_settings_service().get_board_settings().boards)


def test_phone_reads_displays_masked(phone):
    body = phone.get("/settings/board").text
    assert KEY not in body


# --- Key re-entry on a connection change --------------------------------------------------


def moved(client, **changes):
    boards = echoed_boards(client)
    for board in boards:
        if board["id"] == "kitchen":
            board.update(changes)
    return client.put("/settings/board", json={"boards": boards})


def test_rename_with_masks_keeps_the_key(phone):
    response = moved(phone, name="Kitchen 2")
    assert response.status_code == 200, response.text
    assert stored()["name"] == "Kitchen 2" and KEY in stored_key()


@pytest.mark.parametrize("changes", [{"host": "203.0.113.50"}, {"host": "192.168.1.99"}, {"port": 8080}])
def test_moving_a_display_with_its_key_masked_is_refused(phone, changes):
    response = moved(phone, **changes)
    assert response.status_code == 400, response.text
    assert response.json()["error"] == "key_required"
    assert "203.0.113.50" not in stored_key() and '"port": 8080' not in stored_key()
    assert KEY in stored_key()


def test_moving_a_display_with_its_key_left_out_drops_the_key(phone):
    # Leaving the key out is not a leak: the save keeps no stored key to send.
    boards = echoed_boards(phone)
    for board in boards:
        if board["id"] == "kitchen":
            board["host"] = "203.0.113.50"
            board.pop("local_api_key", None)
            if isinstance(board.get("output_config"), dict):
                board["output_config"].pop("local_api_key", None)
                board["output_config"]["host"] = "203.0.113.50"
    response = phone.put("/settings/board", json={"boards": boards})
    assert response.status_code == 200, response.text
    assert KEY not in stored_key()


def test_moving_a_display_with_its_key_typed_again_is_allowed(phone):
    boards = echoed_boards(phone)
    for board in boards:
        if board["id"] == "kitchen":
            board["host"] = "192.168.1.99"
            board["local_api_key"] = "test_retyped_key"
            if isinstance(board.get("output_config"), dict):
                board["output_config"]["host"] = "192.168.1.99"
                board["output_config"]["local_api_key"] = "test_retyped_key"
    response = phone.put("/settings/board", json={"boards": boards})
    assert response.status_code == 200, response.text
    assert "test_retyped_key" in stored_key() and KEY not in stored_key()


def test_browser_is_not_held_to_key_re_entry(auth, boards):
    browser = TestClient(app)
    assert browser.post("/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 200
    response = moved(browser, host="192.168.1.99")
    assert response.status_code == 200, response.text


# --- Device actions on edited settings -----------------------------------------------------


def test_action_on_stored_settings_runs(phone, actions):
    response = phone.post("/boards/kitchen/actions/test_connection", json={})
    assert response.status_code == 200, response.text
    assert actions == [("kitchen", "test_connection", None)]


@pytest.mark.parametrize(
    "edits",
    [
        {"host": "203.0.113.50"},
        {"host": "203.0.113.50", "local_api_key": "***"},
    ],
)
def test_action_on_moved_settings_without_the_key_is_refused(phone, actions, edits):
    response = phone.post("/boards/kitchen/actions/test_connection", json={"output_config": edits})
    assert response.status_code == 400 and response.json()["error"] == "key_required", response.text
    assert actions == []


def test_action_on_moved_settings_with_the_key_runs(phone, actions):
    edits = {"host": "192.168.1.99", "local_api_key": "test_retyped_key"}
    response = phone.post("/boards/kitchen/actions/test_connection", json={"output_config": edits})
    assert response.status_code == 200, response.text
    assert len(actions) == 1


def test_browser_action_is_unchanged(auth, boards, actions):
    browser = TestClient(app)
    assert browser.post("/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 200
    response = browser.post("/boards/kitchen/actions/test_connection", json={"output_config": {"host": "192.168.1.99"}})
    assert response.status_code == 200 and len(actions) == 1


def test_a_non_string_secret_is_compared_exactly():
    from src.settings.phone_displays import moves_a_stored_secret

    stored = {**KITCHEN, "local_api_key": "1234567"}
    # Moving the host with a key that merely contains the stored digits is still a move.
    edit = {**stored, "host": "203.0.113.50", "local_api_key": "***"}
    assert moves_a_stored_secret(edit, stored)
    retyped = {**stored, "host": "203.0.113.50", "local_api_key": "1234567"}
    assert not moves_a_stored_secret(retyped, stored)
    # A secret-shaped value elsewhere in the body does not count as re-entry.
    decoy = {**stored, "host": "203.0.113.50", "local_api_key": "***", "name": "key 1234567 x"}
    assert moves_a_stored_secret(decoy, stored)


# --- Only connection fields ask for the key (tiles, plugin outputs) ----------------------

TILE_KEYS = ("test_tile_key_a", "test_tile_key_b")
ARRAY = {
    "id": "wall",
    "name": "Wall",
    "device_type": "note_array",
    "api_mode": "local",
    "notes_wide": 2,
    "notes_tall": 1,
    "tiles": [
        {"row": 0, "col": 0, "host": "192.168.1.41", "port": 7000, "local_api_key": TILE_KEYS[0], "enabled": True},
        {"row": 0, "col": 1, "host": "192.168.1.42", "port": 7000, "local_api_key": TILE_KEYS[1], "enabled": True},
    ],
}


@pytest.fixture
def wall(boards):
    boards.set_boards([dict(KITCHEN), dict(HALL), json.loads(json.dumps(ARRAY))])


def stored_tiles():
    tiles = stored("wall").get("output_config", {}).get("tiles") or stored("wall").get("tiles")
    return {(t["host"], t.get("local_api_key")) for t in tiles}


def edited_wall(client, edit):
    boards = echoed_boards(client)
    for board in boards:
        if board["id"] == "wall":
            for tiles in (board.get("tiles"), (board.get("output_config") or {}).get("tiles")):
                if tiles:
                    edit(tiles)
    return client.put("/settings/board", json={"boards": boards})


def _swap(tiles):
    tiles[0]["col"], tiles[1]["col"] = 1, 0


def _switch_off(tiles):
    tiles[1]["enabled"] = False


def test_swapping_tiles_keeps_each_key_with_its_host(phone, wall):
    response = edited_wall(phone, _swap)
    assert response.status_code == 200, response.text
    assert stored_tiles() == {("192.168.1.41", TILE_KEYS[0]), ("192.168.1.42", TILE_KEYS[1])}


def test_switching_a_tile_off_needs_no_key(phone, wall):
    assert edited_wall(phone, _switch_off).status_code == 200


def _move_tile(tiles):
    tiles[1]["host"] = "203.0.113.60"


def _move_tile_port(tiles):
    tiles[0]["port"] = 7001


@pytest.mark.parametrize("edit", [_move_tile, _move_tile_port])
def test_moving_a_tile_with_its_key_masked_is_refused(phone, wall, edit):
    response = edited_wall(phone, edit)
    assert response.status_code == 400 and response.json()["error"] == "key_required", response.text
    assert ("192.168.1.42", TILE_KEYS[1]) in stored_tiles()


@pytest.fixture
def recording_output(tmp_path, monkeypatch):
    """A third-party output whose schema declares ``host`` and a secret ``token``."""
    import shutil
    from pathlib import Path

    from src.plugins.loader import PluginLoader
    from src.plugins.registry import PluginRegistry

    plugin_id = "recording_output"
    root = tmp_path / "external"
    shutil.copytree(
        Path(__file__).parent / "fixtures" / "plugins" / plugin_id,
        root / plugin_id,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    loader = PluginLoader(plugins_dir=tmp_path / "builtin", external_dirs=[root])
    assert loader.load_plugin(plugin_id) is not None, loader.load_errors
    registry = PluginRegistry(plugins_dir=tmp_path / "builtin")
    registry._loader = loader
    registry._plugins[plugin_id], registry._manifests[plugin_id] = loader.output_plugins[plugin_id]
    monkeypatch.setattr("src.plugins.get_plugin_registry", lambda: registry)
    yield plugin_id
    loader.unload_plugin(plugin_id)


def _plugin_board(output_id, **config):
    from src.devices import BoardInstance

    output_config = {"host": "192.168.1.50", "token": "test_sign_token", "animation": "stream", **config}
    return BoardInstance.from_dict(
        {"id": "sign", "name": "Sign", "device_type": "flagship", "output": output_id, "output_config": output_config}
    ).to_dict()


@pytest.mark.parametrize("edit", [{"animation": "none"}, {"min_interval_ms": 250}, {"wait_for_cancel": True}])
def test_a_plugin_outputs_other_settings_need_no_key(recording_output, edit):
    from src.settings.phone_displays import moves_a_stored_secret

    stored_board = _plugin_board(recording_output)
    incoming = {**stored_board, "output_config": {**stored_board["output_config"], "token": "***", **edit}}
    assert not moves_a_stored_secret(incoming, stored_board)


def test_a_plugin_outputs_host_change_needs_the_key(recording_output):
    from src.settings.phone_displays import moves_a_stored_secret

    stored_board = _plugin_board(recording_output)
    moved = {**stored_board["output_config"], "token": "***", "host": "203.0.113.70"}
    assert moves_a_stored_secret({**stored_board, "output_config": moved}, stored_board)
    retyped = {**moved, "token": "test_sign_token"}
    assert not moves_a_stored_secret({**stored_board, "output_config": retyped}, stored_board)


def test_re_entry_is_compared_type_strictly():
    from src.auth.key_reentry import moves_a_secret

    before = {"host": "192.168.1.20", "pin": 1}
    masked = {"host": "192.168.1.20", "pin": "***"}
    after = {"host": "203.0.113.50", "pin": 1}
    # A boolean true (or a float 1.0) in the request is not the stored integer 1.
    assert moves_a_secret(before, after, masked, {"host": "203.0.113.50", "pin": "***", "enabled": True})
    assert moves_a_secret(before, after, masked, {"host": "203.0.113.50", "pin": "***", "ratio": 1.0})
    assert not moves_a_secret(before, after, masked, {"host": "203.0.113.50", "pin": 1})


def test_a_withheld_config_is_moved_by_any_change():
    from src.auth.key_reentry import moves_a_secret

    before = {"output": "unknown", "output_config": {"addr": "sign-1", "token": "test_token"}}
    masked = {"output": "unknown", "output_config": "***"}
    after = {"output": "unknown", "output_config": {"addr": "sign-2", "token": "test_token"}}
    assert moves_a_secret(before, after, masked, {"output_config": "***"})
    assert not moves_a_secret(before, dict(before), masked, {"output_config": "***"})


# --- The tables ----------------------------------------------------------------------------


def test_scope_rows():
    for method, path, _ in TIER1:
        assert scopes.permits(scopes.CONTROL, method, path), path
        assert not scopes.requires_step_up(scopes.CONTROL, method, path), path
    for method, path, _ in STILL_DENIED:
        assert not scopes.permits(scopes.CONTROL, method, path), path


@pytest.mark.parametrize("category", ["display", "transitions", "polling", "location"])
def test_fiestabot_reaches_the_display_settings_a_phone_reaches(category):
    assert tier_for("update_setting", {"category": category, "values": {}}) == "step_up"


def test_fiestabot_display_tools():
    assert tier_for("add_board", {"device_type": "flagship"}) == ALLOWED
    assert tier_for("remove_board", {"board_id": "b"}) == ALLOWED
    assert tier_for("detect_board_size", {"board_id": "b"}) == ALLOWED
    assert tier_for("create_display", {"output_id": "x"}) == ALLOWED
    assert tier_for("configure_display", {"board_id": "b", "output_config": {}}) == DENIED
    assert tier_for("update_board", {"board_id": "b", "host": "203.0.113.5"}) == DENIED
