"""Failures must reach the client as failures (Phase 2, Task 10a).

Six handlers used to answer HTTP 200 for outcomes that were not successes,
so every client — the wizard, the settings page, curl, the MCP server —
saw "OK" for a request that did not do what it said. This module pins the
line drawn in ``docs/internal/reference/API_CONVENTIONS.md``:

* a **precondition** failure (missing field, malformed host, SSRF reject) is
  a real 4xx;
* an **upstream** result from a probe endpoint whose declared job is to
  report a verdict (``/config/board/test``,
  ``/config/board/enable-local-api``) may stay 200 — but only through a
  declared ``response_model``, never an ad-hoc dict;
* anything the server did not anticipate is a 5xx.
"""

from unittest.mock import Mock, patch

import pytest
import requests
from fastapi.testclient import TestClient

from src.api_server import app
from tests.test_route_inventory import build_route_metadata


@pytest.fixture
def client():
    return TestClient(app)


def _route_metadata(path: str) -> dict:
    """One route's metadata, found through the *flattened* route table.

    ``app.routes`` only lists top-level entries; a route served by an included
    router hangs off an internal node with no ``path`` of its own, so scanning
    ``app.routes`` directly silently finds nothing once a domain is extracted.
    """
    return next(r for r in build_route_metadata() if r["path"] == path)


def _local_client_mock():
    mock_client = Mock()
    mock_client.base_url = "http://192.168.1.10:7000/local-api/message"
    mock_client.headers = {}
    return mock_client


# ---------------------------------------------------------------------------
# POST /config/board/test — preconditions are 4xx
# ---------------------------------------------------------------------------


class TestBoardTestPreconditions:
    def test_missing_local_api_key_is_400(self, client):
        response = client.post("/config/board/test", json={"api_mode": "local", "host": "192.168.1.10"})
        assert response.status_code == 400
        assert "API key" in response.json()["detail"]

    def test_missing_host_is_400(self, client):
        response = client.post("/config/board/test", json={"api_mode": "local", "local_api_key": "key"})
        assert response.status_code == 400
        assert "host" in response.json()["detail"].lower()

    def test_missing_cloud_key_is_400(self, client):
        response = client.post("/config/board/test", json={"api_mode": "cloud"})
        assert response.status_code == 400

    def test_host_validation_rejection_propagates_as_400(self, client):
        """The host guard's 400 must not be downgraded to a 200 (#1887).

        ``_validate_board_host`` is the guard that stops a caller pointing
        this endpoint at an arbitrary URL. Catching its HTTPException and
        answering 200 made a rejected request indistinguishable from a
        board that merely refused the key.
        """
        with patch("src.api_server.requests.get") as mock_get:
            response = client.post(
                "/config/board/test",
                json={"api_mode": "local", "local_api_key": "key", "host": "evil.example.com/@10.0.0.1"},
            )
        assert response.status_code == 400
        mock_get.assert_not_called()


