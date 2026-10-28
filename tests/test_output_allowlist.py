"""FIESTABOARD_OUTPUTS_ALLOW_HOSTS: the runtime fence on board traffic.

When the variable is set, the app refuses to talk to any board host outside
the list — the dev stack sets it to the bundled mocks, so a developer's
``settings.json`` that still points at a real Vestaboard cannot reach it.
Unset (production) it allows everything, exactly as before.
"""

from unittest.mock import Mock, patch

import pytest

from src.output_allowlist import ENV_VAR, OutputHostBlocked, check_output_host, check_output_url
from tests.first_party_drivers import cloud_driver, local_driver

GRID_6x22 = [[0] * 22 for _ in range(6)]


class TestGuard:
    def test_unset_allows_every_host(self, monkeypatch):
        monkeypatch.delenv(ENV_VAR, raising=False)
        check_output_url("https://rw.vestaboard.com/")
        check_output_host("192.168.1.20")

    def test_empty_value_allows_every_host(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "  ")
        check_output_url("https://rw.vestaboard.com/")

    def test_listed_host_is_allowed(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "fiestaboard-mock-board, 127.0.0.1")
        check_output_url("http://fiestaboard-mock-board:7000/local-api/message")
        check_output_host("127.0.0.1")

    def test_unlisted_host_is_refused(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "fiestaboard-mock-board")
        with pytest.raises(OutputHostBlocked, match=r"rw\.vestaboard\.com"):
            check_output_url("https://rw.vestaboard.com/")

    def test_match_ignores_case(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "Fiestaboard-Mock-Board")
        check_output_host("fiestaboard-mock-board")

    def test_refusal_is_a_connection_error(self):
        # Every existing board error path handles ConnectionError as "board
        # unreachable", so a refused host degrades the same way, no crash.
        import requests

        assert issubclass(OutputHostBlocked, requests.exceptions.ConnectionError)


class TestRefusalLog:
    """A discovery sweep is refused once per host (a /24 is 254 of them):
    the log says so once, then counts, instead of one warning per host."""

    def _refuse(self, hosts):
        for host in hosts:
            with pytest.raises(OutputHostBlocked):
                check_output_host(host)

    def test_a_burst_of_refusals_warns_once_then_summarises(self, monkeypatch, caplog):
        from src.output_allowlist import flush_refusal_summary

        monkeypatch.setenv(ENV_VAR, "fiestaboard-mock-board")
        flush_refusal_summary()
        caplog.clear()
        with caplog.at_level("WARNING", logger="src.output_allowlist"):
            self._refuse(f"192.168.0.{n}" for n in range(1, 101))
            flush_refusal_summary()
        warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 2, warnings
        assert "192.168.0.1" in warnings[0]
        assert "99 more" in warnings[1]

    def test_nothing_suppressed_flushes_nothing(self, monkeypatch, caplog):
        from src.output_allowlist import flush_refusal_summary

        monkeypatch.setenv(ENV_VAR, "fiestaboard-mock-board")
        flush_refusal_summary()
        caplog.clear()
        with caplog.at_level("WARNING", logger="src.output_allowlist"):
            self._refuse(["192.168.0.1"])
            flush_refusal_summary()
        assert len([r for r in caplog.records if r.levelname == "WARNING"]) == 1

    def test_a_refusal_after_the_window_warns_again(self, monkeypatch, caplog):
        from src import output_allowlist

        monkeypatch.setenv(ENV_VAR, "fiestaboard-mock-board")
        output_allowlist.flush_refusal_summary()
        clock = iter([0.0, 1.0, 100.0])
        monkeypatch.setattr(output_allowlist.time, "monotonic", lambda: next(clock))
        caplog.clear()
        with caplog.at_level("WARNING", logger="src.output_allowlist"):
            self._refuse(["192.168.0.1", "192.168.0.2", "192.168.0.3"])
        warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 3, warnings  # first, "1 more" summary, the new one
        assert "1 more" in warnings[1] and "192.168.0.3" in warnings[2]


class TestVestaboardDriver:
    @patch("requests.post")
    def test_local_send_to_unlisted_host_never_leaves(self, mock_post, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "fiestaboard-mock-board")
        client = local_driver("k", "192.168.1.20")

        outcome = client.send_characters(GRID_6x22, with_outcome=True)

        mock_post.assert_not_called()
        assert (outcome.success, outcome.was_sent) == (False, False)

    @patch("requests.post")
    def test_cloud_send_refused_when_cloud_not_listed(self, mock_post, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "fiestaboard-mock-board")
        client = cloud_driver("rw-key")

        success, was_sent = client.send_characters(GRID_6x22)

        mock_post.assert_not_called()
        assert (success, was_sent) == (False, False)

    @patch("requests.post")
    def test_listed_host_still_sends(self, mock_post, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "fiestaboard-mock-board")
        mock_post.return_value = Mock(status_code=200)
        client = local_driver("k", "fiestaboard-mock-board")

        success, was_sent = client.send_characters(GRID_6x22)

        assert mock_post.call_count == 1
        assert (success, was_sent) == (True, True)

    @patch("requests.get")
    def test_read_from_unlisted_host_never_leaves(self, mock_get, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "fiestaboard-mock-board")
        client = local_driver("k", "192.168.1.20")

        assert client.read_current_message() is None
        mock_get.assert_not_called()


class TestConfigProbes:
    def test_connection_test_names_the_allowlist(self, client, monkeypatch):
        import requests

        monkeypatch.setenv(ENV_VAR, "fiestaboard-mock-board")
        with patch.object(requests, "get") as mock_get:
            response = client.post(
                "/config/board/test",
                json={"api_mode": "local", "host": "192.168.1.20", "local_api_key": "k"},
            )

        mock_get.assert_not_called()
        body = response.json()
        assert response.status_code == 200
        assert body["success"] is False
        assert ENV_VAR in body["message"]

    def test_enable_local_api_refused_before_contacting_the_board(self, client, monkeypatch):
        import requests

        monkeypatch.setenv(ENV_VAR, "fiestaboard-mock-board")
        with patch.object(requests, "post") as mock_post:
            response = client.post(
                "/config/board/enable-local-api",
                json={"host": "192.168.1.20", "enablement_token": "t"},
            )

        mock_post.assert_not_called()
        body = response.json()
        assert response.status_code == 200
        assert body["success"] is False
        assert ENV_VAR in body["message"]


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from src.api_server import app

    return TestClient(app)
