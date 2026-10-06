"""Settings v6: each display owns its transition (settings reorg, PR C).

What this module pins, in order:

1. the v5 -> v6 migration copies the install-wide ``transitions`` block
   (strategy, step interval, step size) onto every board without its own
   choice, then deletes the block; moves the beta flags
   (``transition_plugins_enabled``, ``output_plugins_enabled``) into the
   ``plugins`` section and deletes ``beta``; is idempotent and logs its count;
2. a v5 file loads at v6 with its pre-migration snapshot in
   ``settings.json.v5_backup``, and a saved file carries neither block;
3. the runtime reads only the board: strategy, step interval and step size
   are the display's, never an install-wide value;
4. a page's own transition wins, field by field, and falls back to its
   display's;
5. new displays get a transition of their own;
6. ``GET/PUT /settings/transitions`` survive as a deprecated shim on the
   first display, the beta endpoint is gone, and the flags live under
   ``/settings/plugins``.
"""

from __future__ import annotations

import copy
import json
import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.settings.service import page_transition

VESTA = {"id": "vb", "name": "Kitchen", "device_type": "flagship", "output": "vestaboard"}
PANEL = {"id": "tv", "name": "Lounge", "device_type": "panel", "grid_rows": 6, "grid_cols": 22, "output": "fiestapanel"}
PIXOO = {
    "id": "px",
    "name": "Desk",
    "device_type": "panel",
    "grid_rows": 8,
    "grid_cols": 10,
    "output": "divoom_pixoo",
    "device_model": "divoom_pixoo64",
}


def _v5_data(boards: list[dict], transitions: dict | None = None, beta: dict | None = None, **extra) -> dict:
    data: dict = {"schema_version": 5, "board": {"board_type": "black", "boards": copy.deepcopy(boards)}}
    if transitions is not None:
        data["transitions"] = transitions
    if beta is not None:
        data["beta"] = beta
    data.update(extra)
    return data


INSTALL = {"strategy": "diagonal", "step_interval_ms": 40, "step_size": 2}


@pytest.fixture
def no_env_transition(monkeypatch):
    """The legacy env/config.json transition values, all unset."""
    import src.settings.service as service

    monkeypatch.setattr(service, "_legacy_env_transition", lambda: (None, None, None))


# ---------------------------------------------------------------------------
# 1. The migration
# ---------------------------------------------------------------------------


