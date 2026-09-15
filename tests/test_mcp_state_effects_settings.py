"""State effects of the Settings-page MCP tools — boards, panels, network, system, debug.

The sibling of ``tests/test_mcp_state_effects.py`` for the tools that
cover the rest of the web UI's Settings page. Same rule:

    Every assertion is on state read back *after* the call — through the
    service, a fresh store, or another tool — or, where the effect leaves
    the process (the updater sidecar, nmcli, a board's tile, a third-party
    AI endpoint), on the call that crossed that patched boundary.

The fixtures come from the sibling module so the two suites cannot drift:
real ``SettingsService`` / ``ConfigManager`` / ``PanelService`` instances
over files in ``tmp_path``, and the minimal fake display engine (not a
MagicMock, so a tool calling a method that does not exist raises).

Secrets are excluded by design. Several tests pin that: a rename keeps the
stored API key, the AI tool keeps the stored ``api_key`` and refuses one
sent to it, the summary and the backup export mask every credential.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest

pytest.importorskip("mcp", reason="mcp package not installed")

from src.panels.service import PanelService
from src.panels.storage import PanelStorage
from tests import test_mcp_state_effects as sibling
from tests.test_mcp_state_effects import (
    _FakeClient,
    _persisted_files,
    assert_ok,
    call,
    call_expect_error,
)

# The sibling module's fixtures, re-registered here under their own names.
# Bound as module attributes (pytest collects fixture objects from the module
# namespace) rather than imported, so ruff does not read every test's
# ``mcp`` parameter as a redefinition of the import.
mcp = sibling.mcp
services = sibling.services
two_boards = sibling.two_boards
engine = sibling.engine

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _FakeRuntimeEngine:
    """The ``src.display_runtime`` engine surface the board/panel handlers
    touch after a roster mutation. Counts the client rebuilds so a test can
    assert the handler asked for one."""

    def __init__(self) -> None:
        self.reinitialized = 0
        self.invalidated: list[str] = []
        self.vb_client = None
        self.board_clients: dict[str, Any] = {}
        self.runtimes: dict[str, Any] = {}

    def reinitialize_board_client(self) -> None:
        self.reinitialized += 1

    def invalidate_board_content(self, board_id: str) -> None:
        self.invalidated.append(board_id)

    def get_board_client(self, board_id: str):
        return None


@pytest.fixture
def runtime(two_boards, tmp_path, monkeypatch):
    """Real panel storage plus a fake ``display_runtime`` engine.

    ``display_runtime.get_service()`` would otherwise *construct* a
    DisplayService (and try to reach board hardware) the first time a
    handler rebuilds clients.
    """
    fake = _FakeRuntimeEngine()
    monkeypatch.setattr("src.display_runtime.get_service", lambda: fake)
    panels = PanelService(PanelStorage(str(tmp_path / "panels.json")))
    monkeypatch.setattr("src.panels.service._panel_service", panels)
    fake.panels = panels  # type: ignore[attr-defined]
    return fake


class _DebugClient(_FakeClient):
    """A board client that also records raw sends and cache clears."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[tuple[list[list[int]], bool]] = []
        self.cache_clears = 0
        self.last_send_throttled = False

    def send_characters(self, characters, force=False, **_kwargs):
        self.sent.append((characters, force))
        self._last_characters = characters
        return (True, True)

    def clear_cache(self) -> None:
        self.cache_clears += 1


@pytest.fixture
def debug_engine(engine):
    """The sibling module's fake engine, with clients that accept raw sends."""
    for rt in engine.runtimes.values():
        rt.client = _DebugClient()
    return engine


def _board(svc, board_id: str) -> dict[str, Any]:
    return next(b for b in svc.get_board_settings().boards if b.get("id") == board_id)


# ---------------------------------------------------------------------------
# update_setting — the new categories
# ---------------------------------------------------------------------------


def test_update_setting_general_instance_name_is_read_back(mcp, services, two_boards):
    assert_ok(call(mcp, "update_setting", category="general", values={"instance_name": "Kitchen Board"}), "general")

    assert services["config"].get_general()["instance_name"] == "Kitchen Board"
    summary = assert_ok(call(mcp, "get_settings_summary"), "get_settings_summary")
    assert summary["general"]["instance_name"] == "Kitchen Board"


def test_update_setting_general_time_and_date_formats_persist(mcp, services, two_boards):
    assert_ok(
        call(mcp, "update_setting", category="general", values={"time_format": "24h", "date_format": "YYYY-MM-DD"}),
        "general",
    )
    general = services["config"].get_general()
    assert (general["time_format"], general["date_format"]) == ("24h", "YYYY-MM-DD")


def test_update_setting_general_refuses_keys_the_settings_page_does_not_edit(mcp, services, two_boards):
    before = services["config"].get_general().get("refresh_interval_seconds")
    message = call_expect_error(mcp, "update_setting", category="general", values={"refresh_interval_seconds": 5})
    assert "Unknown keys" in message and "refresh_interval_seconds" in message
    assert services["config"].get_general().get("refresh_interval_seconds") == before


