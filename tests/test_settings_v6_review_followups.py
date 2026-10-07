"""Settings v6 (per-display transitions), review follow-ups on PR #2217.

1. a bad or gated legacy default never stops a display being added;
2. a page strategy the target display cannot run falls through to the
   display's own, judged from the output's capabilities;
3. an install-wide transition with no board to land on is not dropped;
4. the deprecated ``/settings/transitions`` shim: null means what it meant in
   v5, and a GET -> PUT round-trip changes nothing;
5. a runtime key that is not a board id reads the first display;
6. ``/settings/beta`` and ``update_setting('beta')`` stay as deprecated
   aliases until v11;
7. the step interval is capped at 5000 ms, like a page's;
8. every way a board is born gives it a transition.
"""

from __future__ import annotations

import asyncio
import copy
import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.settings.service import page_transition
from tests.test_settings_v6_per_display_transitions import (
    INSTALL,
    PANEL,
    PIXOO,
    VESTA,
    _first_board,
    _service_at_v6,
    no_env_transition,  # noqa: F401 - fixture
)


@pytest.fixture
def client() -> TestClient:
    from src.api_server import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. A bad legacy default never stops a display being added
# ---------------------------------------------------------------------------


class TestDefaultIsValidated:
    @pytest.mark.parametrize("bad", ["sparkle", "plugin: ", "plugin:typewriter"])
    def test_a_bad_or_gated_env_strategy_falls_back_to_none(self, tmp_path, monkeypatch, caplog, bad):
        import src.settings.service as service

        monkeypatch.setattr(service, "_legacy_env_transition", lambda: (bad, None, None))
        svc = _service_at_v6(tmp_path, [{**VESTA, "transition": "row"}])
        with caplog.at_level(logging.WARNING, logger="src.settings.service"):
            svc.add_board({"device_type": "note"})
        assert svc.get_board_settings().boards[-1]["transition"] == "none"
        assert repr(bad) in caplog.text

    def test_a_gated_plugin_default_is_kept_once_plugins_are_on(self, tmp_path, monkeypatch):
        import src.settings.service as service

        monkeypatch.setattr(service, "_legacy_env_transition", lambda: ("plugin:typewriter", None, None))
        svc = _service_at_v6(tmp_path, [{**VESTA, "transition": "row"}])
        svc.update_plugin_settings({"transition_plugins_enabled": True})
        svc.add_board({"device_type": "note"})
        assert svc.get_board_settings().boards[-1]["transition"] == "plugin:typewriter"

    def test_an_out_of_range_env_speed_is_dropped(self, tmp_path, monkeypatch):
        import src.settings.service as service

        monkeypatch.setattr(service, "_legacy_env_transition", lambda: ("column", 99999, 0))
        svc = _service_at_v6(tmp_path, [{**VESTA, "transition": "row"}])
        svc.add_board({"device_type": "note"})
        board = svc.get_board_settings().boards[-1]
        assert board["transition"] == "column"
        assert "transition_step_interval_ms" not in board and "transition_step_size" not in board

    def test_the_first_boot_board_survives_a_bad_default(self, tmp_path, monkeypatch):
        import src.settings.service as service

        monkeypatch.setattr(service, "_legacy_env_transition", lambda: ("sparkle", None, None))
        svc = service.SettingsService(settings_file=str(tmp_path / "settings.json"))
        assert svc.get_board_settings().boards[0]["transition"] == "none"

    def test_adding_a_board_through_the_api_never_fails_on_the_default(self, client, monkeypatch):
        import src.settings.service as service

        monkeypatch.setattr(service, "_legacy_env_transition", lambda: ("plugin:typewriter", None, None))
        response = client.post("/settings/board/add", json={"device_type": "note"})
        assert response.status_code in (200, 201), response.text
        assert client.get("/settings/board").json()["boards"][-1]["transition"] == "none"

    def test_creating_a_panel_never_fails_on_the_default(self, client, monkeypatch):
        import src.settings.service as service

        monkeypatch.setattr(service, "_legacy_env_transition", lambda: ("sparkle", None, None))
        response = client.post("/panels", json={"name": "Lounge"})
        assert response.status_code in (200, 201), response.text