class TestMigrateV5ToV6:
    def test_the_install_transition_is_copied_onto_a_board_without_a_choice(self):
        from src.settings.service import _migrate_v5_to_v6

        data = _v5_data([VESTA], INSTALL)
        _migrate_v5_to_v6(data)
        board = data["board"]["boards"][0]
        assert (board["transition"], board["transition_step_interval_ms"], board["transition_step_size"]) == (
            "diagonal",
            40,
            2,
        )

    def test_the_install_block_is_deleted(self):
        from src.settings.service import _migrate_v5_to_v6

        data = _v5_data([VESTA], INSTALL)
        _migrate_v5_to_v6(data)
        assert "transitions" not in data

    def test_a_board_own_choice_is_kept_and_gains_the_install_speed(self):
        """The speed was always the install's, even for a display with its own style."""
        from src.settings.service import _migrate_v5_to_v6

        data = _v5_data([{**VESTA, "transition": "row"}], INSTALL)
        _migrate_v5_to_v6(data)
        board = data["board"]["boards"][0]
        assert (board["transition"], board["transition_step_interval_ms"], board["transition_step_size"]) == (
            "row",
            40,
            2,
        )

    def test_no_install_strategy_is_none_on_a_split_flap_board(self):
        from src.settings.service import _migrate_v5_to_v6

        data = _v5_data([VESTA, PANEL], {"strategy": None, "step_interval_ms": None, "step_size": None})
        _migrate_v5_to_v6(data)
        for board in data["board"]["boards"]:
            assert board["transition"] == "none"
            assert "transition_step_interval_ms" not in board
            assert "transition_step_size" not in board

    def test_an_output_plugin_board_without_a_choice_keeps_its_device_default(self):
        """Unset on an LED board meant its model's default (a flip where it can
        show one), whatever the install's strategy: the migration must not turn
        that into "none"."""
        from src.settings.service import _migrate_v5_to_v6

        data = _v5_data([PIXOO], {"strategy": None, "step_interval_ms": None, "step_size": None})
        _migrate_v5_to_v6(data)
        assert "transition" not in data["board"]["boards"][0]

    def test_an_output_plugin_board_gets_a_non_null_install_strategy_verbatim(self):
        from src.settings.service import _migrate_v5_to_v6

        data = _v5_data([PIXOO], {"strategy": "plugin:typewriter", "step_interval_ms": 50, "step_size": None})
        _migrate_v5_to_v6(data)
        board = data["board"]["boards"][0]
        assert board["transition"] == "plugin:typewriter"
        assert board["transition_step_interval_ms"] == 50

    def test_a_board_speed_of_its_own_is_kept(self):
        from src.settings.service import _migrate_v5_to_v6

        data = _v5_data([{**VESTA, "transition_step_interval_ms": 90}], INSTALL)
        _migrate_v5_to_v6(data)
        assert data["board"]["boards"][0]["transition_step_interval_ms"] == 90

    def test_beta_flags_move_into_plugins(self):
        from src.settings.service import _migrate_v5_to_v6

        data = _v5_data(
            [VESTA],
            INSTALL,
            beta={"transition_plugins_enabled": True, "output_plugins_enabled": True},
            plugins={"auto_update": False},
        )
        _migrate_v5_to_v6(data)
        assert "beta" not in data
        assert data["plugins"] == {
            "auto_update": False,
            "transition_plugins_enabled": True,
            "output_plugins_enabled": True,
        }

    def test_a_file_without_a_plugins_section_gets_one_for_the_flags(self):
        from src.settings.service import _migrate_v5_to_v6

        data = _v5_data([VESTA], INSTALL, beta={"transition_plugins_enabled": True})
        _migrate_v5_to_v6(data)
        assert data["plugins"] == {"transition_plugins_enabled": True}

    def test_it_counts_and_is_idempotent(self):
        from src.settings.service import _migrate_v5_to_v6

        data = _v5_data([VESTA, {**PANEL, "transition": "row"}], INSTALL, beta={"transition_plugins_enabled": False})
        # Two boards stamped, the install block removed, the beta block moved.
        assert _migrate_v5_to_v6(data) == 4
        once = copy.deepcopy(data)
        assert _migrate_v5_to_v6(data) == 0
        assert data == once

    def test_a_file_without_the_block_gives_split_flap_boards_none(self):
        """Every save wrote the block, so a file without one is hand-made:
        nothing to copy, and the migration never reads the environment
        (re-reading it on a re-run would not be idempotent)."""
        from src.settings.service import _migrate_v5_to_v6

        data = _v5_data([VESTA, PIXOO])
        assert _migrate_v5_to_v6(data) == 1
        vb, px = data["board"]["boards"]
        assert vb["transition"] == "none"
        assert "transition" not in px

    def test_a_devices_era_board_section_is_materialized_to_keep_a_strategy(self):
        from src.settings.service import _migrate_v5_to_v6

        data = {"schema_version": 5, "transitions": INSTALL, "board": {"board_type": "black", "devices": ["note"]}}
        _migrate_v5_to_v6(data)
        boards = data["board"]["boards"]
        assert [(b["device_type"], b["transition"]) for b in boards] == [("note", "diagonal")]

    def test_it_is_the_registered_v6_migration(self):
        from src.settings.service import CURRENT_SETTINGS_SCHEMA_VERSION, MIGRATIONS, _migrate_v5_to_v6

        assert CURRENT_SETTINGS_SCHEMA_VERSION == 6
        assert MIGRATIONS[-1] == (6, _migrate_v5_to_v6)


# ---------------------------------------------------------------------------
# 2. Loading and saving
# ---------------------------------------------------------------------------


def test_a_v5_file_loads_at_v6_with_a_backup(tmp_path, caplog):
    from src.settings.service import SettingsService

    path = tmp_path / "settings.json"
    path.write_text(json.dumps(_v5_data([VESTA], INSTALL, beta={"transition_plugins_enabled": True})))
    v5 = path.read_bytes()

    with caplog.at_level(logging.INFO, logger="src.settings.service"):
        service = SettingsService(settings_file=str(path))

    assert "Settings schema migration v5->v6: 3 change(s) applied" in caplog.text
    assert (tmp_path / "settings.json.v5_backup").read_bytes() == v5
    on_disk = json.loads(path.read_text())
    assert on_disk["schema_version"] == 6
    assert "transitions" not in on_disk and "beta" not in on_disk
    assert on_disk["board"]["boards"][0]["transition"] == "diagonal"
    assert service.get_plugin_settings().transition_plugins_enabled is True


