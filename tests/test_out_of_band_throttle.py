"""Out-of-band sends must not be silently swallowed by the send floor (#1868 review).

The RW Cloud min-send-interval floor (#1754) makes ``render`` /
``send_characters`` return ``(True, False)`` with ``last_send_throttled``
set when a send lands inside the window. The engine's tick handles that
(it leaves its dedupe cache clear and retries next tick) — but the manual
out-of-band endpoints (/send-message, /send-welcome-message, /debug/blank,
/debug/fill, /debug/info) have NO retry: answering "success/unchanged"
means the user's write was dropped with no signal. They must answer
HTTP 429 with a Retry-After hint instead.
"""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.board_client import BoardClient


@pytest.fixture
def client():
    return TestClient(app)


def _ok_response() -> Mock:
    resp = Mock()
    resp.raise_for_status = Mock()
    return resp


def _cloud_client(now: dict) -> BoardClient:
    """A REAL RW Cloud board client on a controllable clock."""
    return BoardClient(api_key="test_key", use_cloud=True, _time_func=lambda: now["t"])


def _settings_service():
    ss = Mock()
    ss.should_send_to_board.return_value = True
    ss.is_paused.return_value = False
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


@pytest.fixture
def now():
    return {"t": 1000.0}


@pytest.fixture
def cloud(now):
    return _cloud_client(now)


@pytest.fixture
def service(cloud):
    with patch("src.api_server.get_service") as mock_get:
        svc = Mock()
        svc.vb_client = cloud
        svc.board_clients = {"b1": cloud}
        svc.running = True
        mock_get.return_value = svc
        yield svc


@pytest.fixture
def wired(service, cloud):
    with (
        patch("src.api_server.get_settings_service", return_value=_settings_service()),
        patch("src.api_server._get_board_client", return_value=cloud),
        patch("src.api_server.Config.is_silence_mode_active", return_value=False),
        patch("src.api_server._board_is_paused", return_value=False),
        patch("src.board_client.requests.post") as post,
    ):
        post.return_value = _ok_response()
        yield post


class TestSendMessageThrottled429:
    def test_second_message_inside_the_cloud_window_returns_429(self, client, wired, now):
        """Two /send-message posts inside 15s: the second was DROPPED, not 'unchanged'."""
        first = client.post("/send-message", json={"text": "HELLO"})
        assert first.status_code == 200
        assert first.json()["status"] == "success"

        now["t"] += 5.0  # well inside the 15s cloud window
        second = client.post("/send-message", json={"text": "WORLD"})

        assert second.status_code == 429, (
            f"a dropped send must not read as success: {second.status_code} {second.json()}"
        )
        assert int(second.headers["Retry-After"]) >= 1
        assert wired.call_count == 1  # the second POST never reached the board

    def test_message_after_the_window_still_succeeds(self, client, wired, now):
        client.post("/send-message", json={"text": "HELLO"})
        now["t"] += 16.0
        second = client.post("/send-message", json={"text": "WORLD"})
        assert second.status_code == 200
        assert wired.call_count == 2


class TestDebugWritesThrottled429:
    def test_debug_blank_inside_the_window_returns_429(self, client, wired, now):
        assert client.post("/debug/blank").status_code == 200
        now["t"] += 5.0
        second = client.post("/debug/blank")
        assert second.status_code == 429
        assert int(second.headers["Retry-After"]) >= 1

    def test_debug_fill_inside_the_window_returns_429(self, client, wired, now):
        assert client.post("/debug/fill", json={"character_code": 63}).status_code == 200
        now["t"] += 5.0
        second = client.post("/debug/fill", json={"character_code": 64})
        assert second.status_code == 429
        assert int(second.headers["Retry-After"]) >= 1

    def test_debug_info_inside_the_window_returns_429(self, client, wired, now):
        assert client.post("/debug/blank").status_code == 200
        now["t"] += 5.0
        second = client.post("/debug/info")
        assert second.status_code == 429


class TestUnchangedIsStillNotAnError:
    def test_unchanged_content_outside_the_window_still_reads_as_skipped(self, client, wired, now):
        """The 429 is for THROTTLED sends only; a true unchanged skip stays 200."""
        assert client.post("/send-message", json={"text": "HELLO"}).status_code == 200
        now["t"] += 16.0  # window over; same content -> unchanged-cache skip
        second = client.post("/send-message", json={"text": "HELLO"})
        assert second.status_code == 200
        assert second.json().get("skipped") is True
        assert wired.call_count == 1
