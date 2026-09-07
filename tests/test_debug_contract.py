"""Value-level contract goldens for the /debug API (Phase 2 §2, Task 8).

These are deliberately *values*, not shapes. The shape corpus in
``tests/test_response_shape_goldens.py`` records key sets and type names, so it
cannot see a wrong message, a dropped ``latency_ms``, a grid filled with the
wrong character code, or a failure reported at HTTP 200 — which is exactly the
class of defect this domain is full of.

The eight ``/debug/*`` routes plus their four siblings (``GET /cache-status``,
``POST /clear-cache``, ``POST /force-refresh``, ``GET /logs``) are pinned here
by value **before** the extraction and the conventions pass, so the conversion
has something to be measured against.

Seam targets
------------
Every ``patch()`` target in this file is a module constant below. The slice
moves handlers out of ``src/api_server.py`` and their collaborators into
``src/display_runtime.py``; only the constants change when that happens, never
an assertion. If you find yourself editing an ``assert`` to make this file
pass, stop — that is a contract change and it belongs in the docstring's
change list with a reason.

Re-pinned by the conventions pass in this same PR. What deliberately changed,
and nothing else:

* **Bare bodies.** Every ``{"status": "success", ...}`` envelope in the domain
  is gone. ``/debug/blank``, ``/debug/fill``, ``/debug/clear-cache`` and
  ``/clear-cache`` answer ``{"message": ...}``; ``/debug/info`` answers
  ``{"message", "debug_info"}``; ``/debug/test-connection`` drops ``status``
  and keeps ``connected``/``latency_ms``; ``/debug/cache-status`` and
  ``/debug/network-diagnostics`` return the cache and the diagnostics
  themselves rather than wrapping them; ``/force-refresh`` answers
  ``{"message", "sent"}``.
* **A paused board is a 409**, not a 200 carrying
  ``{"status": "blocked", "paused": true}``. Issue #970 made these endpoints
  skip the send; reporting the skip at 200 meant every client that checks
  only the status code read "sent". ``POST /debug/info`` no longer returns the
  card text on that path — ``GET /debug/system-info`` serves the same data
  and never sends.
* **A throttled write keeps its 429 but serves the standard error body.**
  ``{"status": "throttled", "message", "retry_after_seconds"}`` became
  ``{"detail": ...}``; the ``Retry-After`` header is unchanged and is still
  where the number belongs.
* **``POST /debug/fill`` validates through Pydantic**, so a missing, wrongly
  typed or out-of-range ``character_code`` is FastAPI's 422 instead of a
  hand-rolled 400. ``StrictInt`` also closes a hole the hand-rolled check
  left: ``isinstance(True, int)`` is true, so ``{"character_code": true}``
  used to fill the board with code 1.
* **The 500 detail stopped stuttering.** A refused send served
  ``"500: Failed to blank board"``, because the ``raise`` sat inside the
  handler's own ``try`` and its ``except Exception`` re-raised
  ``HTTPException(500, str(e))``. It now serves ``"Failed to blank board"``.

Every other value — the grids actually sent, the six lines of the debug card,
message strings, the diagnostics pass-through, the log page and its filters,
and the 400/500/503 paths — is unchanged from the pre-conversion recording.
None was weakened.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

# --- Seam targets (see module docstring) -----------------------------------
BOARD_CLIENT = "src.api_server._get_board_client"
SETTINGS_SERVICE = "src.api_server.get_settings_service"
SERVICE = "src.api_server.get_service"
BOARD_ENTRY = "src.api_server._primary_board_entry"
DIAGNOSTICS = "src.network_diagnostics.run_full_diagnostics"
READ_LOGS = "src.api_server._read_logs_from_files"
NOTE_OUT_OF_BAND = "src.api_server._note_out_of_band_write"

FLAGSHIP_ROWS, FLAGSHIP_COLS = 6, 22

CACHE_STATUS = {
    "has_cached_text": True,
    "has_cached_characters": True,
    "skip_unchanged_enabled": True,
    "cached_text_preview": "HELLO WORLD",
}


@pytest.fixture
def client():
    from src.api_server import app

    return TestClient(app)


def _settings(*, send_to_board=True, paused=False):
    settings = Mock()
    settings.should_send_to_board.return_value = send_to_board
    settings.is_paused.return_value = paused
    board_settings = Mock()
    board_settings.boards = [{"device_type": "flagship", "notes_wide": 1, "notes_tall": 1}]
    settings.get_board_settings.return_value = board_settings
    settings.get_primary_board_id.return_value = None
    return settings


def _board_client(*, sent=(True, True), connected=True, throttled=False):
    board = Mock()
    board.send_characters.return_value = sent
    board.test_connection.return_value = connected
    board.clear_cache.return_value = None
    board.get_cache_status.return_value = dict(CACHE_STATUS)
    board.last_send_throttled = throttled
    board.min_send_interval_ms = 15000
    return board


@pytest.fixture
def board(client):
    """A configured, reachable, unpaused primary board."""
    board = _board_client()
    with (
        patch(BOARD_CLIENT, return_value=board),
        patch(SETTINGS_SERVICE, return_value=_settings()),
        patch(NOTE_OUT_OF_BAND),
    ):
        yield board


# ---------------------------------------------------------------------------
# POST /debug/blank
# ---------------------------------------------------------------------------


def test_blank_sends_an_all_space_grid_sized_to_the_board(client, board):
    response = client.post("/debug/blank")

    assert response.status_code == 200
    assert response.json() == {"message": "Board blanked successfully"}
    grid = board.send_characters.call_args.args[0]
    assert grid == [[0] * FLAGSHIP_COLS for _ in range(FLAGSHIP_ROWS)]
    assert board.send_characters.call_args.kwargs == {"force": True}


def test_blank_without_a_configured_board_is_a_400(client):
    with patch(BOARD_CLIENT, return_value=None):
        response = client.post("/debug/blank")

    assert response.status_code == 400
    assert response.json()["detail"] == "Board not configured"


def test_blank_with_a_ui_only_output_target_reports_success_without_sending(client):
    board = _board_client()
    with (
        patch(BOARD_CLIENT, return_value=board),
        patch(SETTINGS_SERVICE, return_value=_settings(send_to_board=False)),
    ):
        response = client.post("/debug/blank")

    assert response.status_code == 200
    assert response.json() == {"message": "Board blank (output target is UI only)"}
    board.send_characters.assert_not_called()


def test_blank_on_a_paused_board_is_a_409(client):
    board = _board_client()
    with (
        patch(BOARD_CLIENT, return_value=board),
        patch(SETTINGS_SERVICE, return_value=_settings(paused=True)),
    ):
        response = client.post("/debug/blank")

    assert response.status_code == 409
    assert response.json() == {"detail": "Board is paused — sends are blocked until it is resumed."}
    board.send_characters.assert_not_called()


def test_blank_reports_a_refused_send_as_a_500(client):
    board = _board_client(sent=(False, False))
    with (
        patch(BOARD_CLIENT, return_value=board),
        patch(SETTINGS_SERVICE, return_value=_settings()),
    ):
        response = client.post("/debug/blank")

    assert response.status_code == 500
    # Was "500: Failed to blank board" before the conventions pass — the raise
    # sat inside the handler's own try and its except re-wrapped it. See the
    # module docstring.
    assert response.json()["detail"] == "Failed to blank board"


def test_blank_dropped_by_the_send_floor_is_a_429_with_retry_after(client):
    board = _board_client(sent=(True, False), throttled=True)
    with (
        patch(BOARD_CLIENT, return_value=board),
        patch(SETTINGS_SERVICE, return_value=_settings()),
        patch(NOTE_OUT_OF_BAND),
    ):
        response = client.post("/debug/blank")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "15"


# ---------------------------------------------------------------------------
# POST /debug/fill
# ---------------------------------------------------------------------------


def test_fill_sends_a_grid_of_the_requested_character(client, board):
    response = client.post("/debug/fill", json={"character_code": 65})

    assert response.status_code == 200
    assert response.json() == {"message": "Board filled with character 65"}
    grid = board.send_characters.call_args.args[0]
    assert grid == [[65] * FLAGSHIP_COLS for _ in range(FLAGSHIP_ROWS)]


def test_fill_without_a_character_code_is_rejected(client, board):
    response = client.post("/debug/fill", json={})

    # 422, not the hand-rolled 400: the body is a Pydantic model now.
    assert response.status_code == 422
    board.send_characters.assert_not_called()


@pytest.mark.parametrize("bad", [-1, 72, "65", True, 3.5, None])
def test_fill_rejects_a_character_code_outside_the_flap_set(client, board, bad):
    """StrictInt closes the ``isinstance(True, int)`` hole the old check left."""
    response = client.post("/debug/fill", json={"character_code": bad})

    assert response.status_code == 422
    board.send_characters.assert_not_called()


def test_fill_accepts_both_ends_of_the_flap_range(client, board):
    for code in (0, 71):
        response = client.post("/debug/fill", json={"character_code": code})
        assert response.status_code == 200, response.text
        assert response.json()["message"] == f"Board filled with character {code}"


def test_fill_without_a_configured_board_is_a_400(client):
    with patch(BOARD_CLIENT, return_value=None):
        response = client.post("/debug/fill", json={"character_code": 1})

    assert response.status_code == 400
    assert response.json()["detail"] == "Board not configured"


def test_fill_on_a_paused_board_is_a_409(client):
    board = _board_client()
    with (
        patch(BOARD_CLIENT, return_value=board),
        patch(SETTINGS_SERVICE, return_value=_settings(paused=True)),
    ):
        response = client.post("/debug/fill", json={"character_code": 5})

    assert response.status_code == 409
    board.send_characters.assert_not_called()


# ---------------------------------------------------------------------------
# POST /debug/info
# ---------------------------------------------------------------------------


def _assert_debug_text(text: str) -> None:
    """The six lines the board actually shows — pinned, not just 'a string'."""
    from src import __version__

    lines = text.split("\n")
    assert len(lines) == 6, lines
    assert lines[0] == "DEBUG INFO"
    assert lines[1].startswith("BOARD: ")
    assert lines[2].startswith("SERVER: ")
    assert lines[3].startswith("UP: ")
    assert lines[4].endswith(" API")
    assert lines[5].startswith(f"V{__version__[:7]} ")


def test_info_sends_the_six_line_debug_card_and_returns_it(client, board):
    response = client.post("/debug/info")

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Debug info sent to board"
    _assert_debug_text(body["debug_info"])
    grid = board.send_characters.call_args.args[0]
    assert len(grid) == FLAGSHIP_ROWS
    assert all(len(row) == FLAGSHIP_COLS for row in grid)


def test_info_with_a_ui_only_output_target_still_returns_the_card(client):
    board = _board_client()
    with (
        patch(BOARD_CLIENT, return_value=board),
        patch(SETTINGS_SERVICE, return_value=_settings(send_to_board=False)),
    ):
        response = client.post("/debug/info")

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Debug info displayed (output target is UI only)"
    _assert_debug_text(body["debug_info"])
    board.send_characters.assert_not_called()


def test_info_on_a_paused_board_is_a_409(client):
    """The card text is no longer returned on this path — GET /debug/system-info
    serves the same data and never sends."""
    board = _board_client()
    with (
        patch(BOARD_CLIENT, return_value=board),
        patch(SETTINGS_SERVICE, return_value=_settings(paused=True)),
    ):
        response = client.post("/debug/info")

    assert response.status_code == 409
    assert response.json() == {"detail": "Board is paused — sends are blocked until it is resumed."}
    board.send_characters.assert_not_called()


def test_info_without_a_configured_board_is_a_400(client):
    with patch(BOARD_CLIENT, return_value=None):
        response = client.post("/debug/info")

    assert response.status_code == 400
    assert response.json()["detail"] == "Board not configured"


# ---------------------------------------------------------------------------
# POST /debug/test-connection
# ---------------------------------------------------------------------------


def test_test_connection_reports_a_reachable_board_with_its_latency(client, board):
    response = client.post("/debug/test-connection")

    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    assert isinstance(body["latency_ms"], int)
    assert body["message"] == f"Connection successful (latency: {body['latency_ms']}ms)"


def test_test_connection_on_an_unreachable_board_is_a_503(client):
    """#1887: a 200 carrying ``status: "error"`` was indistinguishable from success."""
    with (
        patch(BOARD_CLIENT, return_value=_board_client(connected=False)),
        patch(SETTINGS_SERVICE, return_value=_settings()),
    ):
        response = client.post("/debug/test-connection")

    assert response.status_code == 503
    assert response.json()["detail"] == "Could not reach the board."