def test_a_saved_file_has_no_install_transition_or_beta_block(tmp_path, no_env_transition):
    from src.settings.service import SettingsService

    path = tmp_path / "settings.json"
    service = SettingsService(settings_file=str(path))
    service._save_to_file()
    on_disk = json.loads(path.read_text())
    assert "transitions" not in on_disk
    assert "beta" not in on_disk
    assert set(on_disk["plugins"]) == {"auto_update", "transition_plugins_enabled", "output_plugins_enabled"}


# ---------------------------------------------------------------------------
# 3. The runtime reads only the board
# ---------------------------------------------------------------------------


def _service_at_v6(tmp_path, boards: list[dict]):
    from src.settings.service import SettingsService

    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema_version": 6, "board": {"board_type": "black", "boards": boards}}))
    return SettingsService(settings_file=str(path))


class TestRuntimeReadsTheBoard:
    def test_each_display_runs_its_own_speed(self, tmp_path):
        svc = _service_at_v6(
            tmp_path,
            [
                {**VESTA, "transition": "column", "transition_step_interval_ms": 40, "transition_step_size": 2},
                {**PANEL, "transition": "row", "transition_step_interval_ms": 90, "transition_step_size": 3},
            ],
        )
        vb, tv = svc.get_transition_settings("vb"), svc.get_transition_settings("tv")
        assert (vb.strategy, vb.step_interval_ms, vb.step_size) == ("column", 40, 2)
        assert (tv.strategy, tv.step_interval_ms, tv.step_size) == ("row", 90, 3)

    def test_a_stale_install_block_is_ignored(self, tmp_path):
        """A hand-edited v6 file that still carries the old block: the board wins."""
        from src.settings.service import SettingsService

        path = tmp_path / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 6,
                    "transitions": {"strategy": "random", "step_interval_ms": 5, "step_size": 9},
                    "board": {"board_type": "black", "boards": [{**VESTA, "transition": "none"}]},
                }
            )
        )
        resolved = SettingsService(settings_file=str(path)).get_transition_settings("vb")
        assert (resolved.strategy, resolved.step_interval_ms, resolved.step_size) == (None, None, None)

    def test_no_board_id_is_the_first_display(self, tmp_path):
        svc = _service_at_v6(tmp_path, [{**VESTA, "transition": "row"}, {**PANEL, "transition": "column"}])
        assert svc.get_transition_settings().strategy == "row"

    def test_an_unknown_display_reads_the_first(self, tmp_path):
        """A runtime key that is no board id (DisplayService's ``__primary__``)
        is the first display, as the engine's primary runtime is."""
        svc = _service_at_v6(tmp_path, [{**VESTA, "transition": "row"}])
        assert svc.get_transition_settings("missing").strategy == "row"

    def test_an_unset_split_flap_choice_is_none(self, tmp_path):
        svc = _service_at_v6(tmp_path, [VESTA])
        assert svc.get_transition_settings("vb").strategy is None


# ---------------------------------------------------------------------------
# 4. A page's override falls back to its display's choice
# ---------------------------------------------------------------------------


class TestPageOverride:
    def _display(self):
        from src.settings.service import TransitionSettings

        return TransitionSettings(strategy="column", step_interval_ms=40, step_size=2)

    def test_a_page_without_an_override_runs_the_display_transition(self):
        page = SimpleNamespace(transition_strategy=None, transition_interval_ms=None, transition_step_size=None)
        resolved = page_transition(self._display(), page)
        assert (resolved.strategy, resolved.step_interval_ms, resolved.step_size) == ("column", 40, 2)

    def test_a_page_override_wins_field_by_field(self):
        page = SimpleNamespace(transition_strategy="row", transition_interval_ms=None, transition_step_size=5)
        resolved = page_transition(self._display(), page)
        assert (resolved.strategy, resolved.step_interval_ms, resolved.step_size) == ("row", 40, 5)

    def test_a_page_interval_of_zero_is_an_override(self):
        page = SimpleNamespace(transition_strategy=None, transition_interval_ms=0, transition_step_size=None)
        assert page_transition(self._display(), page).step_interval_ms == 0