# ---------------------------------------------------------------------------
# 2. A page strategy the board's driver cannot run falls through to the board's
# ---------------------------------------------------------------------------


def _page(strategy, interval=None, step_size=None):
    return SimpleNamespace(
        transition_strategy=strategy, transition_interval_ms=interval, transition_step_size=step_size
    )


def _driver(natives=(), animation="stream", takes_transitions=False):
    """A stand-in driver: the attributes the runtime reads to pick a transition."""
    return SimpleNamespace(
        native_transitions=frozenset(natives), animation=animation, takes_transitions=takes_transitions
    )


VESTA_DRIVER = _driver(("column", "row", "diagonal"))
PANEL_DRIVER = _driver(())
LED_DRIVER = _driver((), takes_transitions=True)
CLOUD_DRIVER = _driver((), animation="none")


class TestDriverRunsStrategy:
    @pytest.mark.parametrize(
        ("driver", "strategy", "runs"),
        [
            (VESTA_DRIVER, "column", True),
            (VESTA_DRIVER, "random", False),
            (VESTA_DRIVER, "plugin:typewriter", True),
            (VESTA_DRIVER, "flip", False),
            (PANEL_DRIVER, "column", False),
            (PANEL_DRIVER, "plugin:typewriter", True),
            (CLOUD_DRIVER, "plugin:typewriter", False),
            (LED_DRIVER, "fade", True),
            (LED_DRIVER, "column", False),
            (LED_DRIVER, "plugin:typewriter", False),
            (VESTA_DRIVER, "sparkle", False),
        ],
    )
    def test_the_runtime_predicate(self, driver, strategy, runs):
        from src.outputs.transitions import driver_runs_strategy

        assert driver_runs_strategy(driver, strategy) is runs

    def test_a_driver_that_says_nothing_runs_whatever_it_is_asked(self):
        from unittest.mock import Mock

        from src.outputs.transitions import driver_runs_strategy

        assert driver_runs_strategy(Mock(), "column") is True
        assert driver_runs_strategy(None, "column") is True


class TestPageStrategyMustBeRunnable:
    def _display(self, strategy="none"):
        from src.settings.service import TransitionSettings

        return TransitionSettings(strategy=strategy, step_interval_ms=40, step_size=2)

    @pytest.mark.parametrize(
        ("driver", "page_strategy"),
        [(LED_DRIVER, "column"), (LED_DRIVER, "plugin:typewriter"), (VESTA_DRIVER, "flip"), (PANEL_DRIVER, "row")],
        ids=["native-on-led", "plugin-on-led", "led-id-on-split-flap", "native-the-driver-lacks"],
    )
    def test_an_unrunnable_page_strategy_falls_back_to_the_board_and_its_speed(self, driver, page_strategy):
        from src.outputs.transitions import driver_runs_strategy

        page = _page(page_strategy, interval=5, step_size=9)
        resolved = page_transition(self._display(), page, runs=lambda s: driver_runs_strategy(driver, s))
        assert (resolved.strategy, resolved.step_interval_ms, resolved.step_size) == ("none", 40, 2)

    def test_a_runnable_page_strategy_still_wins(self):
        from src.outputs.transitions import driver_runs_strategy

        resolved = page_transition(
            self._display(), _page("column", interval=5), runs=lambda s: driver_runs_strategy(VESTA_DRIVER, s)
        )
        assert (resolved.strategy, resolved.step_interval_ms) == ("column", 5)

    def test_no_driver_to_ask_keeps_the_page_strategy(self):
        assert page_transition(self._display(), _page("column")).strategy == "column"

    def test_transition_settings_carry_nothing_but_the_three_fields(self):
        import dataclasses

        from src.settings.service import TransitionSettings

        assert [f.name for f in dataclasses.fields(TransitionSettings)] == ["strategy", "step_interval_ms", "step_size"]


# ---------------------------------------------------------------------------
# 3. A transition with no board to land on is carried to first boot, never read config.json
# ---------------------------------------------------------------------------


def _config_unreadable(monkeypatch):
    import src.config_manager as config_manager
    import src.settings.service as service

    def refuse(*args, **kwargs):
        raise OSError("config.json unreadable")

    monkeypatch.setattr(config_manager, "get_config_manager", refuse)
    monkeypatch.setattr(service, "_read_legacy_board_connection", refuse)