def test_test_connection_surfaces_an_unexpected_error_as_a_500(client):
    board = _board_client()
    board.test_connection.side_effect = RuntimeError("socket exploded")
    with patch(BOARD_CLIENT, return_value=board):
        response = client.post("/debug/test-connection")

    assert response.status_code == 500
    assert response.json()["detail"] == "Connection test failed."
    assert "socket exploded" not in response.text


def test_test_connection_without_a_configured_board_is_a_400(client):
    with patch(BOARD_CLIENT, return_value=None):
        response = client.post("/debug/test-connection")

    assert response.status_code == 400
    assert response.json()["detail"] == "Board not configured"


# ---------------------------------------------------------------------------
# POST /debug/clear-cache and GET /debug/cache-status
# ---------------------------------------------------------------------------


def test_debug_clear_cache_clears_the_board_clients_cache(client, board):
    response = client.post("/debug/clear-cache")

    assert response.status_code == 200
    assert response.json() == {"message": "Cache cleared - next message will be sent regardless of content"}
    board.clear_cache.assert_called_once_with()


def test_debug_clear_cache_without_a_configured_board_is_a_400(client):
    with patch(BOARD_CLIENT, return_value=None):
        response = client.post("/debug/clear-cache")

    assert response.status_code == 400
    assert response.json()["detail"] == "Board not configured"


