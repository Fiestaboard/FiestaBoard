"""Value-level contract goldens for the platform one-off endpoints.

Phase 2 §2, Task 8 — the last untagged routes. Fifteen route-methods that are
the *app's own* surface rather than a data domain, grouped into four honest
routers by what they actually do:

``service``  ``GET /``, ``GET|HEAD /health``, ``GET /status``, ``POST /start``,
             ``POST /stop``, ``POST /refresh``, ``GET /silence-status``
``board``    ``GET /board/current-message``, ``POST /send-message``,
             ``POST /send-welcome-message``
``mqtt``     ``GET /mqtt/status``, ``POST /mqtt/republish-discovery``
``backup``   ``GET /backup/export``, ``POST /backup/import``

Pinned as **values**, not shapes. The shape corpus records key sets and type
names, so it cannot see a version string that stopped being reported, a board
grid rendered from the wrong cache, a refusal served at 200, or a 500 detail
that stutters. This file is the pre-conversion recording: every value below is
what the unmodified trunk serves, including the envelopes the conventions pass
in this same PR will deliberately replace.
"""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src import __version__
from src.api_server import app
from src.board_client import BoardClient

# --- Seam targets ----------------------------------------------------------
# Written as constants so the seam-retirement commit changes these lines and
# never an assertion.
SERVICE = "src.api_server.get_service"
SETTINGS_SERVICE = "src.api_server.get_settings_service"
BOARD_CLIENT = "src.api_server._get_board_client"
PAUSED = "src.api_server._board_is_paused"


@pytest.fixture
def client():
    return TestClient(app)


def _ok_response() -> Mock:
    resp = Mock()
    resp.raise_for_status = Mock()
    return resp


def _settings_service():
    ss = Mock()
    ss.should_send_to_board.return_value = True
    ss.is_paused.return_value = False
    ss.get_primary_board_id.return_value = "b1"
    ss.get_active_page_id.return_value = "page-1"
    transition = Mock()
    transition.strategy = None
    transition.step_interval_ms = 0
    transition.step_size = 1
    ss.get_transition_settings.return_value = transition
    board_settings = Mock()
    board_settings.boards = [{"id": "b1", "device_type": "flagship", "notes_wide": 1, "notes_tall": 1}]
    ss.get_board_settings.return_value = board_settings
    ss.get_general_settings.return_value = Mock(welcome_message="")
    return ss


# ===========================================================================
# service — GET /
# ===========================================================================


