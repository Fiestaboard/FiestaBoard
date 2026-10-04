"""Vestaboard knowledge behind output hooks (plan Phase 1.6).

Core asks the board's *output* — through its registry entry's hooks or its
driver — instead of knowing Vestaboard:

- ``discover`` (``POST /config/board/scan``), ``diagnostics``
  (``GET /debug/network-diagnostics``) and the ``enable_local_api`` action
  are hooks on the ``vestaboard`` registry entry; ``fiestapanel`` has none;
- ``check_connection`` (a structured :class:`ConnectionCheck`), ``read_back``
  and ``connection_label`` are the driver's;
- the MQTT device ``model`` is the primary board's output name.

Plus the literal ratchet: Vestaboard transport literals left in ``src/``
outside the vestaboard output's modules may only go down (Phase 4: zero).
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import requests

from src.board_client import CLOUD_REQUEST_TIMEOUT, LOCAL_REQUEST_TIMEOUT, BoardClient
from src.note_array_local_client import NoteArrayLocalClient
from src.outputs.hooks import ConnectionCheck, UnknownOutputAction
from src.outputs.registry import (
    FIESTAPANEL,
    VESTABOARD,
    UnknownOutputError,
    discover_devices,
    output_action,
    output_registry,
)
from src.virtual_board_client import VirtualBoardClient

REPO = Path(__file__).resolve().parents[1]

LOCAL_HOST = "192.0.2.10"
LOCAL_URL = f"http://{LOCAL_HOST}:7000/local-api/message"
BOARD_GRID = {"message": [[0] * 22 for _ in range(6)]}


def _local() -> BoardClient:
    return BoardClient(api_key="test_local_key", host=LOCAL_HOST)


def _cloud() -> BoardClient:
    return BoardClient(api_key="test_rw_key", use_cloud=True)


def _response(status: int, body=None) -> Mock:
    response = Mock(status_code=status)
    response.json.return_value = body
    return response


# --- the registry entries declare their hooks ------------------------------------


class TestRegistryHooks:
    def test_vestaboard_declares_discover_diagnostics_and_enable_local_api(self):
        hooks = output_registry().get(VESTABOARD).hooks
        assert hooks.discover is not None
        assert hooks.diagnostics is not None
        assert set(hooks.actions) == {"enable_local_api"}

    def test_fiestapanel_declares_no_device_hooks(self):
        """No discovery, diagnostics or custom action: a FiestaPanel has no
        device. Its one board-settings action (test_connection, plan D13) is
        answered by ``dispatch`` and says so."""
        hooks = output_registry().get(FIESTAPANEL).hooks
        assert (hooks.discover, hooks.diagnostics, dict(hooks.actions)) == (None, None, {})
        assert [a.id for a in output_registry().get(FIESTAPANEL).actions] == ["test_connection"]

    def test_discover_devices_runs_the_outputs_discover_hook_with_the_timeout(self):
        found = [{"ip": "192.0.2.50", "port": 7000, "hostname": "", "source": "port_scan"}]
        with patch("src.outputs.vestaboard.discovery.discover", return_value=found) as discover:
            assert discover_devices(VESTABOARD, 2.5) == found
        discover.assert_called_once_with(2.5)

    def test_an_output_without_a_discover_hook_discovers_nothing(self):
        assert discover_devices(FIESTAPANEL, 1.0) == []

    def test_discovering_with_an_unknown_output_is_refused(self):
        with pytest.raises(UnknownOutputError):
            discover_devices("not-installed", 1.0)

    def test_an_action_the_output_does_not_have_is_refused(self):
        with pytest.raises(UnknownOutputAction):
            output_action(FIESTAPANEL, "enable_local_api")


# --- check_connection: structured, over the client's own request path ------------


class TestCheckConnectionTransport:
    """A4 wire-goldens finding 4: the probe used a single ``timeout=10`` and its
    own ``requests.get``. It now goes through the driver with the client's
    ``(connect, read)`` pair."""

    def test_local_probe_uses_the_clients_url_headers_and_split_timeout(self):
        with patch("requests.get", return_value=_response(200, BOARD_GRID)) as get:
            _local().check_connection()
        assert get.call_args.args == (LOCAL_URL,)
        assert get.call_args.kwargs["headers"]["X-Vestaboard-Local-Api-Key"] == "test_local_key"
        assert get.call_args.kwargs["timeout"] == LOCAL_REQUEST_TIMEOUT == (3.0, 10.0)

    def test_cloud_probe_uses_the_cloud_split_timeout(self):
        with patch("requests.get", return_value=_response(200, BOARD_GRID)) as get:
            _cloud().check_connection()
        assert get.call_args.args == (BoardClient.CLOUD_API_URL,)
        assert get.call_args.kwargs["timeout"] == CLOUD_REQUEST_TIMEOUT == (5.0, 10.0)

    def test_a_host_outside_the_allow_list_is_blocked_without_a_request(self, monkeypatch):
        monkeypatch.setenv("FIESTABOARD_OUTPUTS_ALLOW_HOSTS", "fiestaboard-mock-board")
        with patch("requests.get") as get:
            check = _local().check_connection()
        get.assert_not_called()
        assert (check.success, check.failure, check.error) == (False, "blocked", "Host not allowed")


class TestCheckConnectionFailureClasses:
    @pytest.mark.parametrize(
        ("answer", "failure", "error"),
        [
            (_response(401), "auth", "HTTP 401"),
            (_response(403), "auth", "HTTP 403"),
            (_response(503), "server_error", "HTTP 503"),
            (_response(418), "unexpected_status", "HTTP 418"),
            (
                _response(200, {"unexpected": True}),
                "bad_response",
                "Unrecognized read response (JSON keys: unexpected).",
            ),
            (requests.exceptions.ConnectionError("refused"), "unreachable", "Connection error"),
            (requests.exceptions.ConnectTimeout("connect timed out"), "unreachable", "Connection error"),
            (requests.exceptions.ReadTimeout("read timed out"), "timeout", "Timeout"),
        ],
        ids=["401", "403", "503", "418", "bad-body", "refused", "connect-timeout", "read-timeout"],
    )
    def test_each_failure_is_classified(self, answer, failure, error):
        kwargs = {"side_effect": answer} if isinstance(answer, Exception) else {"return_value": answer}
        with patch("requests.get", **kwargs):
            check = _local().check_connection()
        assert (check.success, check.failure, check.error) == (False, failure, error)
        assert check.troubleshooting, "every failure carries troubleshooting"

    def test_invalid_json_is_a_bad_response(self):
        response = _response(200)
        response.json.side_effect = ValueError("not json")
        with patch("requests.get", return_value=response):
            check = _local().check_connection()
        assert (check.failure, check.error) == ("bad_response", "Invalid JSON response")

    def test_a_board_read_is_success_with_the_api_mode(self):
        with patch("requests.get", return_value=_response(200, BOARD_GRID)):
            check = _cloud().check_connection()
        assert check == ConnectionCheck(
            success=True, message="Successfully connected to your board!", details={"api_mode": "cloud"}
        )

    def test_an_unanticipated_error_is_not_a_verdict(self):
        with patch("requests.get", side_effect=RuntimeError("boom")), pytest.raises(RuntimeError):
            _local().check_connection()


class TestConnectionCheckWireShape:
    def test_success_verdict_is_success_message_and_details(self):
        check = ConnectionCheck(success=True, message="ok", details={"api_mode": "local"})
        assert check.to_verdict() == {"success": True, "message": "ok", "api_mode": "local"}

    def test_failure_verdict_carries_error_and_troubleshooting_but_not_the_class(self):
        check = ConnectionCheck(success=False, message="no", failure="auth", error="HTTP 401", troubleshooting=("a",))
        assert check.to_verdict() == {"success": False, "message": "no", "error": "HTTP 401", "troubleshooting": ["a"]}

    def test_drivers_without_a_richer_probe_report_reachability(self):
        assert VirtualBoardClient(device_type="flagship").check_connection().success is True
        array = NoteArrayLocalClient([{"row": 0, "col": 0, "host": "192.0.2.11", "local_api_key": "k"}], 1, 1)
        with patch.object(array, "test_connection", return_value=False):
            check = array.check_connection()
        assert (check.success, check.failure) == (False, "unreachable")


# --- capabilities the driver declares -----------------------------------------------


def _drivers() -> dict[str, object]:
    return {
        "local": _local(),
        "rw-cloud": _cloud(),
        "note-array-cloud": BoardClient(api_key="t", use_cloud=True, note_array_token="t"),
        "note-array-local": NoteArrayLocalClient(
            [{"row": 0, "col": 0, "host": "192.0.2.11", "local_api_key": "k"}], 1, 1
        ),
        "virtual": VirtualBoardClient(device_type="flagship"),
    }


@pytest.mark.parametrize(
    ("kind", "cost", "interval", "label"),
    [
        ("local", "cheap", 30, "Local API"),
        ("rw-cloud", "network", 180, "Cloud API"),
        ("note-array-cloud", "network", 180, "Cloud API"),
        ("note-array-local", "cheap", 30, "Local API"),
        # A panel has always reported "Local API" (it was use_cloud=False).
        ("virtual", "cheap", 30, "Local API"),
    ],
)
def test_driver_declares_read_back_and_connection_label(kind, cost, interval, label):
    driver = _drivers()[kind]
    assert (driver.read_back.supported, driver.read_back.cost, driver.read_back.suggested_interval_s) == (
        True,
        cost,
        interval,
    )
    assert driver.connection_label == label


@pytest.mark.parametrize(("kind", "expected"), [("local", 31), ("rw-cloud", 181), ("virtual", 31)])
def test_board_read_poll_interval_follows_the_drivers_read_back_cost(kind, expected):
    from src.main import DisplayService

    settings = Mock()
    settings.get_polling_settings.return_value = SimpleNamespace(
        board_read_interval_local=31, board_read_interval_cloud=181
    )
    with patch("src.main.get_settings_service", return_value=settings):
        interval = DisplayService._get_board_read_interval(SimpleNamespace(vb_client=_drivers()[kind]))
    assert interval == expected


# --- MQTT: the device model is the primary board's output -----------------------------


@pytest.mark.parametrize(
    ("board", "model"),
    [
        ({"id": "b", "api_mode": "local", "host": LOCAL_HOST}, "Vestaboard"),
        ({"id": "p", "device_type": "panel", "api_mode": "virtual"}, "FiestaPanel"),
        (None, "Vestaboard"),
    ],
    ids=["vestaboard", "fiestapanel", "no-board"],
)
def test_mqtt_model_is_the_primary_boards_output_name(board, model):
    from src.mqtt.discovery import primary_board_model

    with patch("src.board_guards.primary_board_entry", return_value=board):
        assert primary_board_model() == model


def test_mqtt_device_info_defaults_to_the_default_outputs_name():
    from src.mqtt.config import MQTTConfig
    from src.mqtt.discovery import build_device_info

    config = MQTTConfig(instance_id="fiestaboard_test")
    assert build_device_info(config)["model"] == "Vestaboard"
    assert build_device_info(config, model="FiestaPanel")["model"] == "FiestaPanel"


# --- diagnostics: core asks the board's output ------------------------------------------


@pytest.fixture
def core_checks_ok():
    with (
        patch("src.network_diagnostics.check_dns_resolution", return_value={"ok": True}),
        patch("src.network_diagnostics.check_internet_connectivity", return_value={"ok": True}),
    ):
        yield


def test_a_board_whose_output_has_no_diagnostics_reports_the_unconfigured_section(core_checks_ok):
    from src.network_diagnostics import run_full_diagnostics

    with patch("src.outputs.vestaboard.diagnostics.check_vestaboard_connection") as vestaboard:
        result = run_full_diagnostics({"id": "p", "api_mode": "virtual", "host": LOCAL_HOST})
    vestaboard.assert_not_called()
    assert result["vestaboard"] == {
        "ok": False,
        "mode": None,
        "steps": {},
        "error": "No board host or cloud key configured",
    }
    assert result["recommendations"] == []


def test_a_vestaboard_board_is_diagnosed_by_the_vestaboard_hook(core_checks_ok):
    from src.network_diagnostics import run_full_diagnostics

    section = {"ok": True, "mode": "local", "steps": {}}
    with patch("src.outputs.vestaboard.diagnostics.check_vestaboard_connection", return_value=section) as vestaboard:
        result = run_full_diagnostics({"host": LOCAL_HOST, "local_api_key": "k"})
    vestaboard.assert_called_once_with(host=LOCAL_HOST, port=7000, api_key="k")
    assert result["vestaboard"] == section
    assert result["recommendations"] == [
        {"summary": "All checks passed — your Vestaboard connection is healthy", "steps": []}
    ]


# --- the literal ratchet -----------------------------------------------------------------

#: The vestaboard output's modules: the drivers and the hooks package.
VESTABOARD_OUTPUT_MODULES = (
    REPO / "src" / "board_client.py",
    REPO / "src" / "note_array_local_client.py",
    REPO / "src" / "outputs" / "vestaboard",
)

_VESTABOARD_LITERAL = re.compile(r"vestaboard\.com|X-Vestaboard-|/local-api/|\b7000\b")

#: Vestaboard transport literals left in src/ outside the vestaboard output's
#: modules. Was 36 before refactor/vestaboard-behind-hooks. It may only go
#: down; Phase 4 drives it to 0 and turns on the full no-literals ratchet.
MAX_VESTABOARD_LITERALS = 9


def _is_vestaboard_module(path: Path) -> bool:
    return any(path == module or module in path.parents for module in VESTABOARD_OUTPUT_MODULES)


def _vestaboard_literals(root: Path) -> list[str]:
    found = []
    for path in sorted(root.rglob("*.py")):
        if _is_vestaboard_module(path):
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            found.extend(f"{path.relative_to(root.parent)}:{lineno} {m}" for m in _VESTABOARD_LITERAL.findall(line))
    return found


def test_vestaboard_literals_outside_the_output_never_increase():
    found = _vestaboard_literals(REPO / "src")
    listing = "\n  ".join(found)
    assert len(found) <= MAX_VESTABOARD_LITERALS, (
        f"{len(found)} Vestaboard literals in src/ outside the vestaboard output (max "
        f"{MAX_VESTABOARD_LITERALS}). Ask the output (src/outputs/hooks.py) instead:\n  {listing}"
    )
    assert len(found) == MAX_VESTABOARD_LITERALS, (
        f"Only {len(found)} remain — lower MAX_VESTABOARD_LITERALS to {len(found)}:\n  {listing}"
    )


def test_literal_ratchet_scanner_sees_a_planted_literal(tmp_path):
    planted = tmp_path / "src" / "planted.py"
    planted.parent.mkdir()
    planted.write_text('URL = "https://rw.vestaboard.com/"\nHDR = "X-Vestaboard-Token"\nPORT = 7000\n')
    assert len(_vestaboard_literals(planted.parent)) == 3