def test_update_setting_refuses_unknown_keys_instead_of_ignoring_them(mcp, services, two_boards):
    """The request models drop unknown keys; a typo must not read as success."""
    message = call_expect_error(
        mcp, "update_setting", category="display", values={"reduce_motion": True, "flap_speed": "quick"}
    )
    assert "flap_speed" in message
    assert two_boards.get_display_settings().reduce_motion is False, "a refused call must change nothing"


def test_update_setting_beta_transition_plugins_flag_persists(mcp, services, two_boards):
    assert two_boards.get_beta_settings().transition_plugins_enabled is False
    assert_ok(call(mcp, "update_setting", category="beta", values={"transition_plugins_enabled": True}), "beta")
    assert two_boards.get_beta_settings().transition_plugins_enabled is True


def test_update_setting_plugins_auto_update_persists(mcp, services, two_boards):
    before = two_boards.get_plugin_settings().auto_update
    assert_ok(call(mcp, "update_setting", category="plugins", values={"auto_update": not before}), "plugins")
    assert two_boards.get_plugin_settings().auto_update is (not before)


def test_update_setting_mqtt_broker_persists_and_is_applied_to_the_live_client(mcp, services, two_boards):
    applied: list[Any] = []
    with patch("src.api_server._apply_mqtt_config", side_effect=applied.append):
        assert_ok(
            call(mcp, "update_setting", category="mqtt", values={"host": "broker.example.com", "port": 1884}),
            "mqtt",
        )

    stored = two_boards.get_mqtt_settings()
    assert (stored.broker_host, stored.broker_port) == ("broker.example.com", 1884)
    assert len(applied) == 1 and applied[0].broker_host == "broker.example.com", (
        "the live MQTT client must be reconfigured, exactly as PUT /settings/mqtt does"
    )


def test_update_setting_mqtt_refuses_the_password_and_leaves_the_stored_one_alone(mcp, services, two_boards):
    two_boards.set_mqtt_settings({"password": "test_mqtt_secret"})
    message = call_expect_error(mcp, "update_setting", category="mqtt", values={"password": "new"})
    assert "password" in message and "credential" in message
    assert two_boards.get_mqtt_settings().password == "test_mqtt_secret"


def _seed_provider(config, **overrides):
    provider = {
        "id": "p1",
        "name": "Old name",
        "protocol": "openai",
        "base_url": "https://api.example.com/v1",
        "api_key": "test_key_1",
        "models": ["model-a"],
        "default_model": "model-a",
    }
    provider.update(overrides)
    config.set_ai_providers({"enabled": True, "providers": [provider], "default_provider_id": "p1"})


def test_update_setting_ai_provider_edit_keeps_the_stored_api_key(mcp, services, two_boards):
    _seed_provider(services["config"])

    assert_ok(
        call(
            mcp,
            "update_setting",
            category="ai",
            values={
                "providers": [
                    {
                        "id": "p1",
                        "name": "New name",
                        "base_url": "https://api.example.com/v1",
                        "models": ["model-a", "model-b"],
                    }
                ]
            },
        ),
        "ai",
    )

    stored = services["config"].get_ai_provider("p1")
    assert stored["name"] == "New name" and stored["models"] == ["model-a", "model-b"]
    assert stored["api_key"] == "test_key_1", "editing a provider must never drop its stored key"


def test_update_setting_ai_refuses_an_api_key_inside_a_provider(mcp, services, two_boards):
    _seed_provider(services["config"])
    message = call_expect_error(
        mcp, "update_setting", category="ai", values={"providers": [{"id": "p1", "api_key": "sk-test-leak"}]}
    )
    assert "api_key" in message
    assert services["config"].get_ai_provider("p1")["name"] == "Old name"


def test_update_setting_ai_new_provider_is_saved_without_a_key(mcp, services, two_boards):
    _seed_provider(services["config"])
    assert_ok(
        call(
            mcp,
            "update_setting",
            category="ai",
            values={
                "providers": [
                    {"id": "p1", "name": "Old name", "base_url": "https://api.example.com/v1", "models": ["model-a"]},
                    {"id": "p2", "name": "Local", "base_url": "http://localhost:11434/v1", "models": ["llama"]},
                ],
                "default_provider_id": "p2",
            },
        ),
        "ai",
    )
    block = services["config"].get_ai_providers()
    assert block["default_provider_id"] == "p2"
    assert services["config"].get_ai_provider("p2")["api_key"] == "", "a new provider must not inherit the mask literal"
    assert services["config"].get_ai_provider("p1")["api_key"] == "test_key_1"


def test_update_setting_ai_enabled_flag_persists(mcp, services, two_boards):
    assert_ok(call(mcp, "update_setting", category="ai", values={"enabled": True}), "ai")
    assert services["config"].get_ai_providers()["enabled"] is True