def test_debug_cache_status_returns_the_clients_cache_fields(client, board):
    response = client.get("/debug/cache-status")

    assert response.status_code == 200
    assert response.json() == CACHE_STATUS


def test_debug_cache_status_without_a_configured_board_is_a_400(client):
    with patch(BOARD_CLIENT, return_value=None):
        response = client.get("/debug/cache-status")

    assert response.status_code == 400
    assert response.json()["detail"] == "Board not configured"


# ---------------------------------------------------------------------------
# GET /debug/system-info
# ---------------------------------------------------------------------------


def test_system_info_reports_the_running_version_and_the_live_cache(client, board):
    from src import __version__

    response = client.get("/debug/system-info")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == __version__
    assert body["cache_status"] == CACHE_STATUS
    assert body["connection_mode"] in {"local", "cloud"}
    assert isinstance(body["board_configured"], bool)
    assert isinstance(body["service_running"], bool)
    assert isinstance(body["uptime_formatted"], str)
    assert body["timestamp"].endswith("Z") or "+" in body["timestamp"]


def test_system_info_reads_the_connection_from_the_boards_store(client):
    """Issue #1791: mode and host come from boards[], never wizard-era config.json."""
    board_entry = {"api_mode": "CLOUD", "host": "192.0.2.10", "device_type": "flagship"}
    with (
        patch(BOARD_CLIENT, return_value=_board_client()),
        patch(BOARD_ENTRY, return_value=board_entry),
    ):
        response = client.get("/debug/system-info")

    body = response.json()
    assert body["connection_mode"] == "cloud"
    assert body["board_ip"] == "192.0.2.10"


