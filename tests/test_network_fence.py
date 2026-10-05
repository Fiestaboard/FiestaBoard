"""The test suite cannot reach the network beyond this machine.

``pytest-socket`` runs with ``--allow-hosts`` (see ``[tool.pytest.ini_options]``
in ``pyproject.toml``), so a test that forgets to mock ``requests`` fails
loudly instead of talking to a real Vestaboard, a real plugin API, or anything
else on the internet. Loopback stays open for the in-process mock servers.
"""

import os
import socket
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from pytest_socket import SocketConnectBlockedError

from src.board_client import BoardClient
from src.network_diagnostics import check_vestaboard_connection

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# TEST-NET-3 (RFC 5737): documentation-only, never routed. Connecting to it
# without the fence would hang until timeout rather than reach anything.
_UNROUTABLE = ("203.0.113.10", 443)


def test_non_loopback_connect_is_blocked():
    with pytest.raises(SocketConnectBlockedError):
        socket.create_connection(_UNROUTABLE, timeout=1)


def test_loopback_connect_is_allowed():
    with socket.create_server(("127.0.0.1", 0)) as server:
        port = server.getsockname()[1]
        accepted = threading.Thread(target=lambda: server.accept()[0].close())
        accepted.start()
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass
        accepted.join(timeout=1)


def _cloud_url_in_fresh_interpreter(**env_overrides: str) -> str:
    """Read ``BoardClient.CLOUD_API_URL`` from a fresh import.

    The env var is read at class definition, so it is checked in a subprocess
    rather than by reloading the suite's already-imported module.
    """
    env = {k: v for k, v in os.environ.items() if k != "VESTABOARD_RW_API_URL"}
    env.update(PYTHONPATH=str(_PROJECT_ROOT), **env_overrides)
    code = "from src.board_client import BoardClient; print(BoardClient.CLOUD_API_URL)"
    return subprocess.check_output([sys.executable, "-c", code], env=env, text=True).strip()


def test_rw_cloud_url_defaults_to_vestaboard():
    assert _cloud_url_in_fresh_interpreter() == "https://rw.vestaboard.com/"


def test_rw_cloud_url_env_override():
    assert _cloud_url_in_fresh_interpreter(VESTABOARD_RW_API_URL="http://mock-host:9300/") == "http://mock-host:9300/"


@patch("src.network_diagnostics.requests.get")
def test_cloud_diagnostic_probes_the_configured_url(mock_get):
    mock_get.return_value.status_code = 200

    with patch.object(BoardClient, "CLOUD_API_URL", "http://mock-host:9300/"):
        check_vestaboard_connection(host="", use_cloud=True, cloud_key="rw-key")

    assert mock_get.call_args.args[0] == "http://mock-host:9300/"


@pytest.mark.integration
def test_integration_tests_are_exempt_from_the_fence(request):
    # Integration tests reach the real network by design (plugin installs
    # from GitHub); conftest marks them enable_socket so the fence lets them.
    assert request.node.get_closest_marker("enable_socket") is not None


def test_unit_tests_are_not_exempt(request):
    assert request.node.get_closest_marker("enable_socket") is None
