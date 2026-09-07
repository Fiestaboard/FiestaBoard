"""Board client send policy: connection retries, backoff, and per-type send floor (#1754).

Covers three behaviors added in issue #1754:

1. **Connection-level retry with backoff** — a send that fails because the
   board never answered (``requests.ConnectionError`` / timeouts) is retried
   exactly once after a short backoff. HTTP error *responses* (4xx/5xx) are
   the board answering and are never retried. The backoff waits on the
   client's cancel event so a preempting render abandons the retry promptly.
2. **Universal min-send-interval floor** — per client instance: RW Cloud
   sends are floored at one send per 15s (Vestaboard's documented limit,
   docs/setup/cloud-api.md); note arrays keep their existing 15s floor;
   the Local API stays unfloored. Throttled sends return ``(True, False)``
   and set ``last_send_throttled`` — the same contract the engine already
   relies on for note arrays (issue #1794).
3. **Connect/read timeout split** — LAN posts use ``(3, 10)`` so an
   unreachable board fails fast; cloud posts use ``(5, 10)``. Read timeouts
   are unchanged.
"""

import threading
from unittest.mock import Mock, patch

import pytest
import requests

from src.board_client import (
    CLOUD_MIN_SEND_INTERVAL,
    CLOUD_REQUEST_TIMEOUT,
    LOCAL_REQUEST_TIMEOUT,
    SEND_MAX_ATTEMPTS,
    SEND_RETRY_BACKOFF_SECONDS,
    BoardClient,
    _note_array_last_send,
)


@pytest.fixture(autouse=True)
def _reset_note_array_throttle():
    """Clear module-level note-array throttle state around each test."""
    _note_array_last_send.clear()
    yield
    _note_array_last_send.clear()


def _clock(*values):
    """Callable yielding the given values in order, then repeating the last."""
    seq = list(values)

    def _next():
        return seq.pop(0) if len(seq) > 1 else seq[0]

    return _next


def _flagship_grid(fill: int = 0) -> list[list[int]]:
    return [[fill] * 22 for _ in range(6)]


def _ok_response() -> Mock:
    resp = Mock()
    resp.raise_for_status = Mock()
    return resp


def _no_cancel(client: BoardClient) -> Mock:
    """Replace the client's cancel event with one that never fires.

    Returns the mock so tests can observe backoff waits without sleeping.
    """
    fake_event = Mock(spec=threading.Event)
    fake_event.wait.return_value = False
    client._cancel_transition = fake_event
    return fake_event


class TestConnectionRetry:
    """Connection-level errors retry exactly once after a short backoff."""

    @pytest.fixture
    def client(self):
        return BoardClient(api_key="test-key", host="192.168.0.11")

    @patch("src.board_client.requests.post")
    def test_connection_error_then_success_retries_once(self, mock_post, client):
        cancel = _no_cancel(client)
        mock_post.side_effect = [requests.exceptions.ConnectionError("unreachable"), _ok_response()]

        result = client.send_characters(_flagship_grid(1))

        assert result == (True, True)
        assert mock_post.call_count == 2
        cancel.wait.assert_called_once_with(SEND_RETRY_BACKOFF_SECONDS)

    @patch("src.board_client.requests.post")
    def test_connection_error_on_both_attempts_gives_up(self, mock_post, client):
        cancel = _no_cancel(client)
        mock_post.side_effect = requests.exceptions.ConnectionError("unreachable")

        result = client.send_characters(_flagship_grid(1))

        assert result == (False, False)
        assert mock_post.call_count == SEND_MAX_ATTEMPTS == 2
        cancel.wait.assert_called_once_with(SEND_RETRY_BACKOFF_SECONDS)

    @patch("src.board_client.requests.post")
    def test_read_timeout_is_retried(self, mock_post, client):
        _no_cancel(client)
        mock_post.side_effect = [requests.exceptions.ReadTimeout("slow"), _ok_response()]

        result = client.send_characters(_flagship_grid(1))

        assert result == (True, True)
        assert mock_post.call_count == 2

    @patch("src.board_client.requests.post")
    def test_http_error_response_is_not_retried(self, mock_post, client):
        cancel = _no_cancel(client)
        resp = Mock()
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
        mock_post.return_value = resp

        result = client.send_characters(_flagship_grid(1))

        assert result == (False, False)
        assert mock_post.call_count == 1
        cancel.wait.assert_not_called()

    @patch("src.board_client.requests.post")
    def test_success_first_try_is_single_attempt(self, mock_post, client):
        cancel = _no_cancel(client)
        mock_post.return_value = _ok_response()

        result = client.send_characters(_flagship_grid(1))

        assert result == (True, True)
        assert mock_post.call_count == 1
        cancel.wait.assert_not_called()

    @patch("src.board_client.requests.post")
    def test_cancel_during_backoff_abandons_retry(self, mock_post, client):
        cancel = Mock(spec=threading.Event)
        cancel.wait.return_value = True  # cancel fires during the backoff
        client._cancel_transition = cancel
        mock_post.side_effect = requests.exceptions.ConnectionError("unreachable")

        result = client.send_characters(_flagship_grid(1))

        assert result == (False, False)
        assert mock_post.call_count == 1  # no second attempt after cancel
        cancel.wait.assert_called_once_with(SEND_RETRY_BACKOFF_SECONDS)

    @patch("src.board_client.requests.post")
    def test_send_text_retries_connection_error(self, mock_post, client):
        _no_cancel(client)
        mock_post.side_effect = [requests.exceptions.ConnectionError("unreachable"), _ok_response()]

        result = client.send_text("hello")

        assert result == (True, True)
        assert mock_post.call_count == 2


