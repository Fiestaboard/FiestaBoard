"""The connection probe's verdicts, the Local API enablement exchange, and the
diagnostics advice — what the plugin tells the user."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests

from first_party_outputs.vestaboard import diagnostics, local_api
from first_party_outputs.vestaboard.tests.conftest import CLOUD, LOCAL, response
from src.plugins import OutputActionError

BOARD_GRID = {"message": [[0] * 22 for _ in range(6)]}


# --- the probe ---------------------------------------------------------------------------


class TestProbe:
    @pytest.mark.parametrize(
        ("config", "answer", "failure", "error"),
        [
            (LOCAL, response(401), "auth", "HTTP 401"),
            (CLOUD, response(403), "auth", "HTTP 403"),
            (LOCAL, response(503), "server_error", "HTTP 503"),
            (LOCAL, response(418), "unexpected_status", "HTTP 418"),
            (
                LOCAL,
                response(200, {"unexpected": True}),
                "bad_response",
                "Unrecognized read response (JSON keys: unexpected).",
            ),
            (
                LOCAL,
                response(200, ["not", "a", "grid"]),
                "bad_response",
                "Unrecognized read response (body type: list).",
            ),
            (LOCAL, requests.exceptions.ConnectionError("refused"), "unreachable", "Connection error"),
            (CLOUD, requests.exceptions.ConnectionError("refused"), "unreachable", "Connection error"),
            (LOCAL, requests.exceptions.ReadTimeout("quiet"), "timeout", "Timeout"),
            (CLOUD, requests.exceptions.ReadTimeout("quiet"), "timeout", "Timeout"),
        ],
    )
    def test_each_answer_is_classified_with_guidance(self, make, config, answer, failure, error):
        plugin, device = make(config)
        device.answer = lambda request: answer
        check = plugin.check_connection()
        assert (check.success, check.failure, check.error) == (False, failure, error)
        assert check.troubleshooting

    def test_a_board_read_is_success_with_its_api_mode(self, make):
        plugin, device = make(LOCAL)
        device.answer = lambda request: response(200, BOARD_GRID)
        assert plugin.check_connection().to_verdict() == {
            "success": True,
            "message": "Successfully connected to your board!",
            "api_mode": "local",
        }

    def test_an_unreadable_body_is_a_bad_response(self, make):
        plugin, device = make(LOCAL)
        broken = response(200)
        broken._content = b"not json"
        device.answer = lambda request: broken
        assert plugin.check_connection().error == "Invalid JSON response"

    def test_a_fenced_host_is_blocked_without_a_request(self, make, monkeypatch):
        monkeypatch.setenv("FIESTABOARD_OUTPUTS_ALLOW_HOSTS", "fiestaboard-mock-board")
        plugin, device = make(LOCAL)
        assert plugin.check_connection().failure == "blocked"
        assert device.requests == []

    def test_an_unusable_credential_is_not_a_verdict(self, make):
        plugin, device = make(LOCAL)
        device.answer = lambda request: ValueError("Invalid header value")
        with pytest.raises(ValueError):
            plugin.check_connection()


# --- the Local API enablement exchange -------------------------------------------------------


def _exchange(host: str, token: str = "test_enablement_token") -> dict:
    return asyncio.run(local_api.exchange_enablement_token(SimpleNamespace(host=host, enablement_token=token)))


class TestEnablementExchange:
    @patch("requests.post")
    def test_the_board_issues_the_key(self, post):
        post.return_value = response(200, {"apiKey": "test_issued_key"})
        verdict = _exchange("192.168.1.20")
        assert (verdict["success"], verdict["api_key"]) == (True, "test_issued_key")
        assert post.call_args.args[0] == "http://192.168.1.20:7000/local-api/enablement"
        assert post.call_args.kwargs["headers"] == {"X-Vestaboard-Local-Api-Enablement-Token": "test_enablement_token"}

    @pytest.mark.parametrize(
        ("answer", "error"),
        [
            (response(200, {}), "Board response did not include an apiKey"),
            (response(401), "HTTP 401: Unauthorized"),
            (response(500), "HTTP 500"),
            (requests.exceptions.ConnectionError("refused"), "Connection error"),
            (requests.exceptions.Timeout("slow"), "Timeout"),
        ],
    )
    def test_what_the_board_said_is_the_verdict(self, answer, error):
        kwargs = {"side_effect": answer} if isinstance(answer, Exception) else {"return_value": answer}
        with patch("requests.post", **kwargs):
            verdict = _exchange("192.168.1.20")
        assert (verdict["success"], verdict["error"]) == (False, error)

    @pytest.mark.parametrize(
        ("host", "token", "detail"),
        [
            ("", "t", "Board IP address is required"),
            ("192.168.1.20", "", "Enablement token is required"),
            ("8.8.8.8", "t", "host must resolve to a local/private IPv4 address"),
        ],
    )
    def test_what_is_refused_before_the_board_is_contacted(self, host, token, detail):
        with patch("requests.post") as post, pytest.raises(Exception) as refused:
            _exchange(host, token)
        assert detail in str(getattr(refused.value, "detail", refused.value))
        post.assert_not_called()

    def test_a_fenced_host_is_a_blocked_verdict(self, monkeypatch):
        monkeypatch.setenv("FIESTABOARD_OUTPUTS_ALLOW_HOSTS", "fiestaboard-mock-board")
        with patch("requests.post") as post:
            verdict = _exchange("192.168.1.20")
        assert verdict["success"] is False and "Not contacted" in verdict["message"]
        post.assert_not_called()

    def test_an_unanticipated_failure_is_a_500(self):
        with patch("requests.post", side_effect=RuntimeError("boom")), pytest.raises(OutputActionError) as failed:
            _exchange("192.168.1.20")
        assert failed.value.status_code == 500


# --- the diagnostics section and its advice ------------------------------------------------


class TestDiagnose:
    def test_a_cloud_board_with_a_key_checks_the_cloud(self):
        with patch.object(diagnostics, "check_vestaboard_connection", return_value={"ok": True}) as check:
            diagnostics.diagnose({"api_mode": "cloud", "cloud_key": "test_key"})
        assert check.call_args.kwargs == {"host": "", "use_cloud": True, "cloud_key": "test_key"}

    def test_a_board_with_a_host_checks_the_local_api(self):
        with patch.object(diagnostics, "check_vestaboard_connection", return_value={"ok": True}) as check:
            diagnostics.diagnose({"host": "192.0.2.10", "port": 7001, "local_api_key": "k"})
        assert check.call_args.kwargs == {"host": "192.0.2.10", "port": 7001, "api_key": "k"}

    def test_nothing_configured_is_the_unconfigured_section(self):
        section = diagnostics.diagnose({})
        assert section["ok"] is False


class TestAdvice:
    @pytest.mark.parametrize(
        ("section", "summary"),
        [
            ({"mode": "local", "steps": {"dns": {"ok": False, "hostname": "vb.local"}}}, "cannot find your Vestaboard"),
            ({"mode": "local", "steps": {"port": {"ok": False, "port": 7000}}}, "cannot connect to it"),
            ({"mode": "local", "steps": {"api": {"ok": False, "status_code": 401}}}, "API key was rejected"),
            ({"mode": "local", "steps": {"api": {"ok": False, "status_code": 500}}}, "responded with an error"),
            ({"mode": "local", "steps": {"api": {"ok": False, "status_code": None}}}, "got no response"),
            ({"mode": "cloud", "steps": {"cloud_api": {"status_code": 403}}}, "rejected your API key"),
            ({"mode": "cloud", "steps": {"cloud_api": {"status_code": 503}}}, "temporarily down"),
            ({"mode": "cloud", "steps": {"cloud_api": {"error": "Could not connect"}}}, "cannot reach"),
            ({"mode": "cloud", "steps": {"cloud_api": {}}}, "connection check failed"),
        ],
    )
    def test_each_failure_gets_its_advice(self, section, summary):
        advice = diagnostics.advise({"ok": False, **section})
        assert len(advice) == 1 and summary in advice[0]["summary"] and advice[0]["steps"]

    def test_a_healthy_or_unconfigured_section_gets_none(self):
        assert diagnostics.advise({"ok": True}) == []
        assert diagnostics.advise({"ok": False, "mode": None}) == []