NO_BOARDS = [
    pytest.param(None, id="no-board-section"),
    pytest.param({"board_type": "black", "boards": [], "devices": ["flagship"]}, id="empty-boards-with-devices"),
    pytest.param({"board_type": "black", "boards": []}, id="empty-boards"),
    pytest.param({"board_type": "black", "devices": ["note"]}, id="devices-era"),
]


class TestNoBoardsToCopyOnto:
    @pytest.mark.parametrize("board", NO_BOARDS)
    def test_the_migration_never_reads_config_json(self, monkeypatch, board):
        import src.settings.service as service

        _config_unreadable(monkeypatch)
        data = {"schema_version": 5, "transitions": INSTALL, "beta": {"transition_plugins_enabled": True}}
        if board is not None:
            data["board"] = copy.deepcopy(board)
        service._migrate_v5_to_v6(data)  # must not raise
        assert data["plugins"]["transition_plugins_enabled"] is True
        assert "transitions" not in data

    @pytest.mark.parametrize("board", NO_BOARDS)
    def test_nothing_is_lost_when_config_json_is_unreadable(self, tmp_path, monkeypatch, board):
        import json

        from src.settings.service import SettingsService

        _config_unreadable(monkeypatch)
        data = {"schema_version": 5, "transitions": INSTALL, "beta": {"transition_plugins_enabled": True}}
        if board is not None:
            data["board"] = copy.deepcopy(board)
        path = tmp_path / "settings.json"
        path.write_text(json.dumps(data))

        svc = SettingsService(settings_file=str(path))

        on_disk = json.loads(path.read_text())
        assert on_disk["schema_version"] == 7  # v6, then v7 (no output-plugin opt-in)
        assert svc.get_plugin_settings().transition_plugins_enabled is True
        first = svc.get_board_settings().boards[0]
        assert (first["transition"], first["transition_step_interval_ms"], first["transition_step_size"]) == (
            "diagonal",
            40,
            2,
        )
        # Persisted, and the hand-off key consumed.
        assert on_disk["board"]["boards"][0]["transition"] == "diagonal"
        assert not any(key.startswith("pending") or "pending" in key for key in on_disk)

    def test_the_first_boot_seed_still_imports_the_connection(self, tmp_path, monkeypatch):
        import json

        import src.settings.service as service
        from src.settings.board_shape import flat_connection

        legacy = {"api_mode": "local", "host": "192.0.2.10", "local_api_key": "test_key", "cloud_key": ""}
        monkeypatch.setattr(service, "_read_legacy_board_connection", lambda: {**legacy, "note_array_token": ""})
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"schema_version": 5, "transitions": INSTALL}))
        svc = service.SettingsService(settings_file=str(path))
        first = svc.get_board_settings().boards[0]
        assert flat_connection(first)["local_api_key"] == "test_key"
        assert first["transition"] == "diagonal"

    def test_nothing_to_copy_leaves_a_missing_board_section_to_first_boot(self):
        from src.settings.service import _migrate_v5_to_v6

        data = {"schema_version": 5, "transitions": {"strategy": None, "step_interval_ms": None, "step_size": None}}
        _migrate_v5_to_v6(data)
        assert "board" not in data

    @pytest.mark.parametrize("label", ["v10_beta_schema5_no_board_section", "v10_beta_schema5_empty_boards"])
    def test_the_upgrade_fixture_runs_the_install_transition(self, _isolated_data_dir, label):
        from tests.test_upgrade_fixtures import boot

        booted = boot(label, _isolated_data_dir)
        resolved = booted.settings.get_transition_settings(booted.boards[0]["id"])
        assert (resolved.strategy, resolved.step_interval_ms, resolved.step_size) == ("diagonal", 40, 2)


# ---------------------------------------------------------------------------
# 4. The deprecated shim: null means what it meant in v5, and round-trips
# ---------------------------------------------------------------------------


