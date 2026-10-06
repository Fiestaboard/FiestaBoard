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
# 2. A page strategy the display cannot run falls through to the display's
# ---------------------------------------------------------------------------


def _caps(technology: str, natives=(), animation: str = "stream"):
    from src.settings.service import TransitionCapabilities

    return TransitionCapabilities(technology=technology, native_transitions=frozenset(natives), animation=animation)


SPLIT_FLAP = ("split_flap", ("column", "row", "diagonal"))
LED = ("led_matrix", ())


def _page(strategy, interval=None, step_size=None):
    return SimpleNamespace(
        transition_strategy=strategy, transition_interval_ms=interval, transition_step_size=step_size
    )


class TestPageStrategyMustBeRunnable:
    def _display(self, technology, natives, strategy="row", animation="stream"):
        from src.settings.service import TransitionSettings

        return TransitionSettings(
            strategy=strategy,
            step_interval_ms=40,
            step_size=2,
            capabilities=_caps(technology, natives, animation),
        )

    @pytest.mark.parametrize(
        ("display", "page_strategy"),
        [(LED, "column"), (LED, "plugin:typewriter"), (SPLIT_FLAP, "flip"), (("screen", ()), "column")],
        ids=["native-on-led", "plugin-on-led", "led-id-on-split-flap", "native-the-output-lacks"],
    )
    def test_an_unrunnable_page_strategy_falls_through_to_the_display(self, display, page_strategy):
        resolved = page_transition(self._display(*display, strategy="none"), _page(page_strategy, interval=5))
        assert (resolved.strategy, resolved.step_interval_ms, resolved.step_size) == ("none", 40, 2)

    @pytest.mark.parametrize(
        ("display", "page_strategy"),
        [(SPLIT_FLAP, "column"), (SPLIT_FLAP, "plugin:typewriter"), (LED, "fade")],
    )
    def test_a_runnable_page_strategy_still_wins(self, display, page_strategy):
        assert page_transition(self._display(*display), _page(page_strategy)).strategy == page_strategy

    def test_a_display_that_takes_no_frames_cannot_run_a_plugin(self):
        display = self._display("split_flap", ("row",), strategy=None, animation="none")
        assert page_transition(display, _page("plugin:typewriter")).strategy is None

    def test_unknown_capabilities_keep_the_page_strategy(self):
        from src.settings.service import TransitionSettings

        assert page_transition(TransitionSettings(strategy="row"), _page("column")).strategy == "column"

    def test_the_display_transition_carries_its_output_capabilities(self, tmp_path):
        svc = _service_at_v6(tmp_path, [{**VESTA, "transition": "row"}, {**PANEL, "transition": "none"}])
        vb, tv = svc.get_transition_settings("vb"), svc.get_transition_settings("tv")
        assert vb.capabilities is not None and "column" in vb.capabilities.native_transitions
        assert tv.capabilities is not None and not tv.capabilities.native_transitions
        assert page_transition(vb, _page("column")).strategy == "column"
        assert page_transition(tv, _page("column")).strategy is None

    def test_capabilities_stay_off_the_wire(self, tmp_path):
        svc = _service_at_v6(tmp_path, [{**VESTA, "transition": "row"}])
        assert set(svc.get_transition_settings("vb").to_dict()) == {"strategy", "step_interval_ms", "step_size"}


# ---------------------------------------------------------------------------
# 3. A transition with no board to land on is not dropped
# ---------------------------------------------------------------------------


class TestNoBoardsToCopyOnto:
    @pytest.mark.parametrize("board", [None, {"board_type": "black", "boards": []}], ids=["no-board-key", "empty"])
    def test_a_default_board_is_materialized_with_the_install_transition(self, monkeypatch, board):
        import src.settings.service as service

        monkeypatch.setattr(service, "_read_legacy_board_connection", lambda: None)
        data = {"schema_version": 5, "transitions": INSTALL}
        if board is not None:
            data["board"] = board
        service._migrate_v5_to_v6(data)
        boards = data["board"]["boards"]
        assert len(boards) == 1
        assert (boards[0]["transition"], boards[0]["transition_step_interval_ms"]) == ("diagonal", 40)

    def test_the_materialized_board_imports_the_legacy_connection(self, monkeypatch):
        import src.settings.service as service
        from src.settings.board_shape import flat_connection

        legacy = {"api_mode": "local", "host": "192.0.2.10", "local_api_key": "test_key", "cloud_key": ""}
        monkeypatch.setattr(service, "_read_legacy_board_connection", lambda: {**legacy, "note_array_token": ""})
        data = {"schema_version": 5, "transitions": INSTALL}
        service._migrate_v5_to_v6(data)
        assert flat_connection(data["board"]["boards"][0])["local_api_key"] == "test_key"

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
# 5. A runtime key that is not a board id reads the first display
# ---------------------------------------------------------------------------


class TestRuntimeKeysFallBackToTheFirstDisplay:
    @pytest.mark.parametrize("key", ["__primary__", "", "missing"])
    def test_a_non_board_key_reads_the_first_display(self, tmp_path, key):
        svc = _service_at_v6(
            tmp_path,
            [{**VESTA, "transition": "row", "transition_step_size": 3}, {**PANEL, "transition": "column"}],
        )
        resolved = svc.get_transition_settings(key)
        assert (resolved.strategy, resolved.step_size) == ("row", 3)

    def test_the_display_service_fallback_key_is_covered(self):
        from src.main import DisplayService

        assert DisplayService._PRIMARY_FALLBACK_KEY == "__primary__"


# ---------------------------------------------------------------------------
# 6. /settings/beta and update_setting('beta') stay as deprecated aliases
# ---------------------------------------------------------------------------


class TestBetaAlias:
    def test_get_beta_reads_the_plugin_flags_with_a_deprecation_notice(self, client):
        client.put("/settings/plugins", json={"output_plugins_enabled": True})
        response = client.get("/settings/beta")
        assert response.status_code == 200
        assert response.json() == {"settings": {"transition_plugins_enabled": False, "output_plugins_enabled": True}}
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
        assert (
            BoardInstance.from_dict({**VESTA, "transition_step_interval_ms": 5001}).transition_step_interval_ms is None
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