def test_system_info_with_no_board_entry_reports_unconfigured(client):
    with (
        patch(BOARD_CLIENT, return_value=None),
        patch(BOARD_ENTRY, return_value=None),
    ):
        response = client.get("/debug/system-info")

    body = response.json()
    assert body["board_configured"] is False
    assert body["cache_status"] is None
    assert body["connection_mode"] == "local"
    assert body["board_ip"] == ""


# ---------------------------------------------------------------------------
# GET /debug/network-diagnostics
# ---------------------------------------------------------------------------

DIAGNOSTIC_RESULT = {
    "dns": {"ok": True, "hostname": "example.com", "ip": "203.0.113.5"},
    "internet": {"ok": True, "url": "https://example.com", "status_code": 204},
    "vestaboard": {"ok": False, "mode": "local", "steps": {}, "error": "timed out"},
    "overall_ok": False,
    "recommendations": [{"summary": "Check the board", "steps": ["Power cycle it"]}],
}


#: What the client is served for DIAGNOSTIC_RESULT after the conventions pass.
#: The per-probe keys are now always present: each probe reports a different
#: subset (DNS has hostname/ip, the port check has host/port, the HTTP checks
#: have url/status_code), and a key that is sometimes absent and sometimes
#: present forces every consumer to guess. Absent is now explicit null — the
#: "sometimes-absent key" fix the slice recipe calls for. No probe's own values
#: change, and unknown keys still pass through (extra="allow").
SERVED_DIAGNOSTICS = {
    "dns": {
        "ok": True,
        "hostname": "example.com",
        "ip": "203.0.113.5",
        "url": None,
        "host": None,
        "port": None,
        "status_code": None,
        "latency_ms": None,
        "error": None,
    },
    "internet": {
        "ok": True,
        "hostname": None,
        "ip": None,
        "url": "https://example.com",
        "host": None,
        "port": None,
        "status_code": 204,
        "latency_ms": None,
        "error": None,
    },
    "vestaboard": {"ok": False, "mode": "local", "steps": {}, "error": "timed out"},
    "overall_ok": False,
    "recommendations": [{"summary": "Check the board", "steps": ["Power cycle it"]}],
}