class TestShimNullAndRoundTrip:
    def test_null_on_an_led_first_board_is_its_device_default(self, tmp_path):
        svc = _service_at_v6(tmp_path, [{**PIXOO, "transition": "fade"}, VESTA])
        svc.update_transition_settings(strategy=None)
        assert "transition" not in svc.get_board_settings().boards[0]

    def test_null_on_a_split_flap_first_board_is_none(self, tmp_path):
        svc = _service_at_v6(tmp_path, [{**VESTA, "transition": "row"}])
        svc.update_transition_settings(strategy=None)
        assert svc.get_board_settings().boards[0]["transition"] == "none"

    @pytest.mark.parametrize(
        "first",
        [
            {**VESTA, "transition": "none"},
            {**VESTA, "transition": "row", "transition_step_interval_ms": 30, "transition_step_size": 2},
            {**PIXOO, "transition": "none"},
            {**PIXOO, "transition": "fade"},
            PIXOO,
        ],
        ids=["vb-none", "vb-row", "led-none", "led-fade", "led-unset"],
    )
    def test_get_then_put_changes_nothing(self, tmp_path, first):
        from src.devices import BoardInstance

        svc = _service_at_v6(tmp_path, [first])
        # As the store normalizes any write (grid clamps etc.): only the
        # round trip itself is under test.
        before = BoardInstance.from_dict(copy.deepcopy(svc.get_board_settings().boards[0])).to_dict()
        got = svc.get_transition_settings()
        svc.update_transition_settings(
            strategy=got.strategy, step_interval_ms=got.step_interval_ms, step_size=got.step_size
        )
        assert svc.get_board_settings().boards[0] == before

    def test_get_then_put_through_the_api_changes_nothing(self, client):
        client.put("/settings/transitions", json={"strategy": "row", "step_interval_ms": 30})
        before = _first_board(client)
        got = client.get("/settings/transitions").json()
        body = {k: got[k] for k in ("strategy", "step_interval_ms", "step_size")}
        assert client.put("/settings/transitions", json=body).status_code == 200
        assert _first_board(client) == before


# ---------------------------------------------------------------------------
# 5. Only "" and the primary runtime key read the first display
# ---------------------------------------------------------------------------


class TestRuntimeKeysFallBackToTheFirstDisplay:
    @pytest.mark.parametrize("key", ["__primary__", "", None])
    def test_the_primary_keys_read_the_first_display(self, tmp_path, key):
        svc = _service_at_v6(
            tmp_path,
            [{**VESTA, "transition": "row", "transition_step_size": 3}, {**PANEL, "transition": "column"}],
        )
        resolved = svc.get_transition_settings(key)
        assert (resolved.strategy, resolved.step_size) == ("row", 3)

    def test_an_unknown_id_has_no_transition(self, tmp_path):
        svc = _service_at_v6(tmp_path, [{**VESTA, "transition": "row", "transition_step_size": 3}])
        resolved = svc.get_transition_settings("missing")
        assert (resolved.strategy, resolved.step_interval_ms, resolved.step_size) == (None, None, None)

    def test_writing_an_unknown_id_is_refused(self, tmp_path):
        svc = _service_at_v6(tmp_path, [{**VESTA, "transition": "row"}])
        with pytest.raises(ValueError):
            svc._write_board_fields("missing", {"transition": "column"})

    def test_the_display_service_uses_the_shared_primary_key(self):
        from src.main import DisplayService
        from src.settings.service import PRIMARY_RUNTIME_KEY

        assert DisplayService._PRIMARY_FALLBACK_KEY == PRIMARY_RUNTIME_KEY == "__primary__"


# ---------------------------------------------------------------------------
# 6. /settings/beta and update_setting('beta') stay as deprecated aliases
# ---------------------------------------------------------------------------