def test_update_setting_release_channel_switches_through_the_sidecar(mcp, services, two_boards):
    switched: list[str] = []

    def fake_switch(channel):
        switched.append(channel)
        return {"status": "queued", "channel": channel, "tag": "beta"}

    with (
        patch("src.system.update_service.channel_switch_blocker", return_value=None),
        patch("src.system.update_service.switch_channel", side_effect=fake_switch),
    ):
        assert_ok(call(mcp, "update_setting", category="release_channel", values={"channel": "beta"}), "channel")
    assert switched == ["beta"]


def test_update_setting_release_channel_reports_the_blocker(mcp, services, two_boards):
    """No sidecar → the handler's 503 reason, not a success."""
    message = call_expect_error(mcp, "update_setting", category="release_channel", values={"channel": "beta"})
    assert "sidecar" in message


def test_update_setting_auto_update_interval_persists_in_the_update_state(mcp, services, two_boards):
    from src.system import update_service

    assert_ok(call(mcp, "update_setting", category="auto_update", values={"interval": "monthly"}), "auto_update")

    assert update_service._resolve_auto_update_interval(update_service._system_update_state_load()) == "monthly"
    status = assert_ok(call(mcp, "get_system_status"), "get_system_status")
    assert status["update"]["auto_update_interval"] == "monthly"


def test_update_setting_auto_update_rejects_an_unknown_interval(mcp, services, two_boards):
    message = call_expect_error(mcp, "update_setting", category="auto_update", values={"interval": "hourly"})
    assert "hourly" in message


def test_update_setting_hdmi_kiosk_posts_the_enable_verb_to_the_sidecar(mcp, services, two_boards):
    posted: list[str] = []

    def fake_post(url, **_kwargs):
        posted.append(url)
        return Mock(status_code=200, json=lambda: {"status": "queued", "action": "hdmi_enable"})

    with (
        patch("src.system.update_service._fiestaboard_profile", return_value="pi"),
        patch("src.system.update_service._updater_probe", return_value=True),
        patch("src.system.update_service._updater_token", return_value="test_token"),
        patch("src.settings.routes.requests.post", side_effect=fake_post),
    ):
        assert_ok(call(mcp, "update_setting", category="hdmi_kiosk", values={"enabled": True}), "hdmi_kiosk")
    assert len(posted) == 1 and posted[0].endswith("/hdmi/enable")


def test_update_setting_hdmi_kiosk_off_the_pi_is_an_error(mcp, services, two_boards):
    message = call_expect_error(mcp, "update_setting", category="hdmi_kiosk", values={"enabled": True})
    assert "FiestaPi" in message


def test_update_setting_silence_schedule_with_board_id_writes_that_boards_override(mcp, services, two_boards):
    assert_ok(
        call(
            mcp,
            "update_setting",
            category="silence_schedule",
            values={"enabled": True, "start_time": "22:00", "end_time": "07:00", "board_id": "board-note"},
        ),
        "silence_schedule",
    )
    feature = services["config"].get_feature("silence_schedule") or {}
    assert feature.get("by_board", {}).get("board-note", {}).get("enabled") is True
    assert not feature.get("enabled"), "a per-board write must leave the install-wide schedule alone"


# ---------------------------------------------------------------------------
# Boards
# ---------------------------------------------------------------------------


def test_update_board_renames_the_board_and_keeps_its_credentials(mcp, services, two_boards, runtime):
    two_boards.set_boards(
        [
            {"id": "board-main", "name": "Living Room", "device_type": "flagship", "local_api_key": "test_secret_key"},
            {"id": "board-note", "name": "Kitchen", "device_type": "note"},
        ]
    )

    result = assert_ok(call(mcp, "update_board", board_id="board-main", name="Bedroom"), "update_board")

    stored = _board(two_boards, "board-main")
    assert stored["name"] == "Bedroom"
    assert stored["local_api_key"] == "test_secret_key", "a rename must not drop the stored API key"
    assert runtime.reinitialized == 1, "the display engine must rebuild its clients after a roster change"
    assert "test_secret_key" not in json.dumps(result)
    assert result["board"]["has_credentials"] is True and "host" not in result["board"]


def test_update_board_changes_type_colour_glyph_and_mode(mcp, services, two_boards, runtime):
    assert_ok(
        call(
            mcp,
            "update_board",
            board_id="board-note",
            device_type="note_array",
            notes_wide=2,
            notes_tall=1,
            board_color="white",
            api_mode="cloud",
        ),
        "update_board",
    )
    assert_ok(call(mcp, "update_board", board_id="board-main", code62_glyph="heart"), "update_board")

    note = _board(two_boards, "board-note")
    assert (note["device_type"], note["notes_wide"], note["notes_tall"]) == ("note_array", 2, 1)
    assert (note["board_color"], note["api_mode"]) == ("white", "cloud")
    assert _board(two_boards, "board-main")["code62_glyph"] == "heart"
    summary = assert_ok(call(mcp, "get_settings_summary"), "get_settings_summary")
    by_id = {b["id"]: b for b in summary["boards"]}
    assert (by_id["board-note"]["rows"], by_id["board-note"]["cols"]) == (3, 30)
    assert by_id["board-main"]["code62_glyph"] == "heart"