def test_network_diagnostics_returns_the_runners_verdict(client):
    with (
        patch(BOARD_ENTRY, return_value={"host": "192.0.2.10", "port": 7000}),
        patch(DIAGNOSTICS, return_value=DIAGNOSTIC_RESULT) as run,
    ):
        response = client.get("/debug/network-diagnostics")

    assert response.status_code == 200
    assert response.json() == SERVED_DIAGNOSTICS
    assert run.call_args.kwargs["board_host"] == "192.0.2.10"
    assert run.call_args.kwargs["board_port"] == 7000
    assert run.call_args.kwargs["use_cloud"] is False


def test_network_diagnostics_failure_is_a_500_without_the_exception_text(client):
    with (
        patch(BOARD_ENTRY, return_value=None),
        patch(DIAGNOSTICS, side_effect=RuntimeError("resolver blew up")),
    ):
        response = client.get("/debug/network-diagnostics")

    assert response.status_code == 500
    assert response.json()["detail"] == "Network diagnostics failed"
    assert "resolver blew up" not in response.text


# ---------------------------------------------------------------------------
# GET /cache-status, POST /clear-cache, POST /force-refresh
# ---------------------------------------------------------------------------


def _display_service(*, sent=True, error=None):
    service = Mock()
    service.vb_client = _board_client()
    service.board_clients = {}
    service.check_and_send_active_page_with_status.return_value = (sent, error)
    return service


def test_cache_status_returns_the_primary_clients_cache_bare(client):
    with patch(SERVICE, return_value=_display_service()):
        response = client.get("/cache-status")

    assert response.status_code == 200
    assert response.json() == CACHE_STATUS


def test_cache_status_without_an_initialized_service_is_a_503(client):
    with patch(SERVICE, return_value=None):
        response = client.get("/cache-status")

    assert response.status_code == 503
    assert response.json()["detail"] == "Service not initialized"