# ---------------------------------------------------------------------------
# 5. New displays
# ---------------------------------------------------------------------------


class TestNewDisplays:
    def test_a_new_split_flap_display_starts_with_none(self, tmp_path, no_env_transition):
        svc = _service_at_v6(tmp_path, [{**VESTA, "transition": "row"}])
        svc.add_board({"device_type": "note"})
        assert svc.get_board_settings().boards[-1]["transition"] == "none"

    def test_a_new_split_flap_display_starts_with_the_env_default(self, tmp_path, monkeypatch):
        import src.settings.service as service

        monkeypatch.setattr(service, "_legacy_env_transition", lambda: ("column", 25, 3))
        svc = _service_at_v6(tmp_path, [{**VESTA, "transition": "row"}])
        svc.add_board({"device_type": "note"})
        board = svc.get_board_settings().boards[-1]
        assert (board["transition"], board["transition_step_interval_ms"], board["transition_step_size"]) == (
            "column",
            25,
            3,
        )

    def test_a_new_led_display_starts_with_none(self, tmp_path, monkeypatch):
        import src.settings.service as service

        monkeypatch.setattr(service, "_legacy_env_transition", lambda: ("column", 25, 3))
        svc = _service_at_v6(tmp_path, [{**VESTA, "transition": "row"}])
        svc.add_board(dict(PIXOO, id="px2"))
        board = svc.get_board_settings().boards[-1]
        assert board["transition"] == "none"
        assert "transition_step_interval_ms" not in board

    def test_a_display_choice_given_at_creation_is_kept(self, tmp_path, no_env_transition):
        svc = _service_at_v6(tmp_path, [{**VESTA, "transition": "row"}])
        svc.add_board({"device_type": "note", "transition": "random", "transition_step_size": 4})
        board = svc.get_board_settings().boards[-1]
        assert (board["transition"], board["transition_step_size"]) == ("random", 4)

    def test_the_first_boot_board_has_a_transition(self, tmp_path, no_env_transition):
        from src.settings.service import SettingsService

        svc = SettingsService(settings_file=str(tmp_path / "settings.json"))
        assert svc.get_board_settings().boards[0]["transition"] == "none"


class TestBoardSpeedFields:
    def test_speed_fields_round_trip(self):
        from src.devices import BoardInstance

        data = BoardInstance.from_dict(
            {**VESTA, "transition": "row", "transition_step_interval_ms": 40, "transition_step_size": 2}
        ).to_dict()
        assert (data["transition_step_interval_ms"], data["transition_step_size"]) == (40, 2)

    @pytest.mark.parametrize("bad", [-1, "fast", True, 1.5])
    def test_a_bad_interval_is_unset(self, bad):
        from src.devices import BoardInstance

        assert (
            BoardInstance.from_dict({**VESTA, "transition_step_interval_ms": bad}).transition_step_interval_ms is None
        )

    @pytest.mark.parametrize("bad", [0, -2, "big", False])
    def test_a_bad_step_size_is_unset(self, bad):
        from src.devices import BoardInstance

        assert BoardInstance.from_dict({**VESTA, "transition_step_size": bad}).transition_step_size is None

    def test_an_interval_of_zero_is_kept(self):
        from src.devices import BoardInstance

        assert BoardInstance.from_dict({**VESTA, "transition_step_interval_ms": 0}).transition_step_interval_ms == 0


# ---------------------------------------------------------------------------
# 6. The API
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    from src.api_server import app

    return TestClient(app)


def _first_board(client) -> dict:
    return client.get("/settings/board").json()["boards"][0]