def test_update_board_host_is_stored_but_never_read_back(mcp, services, two_boards, runtime):
    result = assert_ok(call(mcp, "update_board", board_id="board-main", host="192.0.2.10"), "update_board")
    assert _board(two_boards, "board-main")["host"] == "192.0.2.10"
    assert result["board"]["has_host"] is True
    summary = assert_ok(call(mcp, "get_settings_summary"), "get_settings_summary")
    assert "192.0.2.10" not in json.dumps(summary) and "192.0.2.10" not in json.dumps(result)


def test_update_board_refuses_a_value_the_board_model_would_silently_coerce(mcp, services, two_boards, runtime):
    message = call_expect_error(mcp, "update_board", board_id="board-note", device_type="tablet")
    assert "device_type" in message and "tablet" in message
    assert _board(two_boards, "board-note")["device_type"] == "note"
    assert runtime.reinitialized == 0


def test_update_board_reports_an_unknown_board(mcp, services, two_boards, runtime):
    message = call_expect_error(mcp, "update_board", board_id="board-ghost", name="X")
    assert "board-ghost" in message


def test_update_board_with_no_fields_is_reported(mcp, services, two_boards, runtime):
    message = call_expect_error(mcp, "update_board", board_id="board-main")
    assert "Nothing to update" in message


def test_add_board_appends_a_board_and_reports_its_id(mcp, services, two_boards, runtime):
    result = assert_ok(call(mcp, "add_board", device_type="note", name="Hallway"), "add_board")

    boards = two_boards.get_board_settings().boards
    assert len(boards) == 3
    added = _board(two_boards, result["board_id"])
    assert (added["name"], added["device_type"]) == ("Hallway", "note")
    assert runtime.reinitialized == 1


def test_add_board_rejects_an_unknown_device_type(mcp, services, two_boards, runtime):
    call_expect_error(mcp, "add_board", device_type="tablet")
    assert len(two_boards.get_board_settings().boards) == 2


def test_remove_board_drops_it_from_the_roster(mcp, services, two_boards, runtime):
    result = assert_ok(call(mcp, "remove_board", board_id="board-note"), "remove_board")
    assert [b["id"] for b in two_boards.get_board_settings().boards] == ["board-main"]
    assert result["remaining_board_ids"] == ["board-main"]
    assert runtime.reinitialized == 1


def test_remove_board_refuses_the_last_board(mcp, services, two_boards, runtime):
    assert_ok(call(mcp, "remove_board", board_id="board-note"), "remove_board")
    message = call_expect_error(mcp, "remove_board", board_id="board-main")
    assert "last board" in message
    assert len(two_boards.get_board_settings().boards) == 1


def test_remove_board_refuses_a_board_a_panel_drives(mcp, services, two_boards, runtime):
    panel = assert_ok(call(mcp, "create_panel", name="Den TV"), "create_panel")
    message = call_expect_error(mcp, "remove_board", board_id=panel["board_id"])
    assert "FiestaPanel" in message and "Den TV" in message
    assert any(b["id"] == panel["board_id"] for b in two_boards.get_board_settings().boards)


def test_detect_board_size_classifies_the_live_grid(mcp, services, two_boards, runtime):
    class _Probe:
        def read_current_message(self):
            return [[0] * 15 for _ in range(3)]

    with patch("src.api_server.board_client_from_board_dict", return_value=_Probe()):
        result = assert_ok(call(mcp, "detect_board_size", board_id="board-main"), "detect_board_size")

    assert (result["device_type"], result["rows"], result["cols"]) == ("note", 3, 15)
    assert _board(two_boards, "board-main")["device_type"] == "flagship", "detection reads; it does not apply"


def test_detect_board_size_unconfigured_board_is_an_error(mcp, services, two_boards, runtime):
    message = call_expect_error(mcp, "detect_board_size", board_id="board-main")
    assert "credentials" in message