class TestBetaAlias:
    def test_get_beta_reads_the_plugin_flags_with_a_deprecation_notice(self, client):
        client.put("/settings/plugins", json={"transition_plugins_enabled": True})
        response = client.get("/settings/beta")
        assert response.status_code == 200
        # output_plugins_enabled: always true since settings v7 (no opt-in).
        assert response.json() == {"settings": {"transition_plugins_enabled": True, "output_plugins_enabled": True}}
        assert response.headers["Deprecation"] == "true"
        assert "/api/settings/plugins" in response.headers["Link"]

    def test_put_beta_writes_the_plugin_flags(self, client):
        response = client.put("/settings/beta", json={"transition_plugins_enabled": True})
        assert response.status_code == 200
        assert response.headers["Deprecation"] == "true"
        assert response.json()["settings"]["transition_plugins_enabled"] is True
        assert client.get("/settings/plugins").json()["transition_plugins_enabled"] is True

    def test_put_beta_ignores_auto_update_and_stale_keys(self, client):
        response = client.put("/settings/beta", json={"https_enabled": True, "auto_update": False})
        assert response.status_code == 200
        assert client.get("/settings/plugins").json()["auto_update"] is True

    def test_the_transitions_alias_carries_the_notice_too(self, client):
        response = client.get("/settings/transitions")
        assert response.headers["Deprecation"] == "true"
        assert "/api/settings/board" in response.headers["Link"]

    def test_beta_is_not_back_in_all_settings(self, client):
        assert "beta" not in client.get("/settings/all").json()

    def test_mcp_update_setting_accepts_the_deprecated_beta_category(self):
        from src.ops.executors import update_setting
        from src.settings.service import get_settings_service

        result = asyncio.run(update_setting("beta", {"transition_plugins_enabled": True}))
        assert result.get("status") != "error", result
        assert get_settings_service().get_plugin_settings().transition_plugins_enabled is True


# ---------------------------------------------------------------------------
# 7. The step interval is capped at 5000 ms, like a page's
# ---------------------------------------------------------------------------


class TestIntervalCap:
    def test_the_board_field_is_capped(self):
        from src.devices import BoardInstance

        assert (
            BoardInstance.from_dict({**VESTA, "transition_step_interval_ms": 5000}).transition_step_interval_ms == 5000
        )
        # Stored data above the cap is clamped, never dropped (second review).
        assert (
            BoardInstance.from_dict({**VESTA, "transition_step_interval_ms": 5001}).transition_step_interval_ms == 5000
        )

    @pytest.mark.parametrize(("key", "value"), [("transition_step_interval_ms", 9000), ("transition_step_size", 0)])
    def test_saving_a_board_with_an_out_of_range_speed_is_refused(self, client, key, value):
        board = _first_board(client)
        response = client.put("/settings/board", json={"boards": [{**board, key: value}]})
        assert response.status_code == 400

    def test_the_shim_refuses_an_out_of_range_interval(self, client):
        assert client.put("/settings/transitions", json={"step_interval_ms": 9000}).status_code in (400, 422)

    def test_mcp_refuses_an_out_of_range_interval(self, client):
        from src.ops.executors import update_board

        board_id = _first_board(client)["id"]
        result = asyncio.run(update_board(board_id, transition_step_interval_ms=5001))
        assert result.get("status") == "error"


# ---------------------------------------------------------------------------
# 8. Every way a board is born gets a transition; one split-flap test
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("no_env_transition")
class TestEveryNewBoardGetsATransition:
    def test_set_boards_stamps_a_new_board(self, tmp_path):
        svc = _service_at_v6(tmp_path, [{**VESTA, "transition": "row"}])
        svc.set_boards([{**VESTA, "transition": "row"}, {"device_type": "note", "name": "New"}])
        assert svc.get_board_settings().boards[1]["transition"] == "none"

    def test_set_boards_leaves_an_existing_unset_led_board_unset(self, tmp_path):
        svc = _service_at_v6(tmp_path, [{**VESTA, "transition": "row"}, PIXOO])
        svc.set_boards([{**VESTA, "transition": "row"}, PIXOO])
        assert "transition" not in svc.get_board_settings().boards[1]

    def test_set_devices_stamps_its_boards(self, tmp_path):
        svc = _service_at_v6(tmp_path, [{**VESTA, "transition": "row"}])
        svc.set_devices(["flagship", "note"])
        assert all(b.get("transition") for b in svc.get_board_settings().boards)

    def test_the_config_board_reset_board_has_a_transition(self, client):
        assert client.delete("/config/board").status_code in (200, 204)
        assert _first_board(client)["transition"] == "none"


@pytest.mark.parametrize(("board", "expected"), [(VESTA, True), (PANEL, True), (PIXOO, False)])
def test_is_split_flap(board, expected):
    from src.devices import is_split_flap

    assert is_split_flap(board) is expected