class TestTimeoutSplit:
    """LAN connects fail fast at 3s; cloud gets 5s; reads stay at 10s."""

    @patch("src.board_client.requests.post")
    def test_local_send_uses_short_connect_timeout(self, mock_post):
        mock_post.return_value = _ok_response()
        client = BoardClient(api_key="k", host="192.168.0.11")

        client.send_characters(_flagship_grid(1))

        assert mock_post.call_args.kwargs["timeout"] == LOCAL_REQUEST_TIMEOUT == (3.0, 10.0)

    @patch("src.board_client.requests.post")
    def test_cloud_send_uses_cloud_connect_timeout(self, mock_post):
        mock_post.return_value = _ok_response()
        client = BoardClient(api_key="rw-key", use_cloud=True)

        client.send_characters(_flagship_grid(1))

        assert mock_post.call_args.kwargs["timeout"] == CLOUD_REQUEST_TIMEOUT == (5.0, 10.0)

    @patch("src.board_client.requests.get")
    def test_local_read_uses_split_timeout(self, mock_get):
        resp = Mock()
        resp.raise_for_status = Mock()
        resp.json.return_value = {"message": _flagship_grid(0)}
        mock_get.return_value = resp
        client = BoardClient(api_key="k", host="192.168.0.11")

        client.read_current_message()

        assert mock_get.call_args.kwargs["timeout"] == LOCAL_REQUEST_TIMEOUT


class TestCloudSendFloor:
    """RW Cloud sends are floored at one send per CLOUD_MIN_SEND_INTERVAL."""

    def _cloud_client(self, time_func) -> BoardClient:
        return BoardClient(api_key="rw-key", use_cloud=True, _time_func=time_func)

    @patch("src.board_client.requests.post")
    def test_second_send_within_interval_is_throttled(self, mock_post):
        mock_post.return_value = _ok_response()
        client = self._cloud_client(_clock(0.0, 10.0))

        assert client.send_characters(_flagship_grid(1)) == (True, True)
        result = client.send_characters(_flagship_grid(2))

        assert result == (True, False)
        assert client.last_send_throttled is True
        assert mock_post.call_count == 1

    @patch("src.board_client.requests.post")
    def test_send_after_interval_elapses_goes_through(self, mock_post):
        mock_post.return_value = _ok_response()
        client = self._cloud_client(_clock(0.0, CLOUD_MIN_SEND_INTERVAL))

        assert client.send_characters(_flagship_grid(1)) == (True, True)
        assert client.send_characters(_flagship_grid(2)) == (True, True)
        assert client.last_send_throttled is False
        assert mock_post.call_count == 2

    @patch("src.board_client.requests.post")
    def test_send_text_shares_the_floor_with_send_characters(self, mock_post):
        mock_post.return_value = _ok_response()
        client = self._cloud_client(_clock(0.0, 10.0))

        assert client.send_text("first") == (True, True)
        result = client.send_characters(_flagship_grid(2))

        assert result == (True, False)
        assert client.last_send_throttled is True
        assert mock_post.call_count == 1

    @patch("src.board_client.requests.post")
    def test_unchanged_skip_within_window_is_not_marked_throttled(self, mock_post):
        """Past the floor, identical content still skips as 'unchanged', not 'throttled'."""
        mock_post.return_value = _ok_response()
        client = self._cloud_client(_clock(0.0, 100.0))

        client.send_characters(_flagship_grid(1))
        assert client.send_characters(_flagship_grid(1)) == (True, False)
        assert client.last_send_throttled is False

    @patch("src.board_client.requests.post")
    def test_failed_send_does_not_consume_the_slot(self, mock_post):
        """A send that never reached the board must not start the 15s window."""
        client = self._cloud_client(_clock(0.0, 5.0))
        _no_cancel(client)
        mock_post.side_effect = [
            requests.exceptions.ConnectionError("down"),
            requests.exceptions.ConnectionError("down"),
            _ok_response(),
        ]

        assert client.send_characters(_flagship_grid(1)) == (False, False)
        # 5s later — inside the window, but nothing was ever sent.
        assert client.send_characters(_flagship_grid(2)) == (True, True)
        assert mock_post.call_count == 3

    @patch("src.board_client.requests.post")
    def test_local_sends_have_no_floor(self, mock_post):
        mock_post.return_value = _ok_response()
        client = BoardClient(api_key="k", host="192.168.0.11")

        assert client.send_characters(_flagship_grid(1)) == (True, True)
        assert client.send_characters(_flagship_grid(2)) == (True, True)
        assert mock_post.call_count == 2

    def test_min_send_interval_ms_reports_per_type_floor(self):
        cloud = BoardClient(api_key="rw", use_cloud=True)
        local = BoardClient(api_key="k", host="192.168.0.11")
        note_array = BoardClient(api_key="t", use_cloud=True, note_array_token="t-floor")

        assert cloud.min_send_interval_ms == int(CLOUD_MIN_SEND_INTERVAL * 1000)
        assert local.min_send_interval_ms == 0
        assert note_array.min_send_interval_ms == 15000