def test_identify_tile_flashes_the_configured_tile(mcp, services, two_boards, runtime):
    two_boards.set_boards(
        [
            {"id": "board-main", "name": "Living Room", "device_type": "flagship"},
            {
                "id": "board-array",
                "name": "Wall",
                "device_type": "note_array",
                "api_mode": "local",
                "notes_wide": 2,
                "notes_tall": 1,
                "tiles": [
                    {
                        "row": 0,
                        "col": 0,
                        "host": "192.0.2.21",
                        "port": 7000,
                        "local_api_key": "test_tile_key",
                        "enabled": True,
                    },
                    {
                        "row": 0,
                        "col": 1,
                        "host": "192.0.2.22",
                        "port": 7000,
                        "local_api_key": "test_tile_key",
                        "enabled": True,
                    },
                ],
            },
        ]
    )
    flashed: list[tuple[str, list[list[int]]]] = []

    class _TileClient:
        def __init__(self, api_key, host, **_kwargs):
            self.host = host

        def send_characters(self, pattern, force=False):
            flashed.append((self.host, pattern))
            return (True, True)

    with patch("src.board_client.BoardClient", _TileClient):
        result = assert_ok(call(mcp, "identify_tile", board_id="board-array", row=0, col=1), "identify_tile")

    assert [host for host, _ in flashed] == ["192.0.2.22"]
    assert len(flashed[0][1]) == 3 and len(flashed[0][1][0]) == 15, "the identify pattern is one Note (3×15)"
    assert result["results"] == [{"row": 0, "col": 1, "success": True}]
    assert "test_tile_key" not in json.dumps(result)


def test_identify_tile_on_a_flagship_is_an_error(mcp, services, two_boards, runtime):
    message = call_expect_error(mcp, "identify_tile", board_id="board-main", row=0, col=0)
    assert "note array" in message


# ---------------------------------------------------------------------------
# FiestaPanels
# ---------------------------------------------------------------------------


def test_create_panel_persists_the_panel_and_its_virtual_board(mcp, services, two_boards, runtime):
    result = assert_ok(call(mcp, "create_panel", name="Den TV", screen_diagonal_inches=65), "create_panel")

    panels = assert_ok(call(mcp, "list_panels"), "list_panels")
    assert panels["total"] == 1
    listed = panels["panels"][0]
    assert (listed["id"], listed["name"], listed["screen_diagonal_inches"]) == (result["panel_id"], "Den TV", 65.0)
    assert listed["board_missing"] is False and listed["device_type"] == "note_array"

    board = _board(two_boards, result["board_id"])
    assert (board["api_mode"], board["name"]) == ("virtual", "Den TV (Panel)")
    assert runtime.reinitialized == 1


def test_create_panel_survives_a_fresh_panel_service(mcp, services, two_boards, runtime, tmp_path):
    result = assert_ok(call(mcp, "create_panel", name="Den TV"), "create_panel")
    reloaded = PanelService(PanelStorage(str(tmp_path / "panels.json")))
    assert [p.id for p in reloaded.list_panels()] == [result["panel_id"]]


def test_update_panel_changes_the_stored_fields(mcp, services, two_boards, runtime):
    created = assert_ok(call(mcp, "create_panel", name="Den TV"), "create_panel")

    assert_ok(
        call(
            mcp,
            "update_panel",
            panel_id=created["panel_id"],
            name="Lounge TV",
            backdrop="dark",
            auto_dim={"enabled": True, "start": "23:00", "end": "06:30"},
        ),
        "update_panel",
    )

    stored = runtime.panels.get_panel(created["panel_id"])
    assert (stored.name, stored.backdrop) == ("Lounge TV", "dark")
    assert (stored.auto_dim.enabled, stored.auto_dim.start, stored.auto_dim.end) == (True, "23:00", "06:30")


def test_update_panel_is_display_moves_the_role_to_that_panel(mcp, services, two_boards, runtime):
    first = assert_ok(call(mcp, "create_panel", name="Den TV"), "create_panel")
    second = assert_ok(call(mcp, "create_panel", name="Hall TV"), "create_panel")
    assert_ok(call(mcp, "update_panel", panel_id=first["panel_id"], is_display=True), "update_panel")

    assert_ok(call(mcp, "update_panel", panel_id=second["panel_id"], is_display=True), "update_panel")

    assert runtime.panels.get_panel(second["panel_id"]).is_display is True
    assert runtime.panels.get_panel(first["panel_id"]).is_display is False, "exactly one panel holds /p/display"


def test_update_panel_screen_size_refits_the_virtual_board(mcp, services, two_boards, runtime):
    created = assert_ok(call(mcp, "create_panel", name="Den TV", screen_diagonal_inches=32), "create_panel")
    before = _board(two_boards, created["board_id"])

    assert_ok(call(mcp, "update_panel", panel_id=created["panel_id"], screen_diagonal_inches=85), "update_panel")

    after = _board(two_boards, created["board_id"])
    assert (after["notes_wide"], after["notes_tall"]) != (before["notes_wide"], before["notes_tall"])


def test_update_panel_reports_an_unknown_panel(mcp, services, two_boards, runtime):
    message = call_expect_error(mcp, "update_panel", panel_id="nope", name="X")
    assert "not found" in message.lower()


def test_delete_panel_removes_the_panel_and_its_board(mcp, services, two_boards, runtime):
    created = assert_ok(call(mcp, "create_panel", name="Den TV"), "create_panel")

    assert_ok(call(mcp, "delete_panel", panel_id=created["panel_id"]), "delete_panel")

    assert assert_ok(call(mcp, "list_panels"), "list_panels")["total"] == 0
    assert all(b["id"] != created["board_id"] for b in two_boards.get_board_settings().boards)