# ===========================================================================
# Second review
# ===========================================================================

# ---------------------------------------------------------------------------
# B. Out-of-range stored speeds are clamped, and only written fields validated
# ---------------------------------------------------------------------------


class TestStoredSpeedsAreClamped:
    def test_a_stored_interval_above_the_cap_loads_clamped_and_logged(self, tmp_path, caplog):
        with caplog.at_level(logging.WARNING):
            svc = _service_at_v6(tmp_path, [{**VESTA, "transition": "row", "transition_step_interval_ms": 9000}])
        assert svc.get_board_settings().boards[0]["transition_step_interval_ms"] == 5000
        assert "9000" in caplog.text

    def test_the_migration_clamps_the_install_interval(self, caplog):
        from src.settings.service import _migrate_v5_to_v6

        data = {
            "schema_version": 5,
            "transitions": {"strategy": "row", "step_interval_ms": 9000, "step_size": None},
            "board": {"board_type": "black", "boards": [dict(VESTA)], "devices": ["flagship"]},
        }
        with caplog.at_level(logging.WARNING):
            _migrate_v5_to_v6(data)
        assert data["board"]["boards"][0]["transition_step_interval_ms"] == 5000
        assert "9000" in caplog.text

    def test_get_then_put_of_the_boards_succeeds(self, client):
        boards = client.get("/settings/board").json()["boards"]
        assert client.put("/settings/board", json={"boards": boards}).status_code == 200

    def test_a_write_that_leaves_a_bad_stored_transition_alone_is_not_refused(self, tmp_path):
        svc = _service_at_v6(tmp_path, [{**VESTA, "transition": "sparkle"}])
        stored = svc.get_board_settings().boards[0]
        svc.set_boards([{**stored, "name": "Hall"}])
        assert svc.get_board_settings().boards[0]["name"] == "Hall"

    def test_one_constant_bounds_every_interval(self):
        from src.devices import MAX_TRANSITION_STEP_INTERVAL_MS, TRANSITION_SPEED_BOUNDS
        from src.pages.models import PageCreate
        from src.settings.models import TransitionSettingsUpdate

        def le(model, name):
            return next(m.le for m in model.model_fields[name].metadata if hasattr(m, "le"))

        assert TRANSITION_SPEED_BOUNDS["transition_step_interval_ms"][1] == MAX_TRANSITION_STEP_INTERVAL_MS
        assert le(TransitionSettingsUpdate, "step_interval_ms") == MAX_TRANSITION_STEP_INTERVAL_MS
        assert le(PageCreate, "transition_interval_ms") == MAX_TRANSITION_STEP_INTERVAL_MS

    def test_the_mcp_doc_names_the_cap(self):
        import inspect

        from src.devices import MAX_TRANSITION_STEP_INTERVAL_MS
        from src.mcp_server import _build_mcp_server

        source = inspect.getsource(_build_mcp_server)
        assert f"0–{MAX_TRANSITION_STEP_INTERVAL_MS}" in source

    def test_the_ui_constant_matches(self):
        from pathlib import Path

        from src.devices import MAX_TRANSITION_STEP_INTERVAL_MS

        ui = Path(__file__).resolve().parent.parent / "web/src/components/displays/display-transition.tsx"
        assert f"MAX_STEP_INTERVAL_MS = {MAX_TRANSITION_STEP_INTERVAL_MS};" in ui.read_text()


# ---------------------------------------------------------------------------
# D. An LED id or "none" on a plugin without LED transitions is a plain write
# ---------------------------------------------------------------------------


def test_an_led_choice_on_a_native_plugin_drops_its_speed_too(monkeypatch):
    from src.outputs.factory import build_driver
    from src.plugins.loader import PluginLoader
    from tests.test_output_plugin_e2e import FIXTURES, GRID, PLUGIN_ID, board

    loader = PluginLoader(plugins_dir=FIXTURES, external_dirs=[])
    assert loader.load_plugin(PLUGIN_ID) is not None, loader.load_errors
    try:
        driver = build_driver(board())
        assert "column" in driver.native_transitions
        driver.render(GRID, strategy="none", step_interval_ms=50, step_size=2)
        assert driver.plugin.natives == [None]
    finally:
        loader.unload_plugin(PLUGIN_ID)


