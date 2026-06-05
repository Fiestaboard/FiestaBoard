"""Tests for POST /config/board/test endpoint HTTP error handling.

These tests verify that the board connection test endpoint returns
specific, actionable error messages with troubleshooting steps for
every failure mode instead of a generic error.
"""

import json
import re
from unittest.mock import Mock, patch
from urllib.parse import urlparse

import pytest
import requests
from fastapi.testclient import TestClient

from src.api_server import app

_URL_RE = re.compile(r"https?://[^\s'\"<>]+")


def _mentions_host(text, expected_host):
    """Check whether `text` contains a URL whose host equals `expected_host`.

    Used in place of `"host" in text` substring checks, which CodeQL
    flags because they can be tricked by URLs like
    `https://evil.com/?x=rw.vestaboard.com`.
    """
    expected = expected_host.lower()
    for match in _URL_RE.finditer(text):
        host = (urlparse(match.group(0)).hostname or "").lower()
        if host == expected or host.endswith("." + expected):
            return True
    return False


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# Successful connection
# ---------------------------------------------------------------------------


class TestBoardTestSuccess:
    """Test successful board connection responses."""

    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_local_success_with_message_dict(self, mock_client_cls, mock_get, client):
        """Local API returns 200 with {message: [[...]]}."""
        mock_client = Mock()
        mock_client.base_url = "http://192.168.1.10:7000/local-api/message"
        mock_client.headers = {"X-Vestaboard-Local-Api-Key": "key"}
        mock_client_cls.return_value = mock_client

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": [[0] * 22] * 6}
        mock_get.return_value = mock_resp

        response = client.post(
            "/config/board/test",
            json={
                "api_mode": "local",
                "local_api_key": "key",
                "host": "192.168.1.10",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "successfully" in data["message"].lower()

    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_local_success_with_list_response(self, mock_client_cls, mock_get, client):
        """Local API returns 200 with a list (older firmware format)."""
        mock_client = Mock()
        mock_client.base_url = "http://192.168.1.10:7000/local-api/message"
        mock_client.headers = {}
        mock_client_cls.return_value = mock_client

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [[0] * 22] * 6
        mock_get.return_value = mock_resp

        response = client.post(
            "/config/board/test",
            json={
                "api_mode": "local",
                "local_api_key": "key",
                "host": "192.168.1.10",
            },
        )

        data = response.json()
        assert data["success"] is True

    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_cloud_success(self, mock_client_cls, mock_get, client):
        """Cloud API returns 200 with valid data."""
        mock_client = Mock()
        mock_client.base_url = "https://rw.vestaboard.com/"
        mock_client.headers = {"X-Vestaboard-Read-Write-Key": "rw-key"}
        mock_client_cls.return_value = mock_client

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": [[0] * 22] * 6}
        mock_get.return_value = mock_resp

        response = client.post(
            "/config/board/test",
            json={
                "api_mode": "cloud",
                "cloud_key": "rw-key",
            },
        )

        data = response.json()
        assert data["success"] is True


# ---------------------------------------------------------------------------
# Authentication failures (401 / 403)
# ---------------------------------------------------------------------------


class TestBoardTestAuthFailure:
    """Test auth rejection error messages with troubleshooting steps."""

    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_local_401_returns_troubleshooting(self, mock_client_cls, mock_get, client):
        mock_client = Mock()
        mock_client.base_url = "http://192.168.1.10:7000/local-api/message"
        mock_client.headers = {}
        mock_client_cls.return_value = mock_client

        mock_resp = Mock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp

        response = client.post(
            "/config/board/test",
            json={
                "api_mode": "local",
                "local_api_key": "bad-key",
                "host": "192.168.1.10",
            },
        )

        data = response.json()
        assert data["success"] is False
        assert "rejected" in data["message"].lower()
        assert "troubleshooting" in data
        assert any("Local API" in s for s in data["troubleshooting"])

    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_local_403_returns_troubleshooting(self, mock_client_cls, mock_get, client):
        mock_client = Mock()
        mock_client.base_url = "http://192.168.1.10:7000/local-api/message"
        mock_client.headers = {}
        mock_client_cls.return_value = mock_client

        mock_resp = Mock()
        mock_resp.status_code = 403
        mock_get.return_value = mock_resp

        response = client.post(
            "/config/board/test",
            json={
                "api_mode": "local",
                "local_api_key": "bad-key",
                "host": "192.168.1.10",
            },
        )

        data = response.json()
        assert data["success"] is False
        assert "rejected" in data["message"].lower()

    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_cloud_401_returns_cloud_troubleshooting(self, mock_client_cls, mock_get, client):
        mock_client = Mock()
        mock_client.base_url = "https://rw.vestaboard.com/"
        mock_client.headers = {}
        mock_client_cls.return_value = mock_client

        mock_resp = Mock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp

        response = client.post(
            "/config/board/test",
            json={
                "api_mode": "cloud",
                "cloud_key": "bad-rw-key",
            },
        )

        data = response.json()
        assert data["success"] is False
        assert "rejected" in data["message"].lower()
        assert any(_mentions_host(s, "web.vestaboard.com") for s in data["troubleshooting"])


# ---------------------------------------------------------------------------
# Server errors (500+)
# ---------------------------------------------------------------------------


class TestBoardTestServerError:
    """Test server error messages with troubleshooting steps."""

    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_500_returns_troubleshooting(self, mock_client_cls, mock_get, client):
        mock_client = Mock()
        mock_client.base_url = "http://192.168.1.10:7000/local-api/message"
        mock_client.headers = {}
        mock_client_cls.return_value = mock_client

        mock_resp = Mock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp

        response = client.post(
            "/config/board/test",
            json={
                "api_mode": "local",
                "local_api_key": "key",
                "host": "192.168.1.10",
            },
        )

        data = response.json()
        assert data["success"] is False
        assert "error" in data["message"].lower()
        assert "troubleshooting" in data
        assert any("unplug" in s.lower() for s in data["troubleshooting"])

    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_502_returns_troubleshooting(self, mock_client_cls, mock_get, client):
        mock_client = Mock()
        mock_client.base_url = "http://192.168.1.10:7000/local-api/message"
        mock_client.headers = {}
        mock_client_cls.return_value = mock_client

        mock_resp = Mock()
        mock_resp.status_code = 502
        mock_get.return_value = mock_resp

        response = client.post(
            "/config/board/test",
            json={
                "api_mode": "local",
                "local_api_key": "key",
                "host": "192.168.1.10",
            },
        )

        data = response.json()
        assert data["success"] is False
        assert "troubleshooting" in data


# ---------------------------------------------------------------------------
# Connection errors
# ---------------------------------------------------------------------------


class TestBoardTestConnectionError:
    """Test connection error messages with troubleshooting steps."""

    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_local_connection_refused(self, mock_client_cls, mock_get, client):
        mock_client = Mock()
        mock_client.base_url = "http://192.168.1.10:7000/local-api/message"
        mock_client.headers = {}
        mock_client_cls.return_value = mock_client

        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        response = client.post(
            "/config/board/test",
            json={
                "api_mode": "local",
                "local_api_key": "key",
                "host": "192.168.1.10",
            },
        )

        data = response.json()
        assert data["success"] is False
        assert "connect" in data["message"].lower()
        assert "troubleshooting" in data
        assert any("same wi-fi" in s.lower() for s in data["troubleshooting"])

    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_cloud_connection_error(self, mock_client_cls, mock_get, client):
        mock_client = Mock()
        mock_client.base_url = "https://rw.vestaboard.com/"
        mock_client.headers = {}
        mock_client_cls.return_value = mock_client

        mock_get.side_effect = requests.exceptions.ConnectionError("no route")

        response = client.post(
            "/config/board/test",
            json={
                "api_mode": "cloud",
                "cloud_key": "rw-key",
            },
        )

        data = response.json()
        assert data["success"] is False
        assert "cloud" in data["message"].lower()
        assert any(_mentions_host(s, "rw.vestaboard.com") for s in data["troubleshooting"])


# ---------------------------------------------------------------------------
# Timeout errors
# ---------------------------------------------------------------------------


class TestBoardTestTimeout:
    """Test timeout error messages with troubleshooting steps."""

    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_local_timeout(self, mock_client_cls, mock_get, client):
        mock_client = Mock()
        mock_client.base_url = "http://192.168.1.10:7000/local-api/message"
        mock_client.headers = {}
        mock_client_cls.return_value = mock_client

        mock_get.side_effect = requests.exceptions.Timeout("timed out")

        response = client.post(
            "/config/board/test",
            json={
                "api_mode": "local",
                "local_api_key": "key",
                "host": "192.168.1.10",
            },
        )

        data = response.json()
        assert data["success"] is False
        assert "timed out" in data["message"].lower()
        assert "troubleshooting" in data
        assert any("ip" in s.lower() or "address" in s.lower() for s in data["troubleshooting"])

    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_cloud_timeout(self, mock_client_cls, mock_get, client):
        mock_client = Mock()
        mock_client.base_url = "https://rw.vestaboard.com/"
        mock_client.headers = {}
        mock_client_cls.return_value = mock_client

        mock_get.side_effect = requests.exceptions.Timeout("timed out")

        response = client.post(
            "/config/board/test",
            json={
                "api_mode": "cloud",
                "cloud_key": "rw-key",
            },
        )

        data = response.json()
        assert data["success"] is False
        assert "timed out" in data["message"].lower()
        assert "troubleshooting" in data


# ---------------------------------------------------------------------------
# Unexpected response formats
# ---------------------------------------------------------------------------


class TestBoardTestUnexpectedResponse:
    """Test unexpected response format messages."""

    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_200_unexpected_json_format(self, mock_client_cls, mock_get, client):
        """200 but no 'message' key and not a list → unexpected format."""
        mock_client = Mock()
        mock_client.base_url = "http://192.168.1.10:7000/local-api/message"
        mock_client.headers = {}
        mock_client_cls.return_value = mock_client

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ok"}  # No "message" key, not a list
        mock_get.return_value = mock_resp

        response = client.post(
            "/config/board/test",
            json={
                "api_mode": "local",
                "local_api_key": "key",
                "host": "192.168.1.10",
            },
        )

        data = response.json()
        assert data["success"] is False
        assert "recognized" in data["message"].lower()
        assert "status" in data.get("error", "").lower() or "keys" in data.get("error", "").lower()
        assert "troubleshooting" in data

    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_cloud_200_current_message_note_layout(self, mock_client_cls, mock_get, client):
        """Cloud GET returns Vestaboard currentMessage.layout string (Note 3x15)."""
        note_grid = [[0] * 15 for _ in range(3)]
        mock_client = Mock()
        mock_client.base_url = "https://rw.vestaboard.com/"
        mock_client.headers = {}
        mock_client_cls.return_value = mock_client

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "currentMessage": {
                "layout": json.dumps(note_grid),
                "id": "test-uuid",
                "appeared": 1,
            }
        }
        mock_get.return_value = mock_resp

        response = client.post(
            "/config/board/test",
            json={"api_mode": "cloud", "cloud_key": "rw-key"},
        )
        data = response.json()
        assert data["success"] is True
        assert data["api_mode"] == "cloud"

    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_cloud_200_current_message_null(self, mock_client_cls, mock_get, client):
        """Cloud GET with empty board (currentMessage null) still counts as connected."""
        mock_client = Mock()
        mock_client.base_url = "https://rw.vestaboard.com/"
        mock_client.headers = {}
        mock_client_cls.return_value = mock_client

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"currentMessage": None}
        mock_get.return_value = mock_resp

        response = client.post(
            "/config/board/test",
            json={"api_mode": "cloud", "cloud_key": "rw-key"},
        )
        assert response.json()["success"] is True

    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_200_invalid_json(self, mock_client_cls, mock_get, client):
        """200 but body is not valid JSON."""
        mock_client = Mock()
        mock_client.base_url = "http://192.168.1.10:7000/local-api/message"
        mock_client.headers = {}
        mock_client_cls.return_value = mock_client

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_resp

        response = client.post(
            "/config/board/test",
            json={
                "api_mode": "local",
                "local_api_key": "key",
                "host": "192.168.1.10",
            },
        )

        data = response.json()
        assert data["success"] is False
        assert "troubleshooting" in data

    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_unexpected_http_status(self, mock_client_cls, mock_get, client):
        """Non-200, non-401/403, non-500+ status code."""
        mock_client = Mock()
        mock_client.base_url = "http://192.168.1.10:7000/local-api/message"
        mock_client.headers = {}
        mock_client_cls.return_value = mock_client

        mock_resp = Mock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        response = client.post(
            "/config/board/test",
            json={
                "api_mode": "local",
                "local_api_key": "key",
                "host": "192.168.1.10",
            },
        )

        data = response.json()
        assert data["success"] is False
        assert "troubleshooting" in data

    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_200_empty_list(self, mock_client_cls, mock_get, client):
        """200 with empty list — no message data."""
        mock_client = Mock()
        mock_client.base_url = "http://192.168.1.10:7000/local-api/message"
        mock_client.headers = {}
        mock_client_cls.return_value = mock_client

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []  # Empty list
        mock_get.return_value = mock_resp

        response = client.post(
            "/config/board/test",
            json={
                "api_mode": "local",
                "local_api_key": "key",
                "host": "192.168.1.10",
            },
        )

        data = response.json()
        # Empty list → characters is None → unexpected format
        assert data["success"] is False