def test_delete_panel_reports_an_unknown_panel(mcp, services, two_boards, runtime):
    message = call_expect_error(mcp, "delete_panel", panel_id="nope")
    assert "not found" in message.lower()


# ---------------------------------------------------------------------------
# Network (FiestaPi Wi-Fi) — nmcli is the boundary
# ---------------------------------------------------------------------------


@pytest.fixture
def wifi():
    from src.network.wifi import WiFiCapability, get_wifi_service

    svc = get_wifi_service()
    svc._cached_capability = WiFiCapability(available=True)
    yield svc
    svc._cached_capability = None


def test_forget_wifi_network_deletes_the_named_profile(mcp, services, wifi):
    forgotten: list[str] = []

    async def _forget(name):
        forgotten.append(name)

    with patch.object(wifi, "forget", side_effect=_forget):
        result = assert_ok(call(mcp, "forget_wifi_network", name="HomeNet"), "forget_wifi_network")
    assert forgotten == ["HomeNet"] and result["name"] == "HomeNet"


def test_forget_wifi_network_reports_nmcli_refusal(mcp, services, wifi):
    from src.network.wifi import WiFiError

    async def _boom(_name):
        raise WiFiError("profile not found")

    with patch.object(wifi, "forget", side_effect=_boom):
        message = call_expect_error(mcp, "forget_wifi_network", name="Nope")
    assert "profile not found" in message


def test_disconnect_wifi_tears_down_the_active_connection(mcp, services, wifi):
    from src.network.wifi import WiFiStatus

    calls: list[bool] = []

    async def _disconnect():
        calls.append(True)
        return WiFiStatus(
            connected=False, ssid=None, ip_address=None, gateway=None, signal=None, internet_reachable=False
        )

    with patch.object(wifi, "disconnect", side_effect=_disconnect):
        result = assert_ok(call(mcp, "disconnect_wifi"), "disconnect_wifi")
    assert calls == [True] and result["status"]["connected"] is False


def test_wifi_tools_report_unavailable_off_the_pi(mcp, services):
    from src.network.wifi import WiFiCapability, get_wifi_service

    svc = get_wifi_service()
    svc._cached_capability = WiFiCapability(available=False, reason="WiFi management is only on the FiestaPi image.")
    try:
        message = call_expect_error(mcp, "disconnect_wifi")
        assert "FiestaPi" in message
        message = call_expect_error(mcp, "forget_wifi_network", name="HomeNet")
        assert "FiestaPi" in message
    finally:
        svc._cached_capability = None


# ---------------------------------------------------------------------------
# System — the updater sidecar is the boundary
# ---------------------------------------------------------------------------


def test_trigger_system_update_asks_the_sidecar_to_apply(mcp, services):
    from src.system.models import UpdateApplyResponse

    applied: list[bool] = []

    async def _apply():
        applied.append(True)
        return UpdateApplyResponse(status="queued", mode="sidecar", previous_digest="sha256:test")

    with patch("src.system.update_service.apply_update", side_effect=_apply):
        result = assert_ok(call(mcp, "trigger_system_update"), "trigger_system_update")
    assert applied == [True] and result["detail"]["status"] == "queued"


def test_trigger_system_update_without_a_sidecar_relays_the_manual_instructions(mcp, services):
    message = call_expect_error(mcp, "trigger_system_update")
    assert message.strip(), "the 503 detail carries the manual-update instructions"


def test_restart_system_requests_a_restart_from_the_sidecar(mcp, services):
    from src.system.models import SystemActionResponse

    actions: list[str] = []

    async def _act(action):
        actions.append(action)
        return SystemActionResponse(status="queued", action=action)

    with patch("src.system.update_service.perform_sidecar_action", side_effect=_act):
        result = assert_ok(call(mcp, "restart_system"), "restart_system")
    assert actions == ["restart"] and result["detail"]["action"] == "restart"


def test_shutdown_system_requests_a_shutdown_from_the_sidecar(mcp, services):
    from src.system.models import SystemActionResponse

    actions: list[str] = []

    async def _act(action):
        actions.append(action)
        return SystemActionResponse(status="queued", action=action)

    with patch("src.system.update_service.perform_sidecar_action", side_effect=_act):
        assert_ok(call(mcp, "shutdown_system"), "shutdown_system")
    assert actions == ["shutdown"]


def test_restart_system_without_a_sidecar_is_an_error_not_a_success(mcp, services):
    message = call_expect_error(mcp, "restart_system")
    assert "sidecar" in message.lower() or "updater" in message.lower()