# ---------------------------------------------------------------------------
# F. The shim validates per board type; a speed-only write leaves the strategy alone
# ---------------------------------------------------------------------------


@pytest.fixture
def recording_output():
    """The recording output plugin: models ``recording_sign`` (a split-flap
    sign, natives ``column``) and ``divoom_pixoo64`` (an LED matrix)."""
    from src.plugins.loader import PluginLoader
    from tests.test_output_plugin_e2e import FIXTURES, PLUGIN_ID

    loader = PluginLoader(plugins_dir=FIXTURES, external_dirs=[])
    assert loader.load_plugin(PLUGIN_ID) is not None, loader.load_errors
    yield PLUGIN_ID
    loader.unload_plugin(PLUGIN_ID)


def _plugin_board(output_id: str, model: str) -> dict:
    return {
        "id": "rec",
        "name": "Sign",
        "device_type": "panel",
        "grid_rows": 6,
        "grid_cols": 22,
        "output": output_id,
        "device_model": model,
        "output_config": {"host": "192.0.2.50"},
        "transition": "none",
    }


class TestShimSplitsOnTheBoardModel:
    """The shim takes what the board's own menu offers, and the menu is
    chosen by the board's device model (LED matrix or not) — not by whether
    an output plugin drives it."""

    def test_a_non_led_output_plugin_board_takes_its_natives_and_plugins(self, tmp_path, recording_output):
        svc = _service_at_v6(tmp_path, [_plugin_board(recording_output, "recording_sign")])
        svc.update_plugin_settings({"transition_plugins_enabled": True})
        svc.update_transition_settings(strategy="column")
        assert svc.get_board_settings().boards[0]["transition"] == "column"
        svc.update_transition_settings(strategy="plugin:typewriter")
        assert svc.get_board_settings().boards[0]["transition"] == "plugin:typewriter"
        with pytest.raises(ValueError, match="column"):
            svc.update_transition_settings(strategy="fade")

    def test_an_led_model_on_the_same_output_takes_led_ids_only(self, tmp_path, recording_output):
        svc = _service_at_v6(tmp_path, [_plugin_board(recording_output, "divoom_pixoo64")])
        svc.update_transition_settings(strategy="fade")
        assert svc.get_board_settings().boards[0]["transition"] == "fade"
        with pytest.raises(ValueError, match="flip"):
            svc.update_transition_settings(strategy="column")

    def test_an_led_fiestapanel_takes_led_ids(self, tmp_path, monkeypatch):
        import src.outputs.board_profile as board_profile

        monkeypatch.setattr(board_profile, "_panel_render_style", lambda board: "led_matrix")
        svc = _service_at_v6(tmp_path, [{**PANEL, "transition": "none"}])
        svc.update_transition_settings(strategy="fade")
        assert svc.get_board_settings().boards[0]["transition"] == "fade"


class TestShimPerBoardType:
    def test_an_led_id_is_refused_on_a_split_flap(self, tmp_path):
        svc = _service_at_v6(tmp_path, [{**VESTA, "transition": "row"}])
        with pytest.raises(ValueError, match="column"):
            svc.update_transition_settings(strategy="fade")
        assert svc.get_board_settings().boards[0]["transition"] == "row"

    def test_a_split_flap_strategy_is_refused_on_an_led_board(self, tmp_path):
        svc = _service_at_v6(tmp_path, [{**PIXOO, "transition": "fade"}])
        with pytest.raises(ValueError, match="flip"):
            svc.update_transition_settings(strategy="column")
        assert svc.get_board_settings().boards[0]["transition"] == "fade"

    def test_a_speed_only_update_does_not_revalidate_the_stored_strategy(self, tmp_path):
        svc = _service_at_v6(tmp_path, [{**VESTA, "transition": "sparkle"}])
        svc.update_transition_settings(step_interval_ms=30)
        board = svc.get_board_settings().boards[0]
        assert (board["transition"], board["transition_step_interval_ms"]) == ("sparkle", 30)

    def test_the_api_names_what_the_board_accepts(self, client):
        response = client.put("/settings/transitions", json={"strategy": "fade"})
        assert response.status_code == 400
        assert "column" in response.json()["detail"]
