"""A sidecar that is behind must be named, not inferred (#1977 follow-on).

Nothing on a running box refreshes the sidecar. ``handle_update`` and
``handle_install`` recreate only the fiestaboard service, and the Pi pulls
the sidecar once per boot. So a box that has not rebooted since a sidecar
image shipped keeps running the old one — silently.

That is not hypothetical. #1977 taught the sidecar to pass ``--pull never``
when recreating after a retag, without which ``pull_policy: always`` re-pulls
``:latest`` and undoes the retag. The image published at 20:58 UTC. At 23:39
UTC a live FiestaPi was still clobbering its own retags, because it had not
rebooted. What the user saw was a channel switch that appeared to work, then
a box on stable, then — three recreations later — the beta again. Nothing in
the API or the logs said "your sidecar is old".

``GET /version`` now advertises what the sidecar can do. An older sidecar
omits the field, and that absence is precisely the signal: no version
negotiation, no release-date arithmetic.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import src.system.update_service as update_service
from src.api_server import app


@pytest.fixture
def client():
    return TestClient(app)


def _version_body(body):
    resp = MagicMock(status_code=200)
    resp.json.return_value = body
    return patch("src.system.update_service.requests.get", return_value=resp)


CURRENT = {
    "service": "fiestaboard",
    "image": "fiestaboard/fiestaboard:latest",
    "digest": "sha256:abc",
    "capabilities": ["install", "pull-never"],
}
# What a pre-#1977 sidecar returns: the same fields, minus the new one.
OLD = {"service": "fiestaboard", "image": "fiestaboard/fiestaboard:latest", "digest": "sha256:abc"}


class TestReadingCapabilities:
    def test_a_current_sidecar_reports_what_it_can_do(self):
        with _version_body(CURRENT):
            assert "pull-never" in update_service.updater_capabilities()

    def test_a_sidecar_that_omits_the_field_reports_nothing(self):
        """Absence IS the signal — an old handler.sh has no such key."""
        with _version_body(OLD):
            assert update_service.updater_capabilities() == []

    def test_an_unreachable_sidecar_reports_nothing(self):
        with patch("src.system.update_service.requests.get", side_effect=OSError("down")):
            assert update_service.updater_capabilities() == []

    def test_a_malformed_capabilities_value_is_ignored(self):
        """Never let a bad payload become a crash on the status path."""
        with _version_body({**OLD, "capabilities": "pull-never"}):
            assert update_service.updater_capabilities() == []


class TestNamingTheStaleSidecar:
    def test_a_sidecar_without_pull_never_is_reported_as_stale(self):
        with _version_body(OLD):
            assert update_service.updater_is_stale() is True

    def test_a_current_sidecar_is_not_stale(self):
        with _version_body(CURRENT):
            assert update_service.updater_is_stale() is False

    def test_an_unreachable_sidecar_is_not_called_stale(self):
        """Unreachable is a different problem, already reported separately.

        Calling it stale would send the user to fix the wrong thing.
        """
        with patch("src.system.update_service.requests.get", side_effect=OSError("down")):
            assert update_service.updater_is_stale() is False


class TestTheStatusEndpointSaysSo:
    def test_status_exposes_staleness(self, client, monkeypatch):
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "test-token")
        with (
            patch("src.system.update_service._updater_probe", return_value=True),
            _version_body(OLD),
        ):
            body = client.get("/system/update/status").json()
        assert body["updater_stale"] is True
        assert body["updater_capabilities"] == []

    def test_status_is_quiet_when_the_sidecar_is_current(self, client, monkeypatch):
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "test-token")
        with (
            patch("src.system.update_service._updater_probe", return_value=True),
            _version_body(CURRENT),
        ):
            body = client.get("/system/update/status").json()
        assert body["updater_stale"] is False
        assert "pull-never" in body["updater_capabilities"]


class TestTheLogExplainsTheSymptom:
    def test_switching_channel_on_a_stale_sidecar_logs_the_remedy(self, monkeypatch, caplog):
        """The four-restart dance is the symptom; this is the cause."""
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "test-token")
        monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
        monkeypatch.setenv("VERSION", "8.37.5")

        with (
            patch("src.system.update_service._updater_probe", return_value=True),
            patch("src.system.update_service._updater_version", return_value=OLD),
            patch("src.system.update_service._updater_post", return_value=MagicMock(status_code=202, text="{}")),
            patch("src.system.update_service._take_settings_snapshot", return_value=None),
            caplog.at_level(logging.WARNING, logger="src.system.update_service"),
        ):
            update_service.switch_channel("beta")

        messages = " ".join(r.getMessage() for r in caplog.records).lower()
        assert "sidecar" in messages or "updater" in messages
        assert "reboot" in messages or "pull" in messages, (
            "told the user their sidecar is old without telling them how to fix it"
        )

    def test_a_current_sidecar_switches_without_a_warning(self, monkeypatch, caplog):
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "test-token")
        monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
        monkeypatch.setenv("VERSION", "8.37.5")

        with (
            patch("src.system.update_service._updater_probe", return_value=True),
            patch("src.system.update_service._updater_version", return_value=CURRENT),
            patch("src.system.update_service._updater_post", return_value=MagicMock(status_code=202, text="{}")),
            patch("src.system.update_service._take_settings_snapshot", return_value=None),
            caplog.at_level(logging.WARNING, logger="src.system.update_service"),
        ):
            update_service.switch_channel("beta")

        assert not [r for r in caplog.records if r.levelno >= logging.WARNING], (
            "a healthy sidecar produced a warning; this one must stay rare enough to mean something"
        )