def test_root_names_the_api_and_its_version(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json() == {"name": "FiestaBoard Display API", "version": "1.0.0", "status": "running"}


# ===========================================================================
# service — GET/HEAD /health
# ===========================================================================


def test_health_reports_ok_with_the_package_version(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert isinstance(body["service_running"], bool)


def test_health_reports_the_loop_as_stopped_when_no_service_exists(client):
    with patch("src.api_server._service_running", False), patch(SERVICE, return_value=None):
        assert client.get("/health").json()["service_running"] is False


def test_health_reports_the_loop_as_running_only_when_both_are_true(client):
    with patch("src.api_server._service_running", True), patch(SERVICE, return_value=Mock()):
        assert client.get("/health").json()["service_running"] is True
    # The flag alone is not enough: no service instance means not running.
    with patch("src.api_server._service_running", True), patch(SERVICE, return_value=None):
        assert client.get("/health").json()["service_running"] is False


def test_head_health_answers_200_with_no_body(client):
    resp = client.head("/health")
    assert resp.status_code == 200
    assert resp.content == b""


# ===========================================================================
# service — GET /status
# ===========================================================================


def test_status_reports_the_flag_the_instance_and_the_active_page(client):
    service = Mock()
    service.get_board_client.return_value = Mock()
    service.board_init_errors = {}
    with (
        patch("src.api_server._service_running", True),
        patch(SERVICE, return_value=service),
        patch(SETTINGS_SERVICE, return_value=_settings_service()),
        patch(PAUSED, return_value=False),
    ):
        resp = client.get("/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["running"] is True
    assert body["initialized"] is True
    assert body["config_summary"]["active_page_id"] == "page-1"
    assert body["boards"]["b1"] == {
        "configured": True,
        "paused": False,
        "active_page_id": "page-1",
        "error": None,
    }


def test_status_surfaces_the_startup_error_that_kept_a_board_unconfigured(client):
    """A board skipped at startup is visible in the API, not only the log (#1749)."""
    service = Mock()
    service.get_board_client.return_value = None
    service.board_init_errors = {"b1": "missing api key"}
    with (
        patch("src.api_server._service_running", True),
        patch(SERVICE, return_value=service),
        patch(SETTINGS_SERVICE, return_value=_settings_service()),
        patch(PAUSED, return_value=False),
    ):
        body = client.get("/status").json()
    assert body["boards"]["b1"]["configured"] is False
    assert body["boards"]["b1"]["error"] == "missing api key"


def test_status_is_503_when_the_service_could_not_be_created(client):
    with patch(SERVICE, return_value=None):
        resp = client.get("/status")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Service not initialized"


# ===========================================================================
# service — POST /start and POST /stop
# ===========================================================================


def test_start_reports_already_running_without_spawning_a_second_thread(client):
    with patch("src.api_server._service_running", True), patch("src.api_server.threading.Thread") as thread:
        resp = client.post("/start")
    assert resp.status_code == 200
    assert resp.json() == {"status": "already_running", "message": "Service is already running"}
    thread.assert_not_called()


def test_start_is_503_when_the_service_could_not_be_created(client):
    with patch("src.api_server._service_running", False), patch(SERVICE, return_value=None):
        resp = client.post("/start")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Service not initialized"


def test_start_is_503_when_re_initialization_fails(client):
    service = Mock()
    service.vb_client = None
    service.initialize.return_value = False
    with patch("src.api_server._service_running", False), patch(SERVICE, return_value=service):
        resp = client.post("/start")
    assert resp.status_code == 503
    assert "check board configuration" in resp.json()["detail"]


def test_stop_reports_not_running_when_the_loop_is_already_stopped(client):
    with patch("src.api_server._service_running", False):
        resp = client.post("/stop")
    assert resp.status_code == 200
    assert resp.json() == {"status": "not_running", "message": "Service is not running"}


def test_stop_clears_the_flag_and_tells_the_service_to_stop(client):
    running = Mock()
    with (
        patch("src.api_server._service_running", True),
        patch("src.api_server.peek_service", return_value=running),
    ):
        resp = client.post("/stop")
    assert resp.status_code == 200
    assert resp.json() == {"status": "stopped", "message": "Service stopped successfully"}
    assert running.running is False


# ===========================================================================
# service — POST /refresh
# ===========================================================================


def test_refresh_without_a_board_id_drives_every_board(client):
    service = Mock()
    with (
        patch(SERVICE, return_value=service),
        patch("src.api_server.run_board_send", return_value=(True, None)) as send,
    ):
        resp = client.post("/refresh")
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "success",
        "message": "Display refreshed successfully",
        "board_id": None,
        "sent": True,
    }
    assert send.await_count == 1


def test_refresh_reports_a_failed_pass_as_500_naming_the_reason(client):
    service = Mock()
    with (
        patch(SERVICE, return_value=service),
        patch("src.api_server.run_board_send", return_value=(False, "board unreachable")),
    ):
        resp = client.post("/refresh")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Failed to refresh display: board unreachable"


def test_refresh_takes_the_board_id_from_the_json_body_too(client):
    service = Mock()
    service.get_runtime.return_value = Mock()
    with (
        patch(SERVICE, return_value=service),
        patch(SETTINGS_SERVICE, return_value=_settings_service()),
        patch("src.api_server._require_board", return_value={"id": "b1"}),
        patch("src.api_server.run_board_send", return_value=(True, None)),
    ):
        resp = client.post("/refresh", json={"board_id": "b1"})
    assert resp.status_code == 200
    assert resp.json()["board_id"] == "b1"
    assert resp.json()["message"] == "Board b1 refreshed successfully"


def test_refresh_is_503_when_the_named_board_has_no_client(client):
    service = Mock()
    service.get_runtime.return_value = None
    with (
        patch(SERVICE, return_value=service),
        patch(SETTINGS_SERVICE, return_value=_settings_service()),
        patch("src.api_server._require_board", return_value={"id": "b1"}),
    ):
        resp = client.post("/refresh?board_id=b1")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Board client not initialized: b1"


def test_refresh_is_503_when_the_service_could_not_be_created(client):
    with patch(SERVICE, return_value=None):
        assert client.post("/refresh").status_code == 503


# ===========================================================================
# service — GET /silence-status
# ===========================================================================


SILENCE_OFF = {
    "enabled": False,
    "start_time": "22:00+00:00",
    "end_time": "07:00+00:00",
    "mode": "freeze",
    "page_id": None,
    "indicator_text": None,
    "indicator_position": None,
}


def test_silence_status_reports_the_window_and_the_board_it_describes(client):
    with (
        patch(SETTINGS_SERVICE, return_value=_settings_service()),
        patch("src.config.resolve_silence_schedule", return_value=dict(SILENCE_OFF)),
    ):
        resp = client.get("/silence-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["active"] is False
    assert body["start_time_utc"] == "22:00+00:00"
    assert body["end_time_utc"] == "07:00+00:00"
    assert body["mode"] == "freeze"
    assert body["page_id"] is None
    assert body["indicator_text"] is None
    assert body["indicator_position"] is None
    # Omitted board_id means "the board you drive by default" (#1788).
    assert body["board_id"] == "b1"
    # Disabled: there is no next transition to count down to.
    assert body["seconds_until_next_change"] is None
    assert body["current_time_utc"].endswith("+00:00")


def test_silence_status_echoes_an_explicit_board_id(client):
    with (
        patch(SETTINGS_SERVICE, return_value=_settings_service()),
        patch("src.config.resolve_silence_schedule", return_value=dict(SILENCE_OFF)),
    ):
        body = client.get("/silence-status?board_id=b2").json()
    assert body["board_id"] == "b2"


def test_silence_status_counts_down_to_the_next_change_when_enabled(client):
    enabled = dict(SILENCE_OFF, enabled=True)
    with (
        patch(SETTINGS_SERVICE, return_value=_settings_service()),
        patch("src.config.resolve_silence_schedule", return_value=enabled),
    ):
        body = client.get("/silence-status").json()
    assert body["enabled"] is True
    assert isinstance(body["seconds_until_next_change"], int)
    assert 0 <= body["seconds_until_next_change"] <= 86_400


# ===========================================================================
# board — GET /board/current-message
# ===========================================================================


def _grid(rows: int = 6, cols: int = 22, code: int = 0) -> list[list[int]]:
    return [[code] * cols for _ in range(rows)]


def test_current_message_serves_the_poll_cache_with_its_timestamp(client):
    service = Mock()
    service.vb_client = Mock(use_cloud=False, _last_characters=_grid(code=1))
    service._polled_characters = _grid(code=2)
    service._polled_at = 1_700_000_000.0
    with patch(SERVICE, return_value=service):
        resp = client.get("/board/current-message")
    assert resp.status_code == 200
    body = resp.json()
    assert body["characters"] == _grid(code=2)
    assert body["message"].splitlines()[0] == "B" * 22
    assert body["rows"] == 6
    assert body["cols"] == 22
    assert body["expected_characters"] == _grid(code=1)
    assert body["cached_at"] == "2023-11-14T22:13:20+00:00"
    assert body["api_mode"] == "local"
    assert body["board_id"] is None


def test_current_message_force_reads_the_board_and_primes_the_cache(client):
    live = _grid(code=3)
    service = Mock()
    service.vb_client = Mock(use_cloud=True, _last_characters=None)
    service.vb_client.read_current_message.return_value = live
    service._polled_characters = _grid(code=2)
    with patch(SERVICE, return_value=service):
        body = client.get("/board/current-message?force=true").json()
    assert body["characters"] == live
    assert body["cached_at"] is None
    assert body["api_mode"] == "cloud"
    assert service._polled_characters == live


def test_current_message_is_503_when_the_live_read_fails(client):
    service = Mock()
    service.vb_client = Mock(use_cloud=False, _last_characters=None)
    service.vb_client.read_current_message.return_value = None
    service._polled_characters = None
    with patch(SERVICE, return_value=service):
        resp = client.get("/board/current-message")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Failed to read current board message"


def test_current_message_is_503_when_no_board_client_exists(client):
    service = Mock()
    service.vb_client = None
    with patch(SERVICE, return_value=service):
        resp = client.get("/board/current-message")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Board client not initialized"


def test_current_message_returns_a_secondary_boards_geometry_before_its_first_send(client):
    """A never-written secondary board answers nulls plus its dimensions (#1247)."""
    service = Mock()
    service.vb_client = Mock(use_cloud=False, _last_characters=None)
    runtime = Mock(client=Mock(use_cloud=False, _last_characters=None), polled_characters=None, polled_at=None)
    service.get_runtime.return_value = runtime
    ss = _settings_service()
    ss.get_primary_board_id.return_value = "b1"
    with (
        patch(SERVICE, return_value=service),
        patch(SETTINGS_SERVICE, return_value=ss),
        patch(
            "src.api_server._require_board",
            return_value={"id": "b2", "device_type": "note", "notes_wide": 1, "notes_tall": 1},
        ),
    ):
        body = client.get("/board/current-message?board_id=b2").json()
    assert body == {
        "characters": None,
        "message": None,
        "rows": 3,
        "cols": 15,
        "expected_characters": None,
        "cached_at": None,
        "api_mode": "local",
        "board_id": "b2",
    }


# ===========================================================================
# board — POST /send-message
# ===========================================================================


@pytest.fixture
def now():
    return {"t": 1000.0}


@pytest.fixture
def cloud(now):
    """A REAL RW Cloud board client on a controllable clock (the send floor)."""
    return BoardClient(api_key="test_key", use_cloud=True, _time_func=lambda: now["t"])


@pytest.fixture
def wired(cloud):
    service = Mock()
    service.vb_client = cloud
    service.board_clients = {"b1": cloud}
    service.running = True
    with (
        patch(SERVICE, return_value=service),
        patch(SETTINGS_SERVICE, return_value=_settings_service()),
        patch(BOARD_CLIENT, return_value=cloud),
        patch("src.api_server.Config.is_silence_mode_active", return_value=False),
        patch(PAUSED, return_value=False),
        patch("src.board_client.requests.post") as post,
    ):
        post.return_value = _ok_response()
        yield post


def test_send_message_delivers_the_text_and_says_so(client, wired):
    resp = client.post("/send-message", json={"text": "HELLO"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "success", "message": "Message sent successfully"}
    assert wired.call_count == 1


def test_send_message_reports_unchanged_content_as_a_skip_not_a_send(client, wired, now):
    assert client.post("/send-message", json={"text": "HELLO"}).status_code == 200
    now["t"] += 16.0  # outside the cloud send floor, so this is a true dedupe skip
    resp = client.post("/send-message", json={"text": "HELLO"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "success", "message": "Message unchanged, no update needed", "skipped": True}
    assert wired.call_count == 1


def test_send_message_reports_a_write_dropped_by_the_send_floor_as_429(client, wired, now):
    assert client.post("/send-message", json={"text": "HELLO"}).status_code == 200
    now["t"] += 5.0  # inside the 15s cloud window: the write is DROPPED, not skipped
    resp = client.post("/send-message", json={"text": "WORLD"})
    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "15"
    assert wired.call_count == 1


def test_send_message_refuses_during_silence_mode(client, wired):
    with patch("src.api_server._silence_active", return_value=True):
        resp = client.post("/send-message", json={"text": "HELLO"})
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "blocked",
        "message": "Manual sends blocked during silence mode to prevent wake-ups",
        "silence_mode": True,
    }
    assert wired.call_count == 0


def test_send_message_refuses_when_the_board_is_paused(client, wired):
    with patch(PAUSED, return_value=True):
        resp = client.post("/send-message", json={"text": "HELLO"})
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "blocked",
        "message": "Board is paused — sends are blocked until it is resumed.",
        "paused": True,
        "board_id": None,
    }
    assert wired.call_count == 0


def test_send_message_is_503_when_the_service_could_not_be_created(client):
    with patch(SERVICE, return_value=None):
        resp = client.post("/send-message", json={"text": "HELLO"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Service not initialized"


def test_send_message_rejects_a_body_with_no_text_as_422(client):
    assert client.post("/send-message", json={}).status_code == 422


# ===========================================================================
# board — POST /send-welcome-message
# ===========================================================================


@pytest.fixture
def welcome_wired(cloud):
    with (
        patch(SETTINGS_SERVICE, return_value=_settings_service()),
        patch("src.api_server._primary_board_entry", return_value={"id": "b1", "device_type": "flagship"}),
        patch("src.api_server.board_client_from_board_dict", return_value=cloud),
        patch("src.api_server.Config.is_silence_mode_active", return_value=False),
        patch(PAUSED, return_value=False),
        patch("src.board_client.requests.post") as post,
    ):
        post.return_value = _ok_response()
        yield post


def test_welcome_message_sends_and_says_so(client, welcome_wired):
    resp = client.post("/send-welcome-message")
    assert resp.status_code == 200
    assert resp.json() == {"status": "success", "message": "Welcome message sent to your board!"}
    assert welcome_wired.call_count == 1


def test_welcome_message_refuses_during_silence_mode(client, welcome_wired):
    with patch("src.api_server._silence_active", return_value=True):
        resp = client.post("/send-welcome-message")
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "blocked",
        "message": "Welcome message blocked during silence mode",
        "silence_mode": True,
    }
    assert welcome_wired.call_count == 0


def test_welcome_message_refuses_when_the_board_is_paused(client, welcome_wired):
    with patch(PAUSED, return_value=True):
        resp = client.post("/send-welcome-message")
    assert resp.status_code == 200
    assert resp.json()["status"] == "blocked"
    assert resp.json()["paused"] is True
    assert welcome_wired.call_count == 0


def test_welcome_message_is_503_when_no_board_is_configured(client):
    with (
        patch("src.api_server.Config.is_silence_mode_active", return_value=False),
        patch(PAUSED, return_value=False),
        patch("src.api_server._primary_board_entry", return_value=None),
    ):
        resp = client.post("/send-welcome-message")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Board not configured: no board with a usable connection"


# ===========================================================================
# mqtt
# ===========================================================================


def test_mqtt_status_reports_off_when_no_client_is_wired(client):
    with patch("src.mqtt.get_mqtt_client", return_value=None):
        resp = client.get("/mqtt/status")
    assert resp.status_code == 200
    assert resp.json() == {"enabled": False, "connected": False, "running": False}


def test_mqtt_status_reports_the_live_clients_two_flags(client):
    mqtt = Mock()
    mqtt.is_connected.return_value = True
    mqtt.is_running.return_value = False
    with patch("src.mqtt.get_mqtt_client", return_value=mqtt):
        resp = client.get("/mqtt/status")
    assert resp.status_code == 200
    assert resp.json() == {"enabled": True, "connected": True, "running": False}


def test_mqtt_status_is_500_when_it_cannot_tell(client):
    """'enabled: false' is a real answer, so it must never double as 'unknown' (#1887)."""
    with patch("src.mqtt.get_mqtt_client", side_effect=RuntimeError("broker exploded")):
        resp = client.get("/mqtt/status")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Failed to read MQTT status."


def test_republish_discovery_asks_the_client_to_republish(client):
    mqtt = Mock()
    mqtt.is_connected.return_value = True
    with patch("src.mqtt.get_mqtt_client", return_value=mqtt):
        resp = client.post("/mqtt/republish-discovery")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "message": "Discovery messages republished"}
    mqtt._publish_discovery.assert_called_once_with()


def test_republish_discovery_is_503_when_mqtt_is_not_connected(client):
    mqtt = Mock()
    mqtt.is_connected.return_value = False
    with patch("src.mqtt.get_mqtt_client", return_value=mqtt):
        resp = client.post("/mqtt/republish-discovery")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "MQTT client not connected"


def test_republish_discovery_is_503_when_no_client_is_wired(client):
    with patch("src.mqtt.get_mqtt_client", return_value=None):
        assert client.post("/mqtt/republish-discovery").status_code == 503


# ===========================================================================
# backup
# ===========================================================================


def test_export_serves_the_backup_as_a_timestamped_download(client):
    svc = Mock()
    svc.export_to_json.return_value = '{"fiestaboard_backup": true}'
    with patch("src.backup.get_backup_service", return_value=svc):
        resp = client.get("/backup/export")
    assert resp.status_code == 200
    assert resp.json() == {"fiestaboard_backup": True}
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.headers["cache-control"] == "no-store"
    disposition = resp.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="fiestaboard-backup-')
    assert disposition.endswith('.json"')


IMPORT_RESULT = {
    "status": "success",
    "restored_files": ["pages.json"],
    "skipped_files": ["schedules.json"],
    "pre_restore_backup_suffix": ".pre-restore-20260101-000000",
    "pre_restore_backup_files": ["pages.json"],
    "plugins": {
        "attempted": ["weather"],
        "installed": ["weather"],
        "already_present": [],
        "failed": [],
        "manual_reinstall_required": [],
    },
    "reload_errors": [],
}


def test_import_returns_what_was_restored_skipped_and_reinstalled(client):
    svc = Mock()
    svc.import_from_dict.return_value = dict(IMPORT_RESULT)
    with patch("src.backup.get_backup_service", return_value=svc):
        resp = client.post("/backup/import", json={"fiestaboard_backup": True, "data": {}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["restored_files"] == ["pages.json"]
    assert body["skipped_files"] == ["schedules.json"]
    assert body["pre_restore_backup_suffix"] == ".pre-restore-20260101-000000"
    assert body["pre_restore_backup_files"] == ["pages.json"]
    assert body["plugins"]["installed"] == ["weather"]
    assert body["reload_errors"] == []
    svc.import_from_dict.assert_called_once_with({"fiestaboard_backup": True, "data": {}}, reinstall_plugins=True)


def test_import_honors_reinstall_plugins_false(client):
    svc = Mock()
    svc.import_from_dict.return_value = dict(IMPORT_RESULT)
    with patch("src.backup.get_backup_service", return_value=svc):
        client.post("/backup/import?reinstall_plugins=false", json={"fiestaboard_backup": True})
    svc.import_from_dict.assert_called_once_with({"fiestaboard_backup": True}, reinstall_plugins=False)


def test_import_blames_the_uploaded_file_with_400(client):
    from src.backup import BackupError

    svc = Mock()
    svc.import_from_dict.side_effect = BackupError("File does not look like a FiestaBoard backup")
    with patch("src.backup.get_backup_service", return_value=svc):
        resp = client.post("/backup/import", json={"nope": True})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "File does not look like a FiestaBoard backup"


def test_import_blames_the_environment_with_500_when_the_restore_aborts(client):
    """A full disk is not the operator's backup being wrong (Task 10d)."""
    from src.backup import BackupRestoreAborted

    svc = Mock()
    svc.import_from_dict.side_effect = BackupRestoreAborted("could not write pre-restore copy")
    with patch("src.backup.get_backup_service", return_value=svc):
        resp = client.post("/backup/import", json={"fiestaboard_backup": True})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "could not write pre-restore copy"


def test_import_never_leaks_an_unexpected_exception_into_the_response(client):
    svc = Mock()
    svc.import_from_dict.side_effect = RuntimeError("/data/pages.json line 3 col 7")
    with patch("src.backup.get_backup_service", return_value=svc):
        resp = client.post("/backup/import", json={"fiestaboard_backup": True})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Backup import failed"


def test_import_rejects_a_body_that_is_not_a_json_object_as_422(client):
    assert client.post("/backup/import", json=[1, 2, 3]).status_code == 422


def test_export_and_import_round_trip_through_the_same_document(client):
    """The export body is exactly what import accepts — the migration path (#1) works."""
    document = {"fiestaboard_backup": True, "schema_version": 1, "data": {"pages.json": {"pages": []}}}
    export_svc = Mock()
    export_svc.export_to_json.return_value = json.dumps(document)
    import_svc = Mock()
    import_svc.import_from_dict.return_value = dict(IMPORT_RESULT)
    with patch("src.backup.get_backup_service", return_value=export_svc):
        exported = client.get("/backup/export").json()
    with patch("src.backup.get_backup_service", return_value=import_svc):
        assert client.post("/backup/import", json=exported).status_code == 200
    import_svc.import_from_dict.assert_called_once_with(document, reinstall_plugins=True)