def test_clear_cache_clears_the_primary_clients_cache(client):
    service = _display_service()
    with patch(SERVICE, return_value=service):
        response = client.post("/clear-cache")

    assert response.status_code == 200
    assert response.json() == {"message": "Cache cleared - next update will be sent to board"}
    service.vb_client.clear_cache.assert_called_once_with()


def test_clear_cache_without_an_initialized_service_is_a_503(client):
    with patch(SERVICE, return_value=None):
        response = client.post("/clear-cache")

    assert response.status_code == 503
    assert response.json()["detail"] == "Service not initialized"


def test_force_refresh_clears_every_cache_and_reports_whether_it_sent(client):
    service = _display_service(sent=True)
    secondary = _board_client()
    service.board_clients = {"board:2": secondary}
    with patch(SERVICE, return_value=service):
        response = client.post("/force-refresh")

    assert response.status_code == 200
    assert response.json() == {"message": "Display force-refreshed successfully", "sent": True}
    service.vb_client.clear_cache.assert_called_once_with()
    secondary.clear_cache.assert_called_once_with()
    service.invalidate_all_board_content.assert_called_once_with()


def test_force_refresh_reports_a_skipped_send_without_claiming_it_sent(client):
    with patch(SERVICE, return_value=_display_service(sent=False)):
        response = client.post("/force-refresh")

    assert response.status_code == 200
    assert response.json()["sent"] is False


def test_force_refresh_surfaces_the_engines_failure_reason_as_a_500(client):
    """Issue #1791: a swallowed send failure used to report success."""
    with patch(SERVICE, return_value=_display_service(sent=False, error="board refused the key")):
        response = client.post("/force-refresh")

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to force refresh: board refused the key"


def test_force_refresh_without_an_initialized_service_is_a_503(client):
    with patch(SERVICE, return_value=None):
        response = client.post("/force-refresh")

    assert response.status_code == 503
    assert response.json()["detail"] == "Service not initialized"


# ---------------------------------------------------------------------------
# GET /logs
# ---------------------------------------------------------------------------

LOG_ENTRIES = [
    {"timestamp": "2026-09-06T00:00:02Z", "level": "ERROR", "logger": "src.main", "message": "board refused"},
    {"timestamp": "2026-09-06T00:00:01Z", "level": "INFO", "logger": "src.api", "message": "started"},
]


def test_logs_returns_entries_with_the_pagination_it_was_asked_for(client):
    with patch(READ_LOGS, return_value=(LOG_ENTRIES, 42, True)) as read:
        response = client.get("/logs", params={"limit": 2, "offset": 4})

    assert response.status_code == 200
    assert response.json() == {
        "logs": LOG_ENTRIES,
        "total": 42,
        "limit": 2,
        "offset": 4,
        "has_more": True,
        "filters": {"level": None, "search": None},
    }
    assert read.call_args.kwargs == {"limit": 2, "offset": 4, "level": None, "search": None}


def test_logs_echoes_the_normalized_filters_it_applied(client):
    with patch(READ_LOGS, return_value=([], 0, False)) as read:
        response = client.get("/logs", params={"level": "error", "search": "refused"})

    assert response.status_code == 200
    assert response.json()["filters"] == {"level": "ERROR", "search": "refused"}
    assert read.call_args.kwargs["level"] == "error"
    assert read.call_args.kwargs["search"] == "refused"


def test_logs_rejects_a_level_that_is_not_a_python_log_level(client):
    response = client.get("/logs", params={"level": "LOUD"})

    assert response.status_code == 400
    assert response.json()["detail"].startswith("Invalid log level: LOUD.")


@pytest.mark.parametrize(
    ("params", "expected"),
    [({"limit": 0}, 422), ({"limit": 501}, 422), ({"offset": -1}, 422)],
)
def test_logs_rejects_out_of_range_pagination(client, params, expected):
    response = client.get("/logs", params=params)
    assert response.status_code == expected