class TestThrottleConcurrency:
    """Two threads through one client cannot double-send inside the floor window.

    Deterministic: thread A is held *inside* the mocked POST (past the throttle
    check, before the pre-#1754 timestamp write) while the main thread sends.
    Pre-fix the main thread's throttle check saw no timestamp and double-sent;
    post-fix the slot is reserved under the lock before the POST starts.
    """

    def _run_concurrent_pair(self, client) -> tuple[dict, list]:
        entered = threading.Event()
        release = threading.Event()
        posts: list = []

        def fake_post(url, **kwargs):
            posts.append(kwargs["json"])
            entered.set()
            release.wait(5)
            return _ok_response()

        results: dict = {}
        with patch("src.board_client.requests.post", side_effect=fake_post):
            worker = threading.Thread(target=lambda: results.setdefault("a", client.send_characters(_flagship_grid(1))))
            worker.start()
            assert entered.wait(5), "thread A never reached the POST"
            results["b"] = client.send_characters(_flagship_grid(2))
            release.set()
            worker.join(5)
        assert not worker.is_alive()
        return results, posts

    def test_concurrent_cloud_sends_send_exactly_once(self):
        client = BoardClient(api_key="rw-key", use_cloud=True, _time_func=lambda: 100.0)

        results, posts = self._run_concurrent_pair(client)

        assert results["a"] == (True, True)
        assert results["b"] == (True, False)
        assert client.last_send_throttled is True
        assert len(posts) == 1

    def test_concurrent_note_array_sends_send_exactly_once(self):
        """The pre-#1754 unlocked module-global raced: a second thread checked
        the throttle while the first was mid-POST (timestamp not yet written)
        and both sends went out inside the 15s window."""
        client = BoardClient(
            api_key="na-tok",
            use_cloud=True,
            note_array_token="na-race-tok",
            _time_func=lambda: 100.0,
        )
        entered = threading.Event()
        release = threading.Event()
        posts: list = []

        def fake_post(url, **kwargs):
            posts.append(kwargs["json"])
            entered.set()
            release.wait(5)
            return _ok_response()

        grid_a = [[0] * 60 for _ in range(3)]
        grid_b = [[1] * 60 for _ in range(3)]
        results: dict = {}
        with patch("src.board_client.requests.post", side_effect=fake_post):
            worker = threading.Thread(target=lambda: results.setdefault("a", client.send_characters(grid_a)))
            worker.start()
            assert entered.wait(5), "thread A never reached the POST"
            results["b"] = client.send_characters(grid_b)
            release.set()
            worker.join(5)
        assert not worker.is_alive()

        assert results["a"] == (True, True)
        assert results["b"] == (True, False)
        assert client.last_send_throttled is True
        assert len(posts) == 1