class TestBoardTestUpstreamVerdictsStay200:
    """The declared contract: an upstream board result is data, not an error."""

    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_board_rejects_key_stays_200_with_typed_body(self, mock_client_cls, mock_get, client):
        mock_client_cls.return_value = _local_client_mock()
        mock_get.return_value = Mock(status_code=401)

        response = client.post(
            "/config/board/test",
            json={"api_mode": "local", "local_api_key": "key", "host": "192.168.1.10"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert isinstance(body["troubleshooting"], list)

    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_board_unreachable_stays_200(self, mock_client_cls, mock_get, client):
        mock_client_cls.return_value = _local_client_mock()
        mock_get.side_effect = requests.exceptions.ConnectionError("refused")

        response = client.post(
            "/config/board/test",
            json={"api_mode": "local", "local_api_key": "key", "host": "192.168.1.10"},
        )
        assert response.status_code == 200
        assert response.json()["success"] is False

    def test_declares_a_response_model(self):
        assert _route_metadata("/config/board/test")["response_model"] is not None


class TestBoardTestUnexpectedErrors:
    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_unexpected_exception_is_500(self, mock_client_cls, mock_get, client):
        mock_client_cls.return_value = _local_client_mock()
        mock_get.side_effect = RuntimeError("unexpected error")

        response = client.post(
            "/config/board/test",
            json={"api_mode": "local", "local_api_key": "key", "host": "192.168.1.10"},
            # TestClient re-raises by default; we want the handled response.
        )
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# POST /config/board/enable-local-api
# ---------------------------------------------------------------------------


class TestEnableLocalApiPreconditions:
    def test_missing_host_is_400(self, client):
        response = client.post("/config/board/enable-local-api", json={"host": "", "enablement_token": "test_token"})
        assert response.status_code == 400

    def test_missing_token_is_400(self, client):
        response = client.post("/config/board/enable-local-api", json={"host": "192.168.1.100", "enablement_token": ""})
        assert response.status_code == 400

    def test_public_ip_is_400_and_issues_no_request(self, client):
        """SSRF guard (#1887): the 400 must reach the client as a 400."""
        with patch("src.api_server.requests.post") as mock_post:
            response = client.post(
                "/config/board/enable-local-api",
                json={"host": "8.8.8.8", "enablement_token": "test_token"},
            )
        assert response.status_code == 400
        mock_post.assert_not_called()

    def test_unresolvable_host_is_400(self, client):
        import socket as socket_mod

        with (
            patch("src.api_server._validate_board_host_is_local_network"),
            patch("socket.getaddrinfo", side_effect=socket_mod.gaierror("no such host")),
            patch("src.api_server.requests.post") as mock_post,
        ):
            response = client.post(
                "/config/board/enable-local-api",
                json={"host": "board.invalid", "enablement_token": "test_token"},
            )
        assert response.status_code == 400
        mock_post.assert_not_called()


class TestEnableLocalApiUpstreamVerdictsStay200:
    def test_invalid_enablement_token_stays_200(self, client):
        with patch("src.api_server.requests.post", return_value=Mock(status_code=401)):
            response = client.post(
                "/config/board/enable-local-api",
                json={"host": "192.168.1.100", "enablement_token": "bad"},
            )
        assert response.status_code == 200
        assert response.json()["success"] is False

    def test_declares_a_response_model(self):
        assert _route_metadata("/config/board/enable-local-api")["response_model"] is not None


class TestEnableLocalApiUnexpectedErrors:
    def test_unexpected_exception_is_500(self, client):
        with patch("src.api_server.requests.post", side_effect=RuntimeError("unexpected")):
            response = client.post(
                "/config/board/enable-local-api",
                json={"host": "192.168.1.100", "enablement_token": "test_token"},
            )
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# POST /traffic/routes/validate
# ---------------------------------------------------------------------------


class TestValidateTrafficRoute:
    @staticmethod
    def _config_manager():
        cm = Mock()
        cm.get_plugin_config.return_value = {"api_key": "test_key"}
        return cm

    def test_upstream_returning_no_data_is_502(self, client):
        source = Mock()
        source.fetch_traffic_data.return_value = None
        with (
            patch("src.api_server.get_config_manager", return_value=self._config_manager()),
            patch("src.utils.traffic.TrafficSource", return_value=source),
        ):
            response = client.post(
                "/traffic/routes/validate",
                json={"origin": "40.7128,-74.0060", "destination": "40.7580,-73.9855"},
            )
        assert response.status_code == 502

    def test_unexpected_exception_is_500(self, client):
        with (
            patch("src.api_server.get_config_manager", return_value=self._config_manager()),
            patch("src.utils.traffic.TrafficSource", side_effect=RuntimeError("boom")),
        ):
            response = client.post(
                "/traffic/routes/validate",
                json={"origin": "40.7128,-74.0060", "destination": "40.7580,-73.9855"},
            )
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# POST /debug/test-connection
# ---------------------------------------------------------------------------


class TestDebugTestConnectionStatuses:
    def test_unreachable_board_is_503(self, client):
        board = Mock()
        board.test_connection.return_value = False
        with patch("src.api_server._get_board_client", return_value=board):
            response = client.post("/debug/test-connection")
        assert response.status_code == 503

    def test_unexpected_exception_is_500(self, client):
        board = Mock()
        board.test_connection.side_effect = RuntimeError("timeout")
        with patch("src.api_server._get_board_client", return_value=board):
            response = client.post("/debug/test-connection")
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# GET /mqtt/status
# ---------------------------------------------------------------------------


class TestMqttStatusMasking:
    def test_error_is_not_reported_as_mqtt_being_off(self, client):
        """`{"enabled": false}` must mean "MQTT is off", never "we crashed"."""
        with patch("src.mqtt.get_mqtt_client", side_effect=RuntimeError("boom")):
            response = client.get("/mqtt/status")
        assert response.status_code == 500

    def test_no_client_still_reports_disabled_at_200(self, client):
        with patch("src.mqtt.get_mqtt_client", return_value=None):
            response = client.get("/mqtt/status")
        assert response.status_code == 200
        assert response.json() == {"enabled": False, "connected": False, "running": False}