# ---------------------------------------------------------------------------
# General exception handling
# ---------------------------------------------------------------------------


class TestBoardTestGeneralError:
    """Test the catch-all exception handler."""

    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_unexpected_exception(self, mock_client_cls, mock_get, client):
        mock_client = Mock()
        mock_client.base_url = "http://192.168.1.10:7000/local-api/message"
        mock_client.headers = {}
        mock_client_cls.return_value = mock_client

        mock_get.side_effect = RuntimeError("unexpected error")

        response = client.post(
            "/config/board/test",
            json={
                "api_mode": "local",
                "local_api_key": "key",
                "host": "192.168.1.10",
            },
        )

        data = response.json()
        assert data["success"] is False
        assert "troubleshooting" in data


# ---------------------------------------------------------------------------
# Troubleshooting field structure
# ---------------------------------------------------------------------------


class TestBoardTestTroubleshootingStructure:
    """Verify troubleshooting field is always a list of strings."""

    @patch("src.api_server.requests.get")
    @patch("src.board_client.BoardClient")
    def test_troubleshooting_is_list_of_strings(self, mock_client_cls, mock_get, client):
        """Every error response should have troubleshooting as a list of strings."""
        mock_client = Mock()
        mock_client.base_url = "http://192.168.1.10:7000/local-api/message"
        mock_client.headers = {}
        mock_client_cls.return_value = mock_client

        # Trigger each error path and check structure
        for exc in [
            requests.exceptions.ConnectionError("refused"),
            requests.exceptions.Timeout("timed out"),
        ]:
            mock_get.side_effect = exc
            response = client.post(
                "/config/board/test",
                json={
                    "api_mode": "local",
                    "local_api_key": "key",
                    "host": "192.168.1.10",
                },
            )
            data = response.json()
            assert isinstance(data.get("troubleshooting"), list), (
                f"troubleshooting should be a list for {type(exc).__name__}"
            )
            for step in data["troubleshooting"]:
                assert isinstance(step, str), f"Each troubleshooting step should be a string for {type(exc).__name__}"