def test_check_for_update_reports_the_registry_verdict(mcp, services):
    from src.system.models import UpdateCheckResponse

    async def _check():
        return UpdateCheckResponse(
            current_version="1.0.0",
            latest_version="1.1.0",
            update_available=True,
            package_url="https://example.com/releases/1.1.0",
            is_production=False,
        )

    with patch("src.system.update_service._perform_update_check", side_effect=_check):
        result = assert_ok(call(mcp, "check_for_update"), "check_for_update")
    assert (result["latest_version"], result["update_available"]) == ("1.1.0", True)


def test_export_backup_returns_the_document_with_secrets_masked(mcp, services):
    data_dir = Path(os.environ["FIESTABOARD_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "settings.json").write_text(
        json.dumps({"board": {"boards": [{"id": "b1", "device_type": "flagship", "local_api_key": "test_secret_key"}]}})
    )

    result = assert_ok(call(mcp, "export_backup"), "export_backup")

    boards = result["data"]["settings"]["board"]["boards"]
    assert boards[0]["local_api_key"] == "***"
    assert "test_secret_key" not in json.dumps(result)
    assert result["data"]["pages"] is None, "absent stores are reported as null, like the download"


def test_test_ai_provider_probes_the_stored_provider_without_returning_its_key(mcp, services):
    from src.settings.models import AiTestResponse

    _seed_provider(services["config"])
    probed: list[dict[str, Any]] = []

    async def _probe(provider, model=None):
        probed.append(provider)
        return AiTestResponse(ok=True, message="Provider responded.", model_used="model-a")

    with patch("src.ai.generator.test_provider", side_effect=_probe):
        result = assert_ok(call(mcp, "test_ai_provider", provider_id="p1"), "test_ai_provider")

    assert probed[0]["api_key"] == "test_key_1", "the probe must use the stored key"
    assert result["ok"] is True and "test_key_1" not in json.dumps(result)


def test_test_ai_provider_unknown_id_is_an_error(mcp, services):
    _seed_provider(services["config"])
    message = call_expect_error(mcp, "test_ai_provider", provider_id="nope")
    assert "nope" in message


# ---------------------------------------------------------------------------
# Advanced / debug board actions — the board client is the boundary
# ---------------------------------------------------------------------------


def test_blank_board_sends_an_all_blank_grid_sized_to_the_board(mcp, services, debug_engine):
    result = assert_ok(call(mcp, "blank_board", board_id="board-note"), "blank_board")

    client = debug_engine.runtimes["board-note"].client
    assert client.sent == [([[0] * 15 for _ in range(3)], True)]
    assert debug_engine.runtimes["board-main"].client.sent == []
    assert debug_engine.out_of_band == ["board-note"], "an out-of-band write must be marked so the loop knows"
    assert (result["rows"], result["cols"]) == (3, 15)


def test_fill_board_sends_the_code_to_every_tile_of_the_primary_board(mcp, services, debug_engine):
    assert_ok(call(mcp, "fill_board", character_code=66), "fill_board")
    client = debug_engine.runtimes["board-main"].client
    assert client.sent == [([[66] * 22 for _ in range(6)], True)]


def test_fill_board_rejects_a_code_outside_the_flap_range(mcp, services, debug_engine):
    message = call_expect_error(mcp, "fill_board", character_code=72)
    assert "0 and 71" in message
    assert debug_engine.runtimes["board-main"].client.sent == []


def test_show_board_debug_info_sends_the_support_card(mcp, services, debug_engine):
    from src.board_chars import characters_to_message

    result = assert_ok(call(mcp, "show_board_debug_info"), "show_board_debug_info")

    client = debug_engine.runtimes["board-main"].client
    assert len(client.sent) == 1
    grid, forced = client.sent[0]
    assert forced is True and (len(grid), len(grid[0])) == (6, 22)
    assert "DEBUG INFO" in characters_to_message(grid)
    assert result["rows"] == 6


def test_blank_board_on_a_paused_board_is_blocked_without_touching_it(mcp, services, two_boards, debug_engine):
    two_boards.set_paused(True, board_id="board-note")
    result = call(mcp, "blank_board", board_id="board-note")
    assert result["status"] == "blocked" and result["paused"] is True
    assert debug_engine.runtimes["board-note"].client.sent == []


def test_blank_board_reports_an_unknown_board(mcp, services, debug_engine):
    message = call_expect_error(mcp, "blank_board", board_id="board-ghost")
    assert "board-ghost" in message


def test_clear_board_cache_clears_only_the_targeted_client(mcp, services, debug_engine):
    assert_ok(call(mcp, "clear_board_cache", board_id="board-note"), "clear_board_cache")
    assert debug_engine.runtimes["board-note"].client.cache_clears == 1
    assert debug_engine.runtimes["board-main"].client.cache_clears == 0

    assert_ok(call(mcp, "clear_board_cache"), "clear_board_cache")
    assert debug_engine.runtimes["board-main"].client.cache_clears == 1


def test_run_network_diagnostics_diagnoses_the_primary_boards_connection(mcp, services, two_boards):
    two_boards.set_boards(
        [
            {"id": "board-main", "name": "Living Room", "device_type": "flagship", "host": "192.0.2.10"},
            {"id": "board-note", "name": "Kitchen", "device_type": "note"},
        ]
    )
    seen: list[dict[str, Any]] = []

    def _run(**kwargs):
        seen.append(kwargs)
        return {
            "dns": {"ok": True},
            "internet": {"ok": True},
            "vestaboard": {"ok": True, "mode": "local", "steps": {}},
            "overall_ok": True,
            "recommendations": [],
        }

    with patch("src.network_diagnostics.run_full_diagnostics", side_effect=_run):
        result = assert_ok(call(mcp, "run_network_diagnostics"), "run_network_diagnostics")

    assert seen[0]["board_host"] == "192.0.2.10" and seen[0]["use_cloud"] is False
    assert result["overall_ok"] is True


# ---------------------------------------------------------------------------
# Reads — masking, and read-only honesty for the boundary-backed reads
# ---------------------------------------------------------------------------


def test_get_settings_summary_masks_mqtt_and_ai_credentials(mcp, services, two_boards):
    two_boards.set_mqtt_settings({"username": "test_user", "password": "test_mqtt_secret", "broker_host": "broker"})
    _seed_provider(services["config"], headers={"Authorization": "Bearer test_header_secret"})

    summary = assert_ok(call(mcp, "get_settings_summary"), "get_settings_summary")

    assert summary["mqtt"]["broker_host"] == "broker"
    assert (summary["mqtt"]["username"], summary["mqtt"]["password"]) == ("***", "***")
    provider = summary["ai"]["providers"][0]
    assert (provider["id"], provider["name"], provider["api_key"]) == ("p1", "Old name", "***")
    flat = json.dumps(summary)
    for secret in ("test_user", "test_mqtt_secret", "test_key_1", "test_header_secret"):
        assert secret not in flat, f"{secret} leaked through get_settings_summary"


def test_get_settings_summary_reports_every_update_setting_category(mcp, services, two_boards):
    summary = assert_ok(call(mcp, "get_settings_summary"), "get_settings_summary")
    for block in ("general", "display", "transitions", "output", "polling", "location", "silence_schedule"):
        assert block in summary, f"{block} missing from the summary"
    assert summary["beta"]["transition_plugins_enabled"] is False
    assert "auto_update" in summary["plugins"]
    assert set(summary["general"]) == {"instance_name", "timezone", "time_format", "date_format", "welcome_message"}


def test_get_system_status_reports_channel_updates_mqtt_and_kiosk(mcp, services, two_boards):
    status = assert_ok(call(mcp, "get_system_status"), "get_system_status")

    assert status["release_channel"] in ("stable", "beta")
    assert status["running_version"]
    assert status["update"]["auto_update_interval"] in ("daily", "weekly", "monthly", "manual")
    assert status["update"]["updater_available"] is False
    assert status["mqtt"] == {"enabled": False, "connected": False, "running": False}
    assert status["hdmi_kiosk"]["supported"] is False and status["hdmi_kiosk"]["enabled"] is None


def test_boundary_backed_read_tools_leave_every_store_untouched(mcp, services, two_boards, runtime, tmp_path):
    """The sibling module's read-only honesty check skips the tools whose
    answer comes from hardware or the network; here they run against
    patched boundaries and must still write nothing."""
    from src.settings.models import AiTestResponse
    from src.system.models import UpdateCheckResponse

    _seed_provider(services["config"])

    class _Probe:
        def read_current_message(self):
            return [[0] * 22 for _ in range(6)]

    async def _check():
        return UpdateCheckResponse(
            current_version="1.0.0", latest_version=None, update_available=False, package_url="", is_production=False
        )

    async def _probe(provider, model=None):
        return AiTestResponse(ok=True, message="ok", model_used=None)

    def _diag(**_kwargs):
        return {"dns": {"ok": True}, "internet": {"ok": True}, "vestaboard": {"ok": True}, "overall_ok": True}

    before = _persisted_files(tmp_path)
    with (
        patch("src.api_server.board_client_from_board_dict", return_value=_Probe()),
        patch("src.system.update_service._perform_update_check", side_effect=_check),
        patch("src.ai.generator.test_provider", side_effect=_probe),
        patch("src.network_diagnostics.run_full_diagnostics", side_effect=_diag),
    ):
        assert_ok(call(mcp, "detect_board_size", board_id="board-main"), "detect_board_size")
        assert_ok(call(mcp, "check_for_update"), "check_for_update")
        assert_ok(call(mcp, "test_ai_provider", provider_id="p1"), "test_ai_provider")
        assert_ok(call(mcp, "run_network_diagnostics"), "run_network_diagnostics")
    after = _persisted_files(tmp_path)

    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    assert not changed, f"read-only tools changed persisted state: {changed}"