class TestTransitionShim:
    def test_put_sets_the_first_display(self, client):
        response = client.put("/settings/transitions", json={"strategy": "row", "step_interval_ms": 30})
        assert response.status_code == 200
        board = _first_board(client)
        assert (board["transition"], board["transition_step_interval_ms"]) == ("row", 30)

    def test_a_null_strategy_is_none_on_the_first_display(self, client):
        client.put("/settings/transitions", json={"strategy": "row"})
        client.put("/settings/transitions", json={"strategy": None})
        assert _first_board(client)["transition"] == "none"

    def test_get_reads_the_first_display(self, client):
        client.put("/settings/transitions", json={"strategy": "diagonal", "step_size": 3})
        body = client.get("/settings/transitions").json()
        assert (body["strategy"], body["step_size"]) == ("diagonal", 3)

    def test_an_omitted_field_is_left_alone(self, client):
        client.put("/settings/transitions", json={"strategy": "row", "step_size": 3})
        client.put("/settings/transitions", json={"step_interval_ms": 10})
        board = _first_board(client)
        assert (board["transition"], board["transition_step_size"], board["transition_step_interval_ms"]) == (
            "row",
            3,
            10,
        )

    def test_the_routes_are_marked_deprecated(self, client):
        from src.settings.routes import get_transition_settings, router, update_transition_settings

        deprecated = {
            route.endpoint: route.deprecated for route in router.routes if route.path == "/settings/transitions"
        }
        assert deprecated == {get_transition_settings: True, update_transition_settings: True}


class TestFlagsLeaveBeta:
    def test_the_beta_endpoint_is_a_deprecated_alias(self, client):
        response = client.get("/settings/beta")
        assert response.status_code == 200
        assert response.headers["Deprecation"] == "true"

    def test_plugin_settings_carry_the_flags(self, client):
        body = client.get("/settings/plugins").json()
        assert body == {"auto_update": True, "transition_plugins_enabled": False, "output_plugins_enabled": False}

    def test_put_plugin_settings_toggles_a_flag(self, client):
        response = client.put("/settings/plugins", json={"transition_plugins_enabled": True})
        assert response.status_code == 200
        assert response.json()["transition_plugins_enabled"] is True
        from src.settings.service import get_settings_service

        assert get_settings_service().get_plugin_settings().transition_plugins_enabled is True

    def test_a_flag_must_be_a_bool(self, client):
        assert client.put("/settings/plugins", json={"output_plugins_enabled": "yes"}).status_code == 422

    def test_all_settings_has_no_beta_block(self, client):
        body = client.get("/settings/all").json()
        assert "beta" not in body
        assert body["plugins"]["transition_plugins_enabled"] is False

    def test_a_plugin_choice_needs_the_flag(self, client):
        board = _first_board(client)
        response = client.put("/settings/board", json={"boards": [{**board, "transition": "plugin:typewriter"}]})
        assert response.status_code == 400
        client.put("/settings/plugins", json={"transition_plugins_enabled": True})
        response = client.put("/settings/board", json={"boards": [{**board, "transition": "plugin:typewriter"}]})
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 7. End to end: an upgraded install's page sends run the display's transition
# ---------------------------------------------------------------------------

PAGE_ID = "00000000-0000-4000-8000-000000000801"


def _last_local_payload(wire) -> dict:
    posts = [c for c in wire.take() if c["method"] == "POST" and c["url"].endswith("/local-api/message")]
    assert posts, "nothing reached the board"
    return posts[-1]["json"]


@pytest.mark.parametrize(
    ("page_override", "expected"),
    [
        ({}, ("diagonal", 40, 2)),
        ({"transition_strategy": "row", "transition_step_size": 5}, ("row", 40, 5)),
    ],
    ids=["no-override", "override-wins-field-by-field"],
)
def test_a_page_send_runs_the_display_transition_unless_the_page_sets_one(
    _isolated_data_dir, monkeypatch, page_override, expected
):
    from src.api_server import app
    from tests.test_upgrade_fixtures import boot
    from tests.test_wire_goldens import install_floor_clock, install_wire_recorder

    wire = install_wire_recorder(monkeypatch)
    install_floor_clock(monkeypatch)
    booted = boot("v10_beta_schema5_install_transition", _isolated_data_dir)
    api = TestClient(app)
    if page_override:
        assert api.put(f"/pages/{PAGE_ID}", json=page_override).status_code == 200
    wire.take()

    response = api.post(f"/pages/{PAGE_ID}/send", json={"board_id": booted.boards[0]["id"]})

    assert response.status_code == 200, response.text
    payload = _last_local_payload(wire)
    assert (payload.get("strategy"), payload.get("step_interval_ms"), payload.get("step_size")) == expected
