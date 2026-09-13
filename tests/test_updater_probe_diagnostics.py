"""A sidecar that stops answering must leave a trail (#1955 follow-on).

Found on a real FiestaPi whose Update Now button had silently vanished.
``GET /system/update/status`` said ``updater_available: false`` and nothing
else — and searching that box's logs for "updater", "sidecar" and
"fiestaupdater" returned **zero hits across all three**. The probe swallows
every exception and returns False, so the one event a user needs to see
leaves no evidence at all.

The cost is not theoretical. That Pi had been unable to take an update for
four days: it sat on 8.35.0 while 8.35.1 through 8.36.0 shipped, and the
only clue anywhere was a missing button.

Logging it once per transition — not once per poll — is the whole fix. The
status endpoint is polled every 30s by the settings page, so an unguarded
log line would bury the journal faster than silence hides the problem.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
import requests

import src.api_server as api_server


@pytest.fixture(autouse=True)
def _reset_probe_state():
    """The log is edge-triggered, so each test starts from a known edge."""
    api_server._updater_probe_last_ok = None
    yield
    api_server._updater_probe_last_ok = None


class TestTheProbeLeavesATrail:
    def test_a_failing_probe_is_logged(self, caplog):
        with (
            patch("src.api_server.requests.get", side_effect=requests.ConnectionError("nope")),
            caplog.at_level(logging.WARNING, logger="src.api_server"),
        ):
            assert api_server._updater_probe() is False

        messages = " ".join(r.getMessage() for r in caplog.records)
        assert "updater" in messages.lower() or "sidecar" in messages.lower(), (
            "a sidecar that stopped answering produced no log line; that is "
            "exactly the state that cost four days on a real FiestaPi"
        )

    def test_the_failure_is_logged_once_not_once_per_poll(self, caplog):
        """The settings page polls this every 30 seconds."""
        with (
            patch("src.api_server.requests.get", side_effect=requests.ConnectionError("nope")),
            caplog.at_level(logging.WARNING, logger="src.api_server"),
        ):
            for _ in range(5):
                api_server._updater_probe()

        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1, (
            f"probe logged {len(warnings)} times for 5 polls; an unguarded log "
            "line buries the journal faster than silence hides the problem"
        )

    def test_recovery_is_logged_too(self, caplog):
        """Coming back matters as much as going away when you are debugging."""
        with patch("src.api_server.requests.get", side_effect=requests.ConnectionError("nope")):
            api_server._updater_probe()

        class _Ok:
            status_code = 200

        with (
            patch("src.api_server.requests.get", return_value=_Ok()),
            caplog.at_level(logging.INFO, logger="src.api_server"),
        ):
            assert api_server._updater_probe() is True

        messages = " ".join(r.getMessage() for r in caplog.records).lower()
        assert "again" in messages or "recover" in messages or "reachable" in messages, (
            "the sidecar came back and said nothing about it"
        )

    def test_a_healthy_probe_stays_quiet(self, caplog):
        class _Ok:
            status_code = 200

        with (
            patch("src.api_server.requests.get", return_value=_Ok()),
            caplog.at_level(logging.INFO, logger="src.api_server"),
        ):
            for _ in range(3):
                assert api_server._updater_probe() is True

        assert not [r for r in caplog.records if r.levelno >= logging.WARNING], (
            "a working sidecar must not generate warnings"
        )

    def test_a_non_200_counts_as_down(self, caplog):
        """Not every failure is an exception; a 503 is still unreachable."""

        class _Bad:
            status_code = 503

        with (
            patch("src.api_server.requests.get", return_value=_Bad()),
            caplog.at_level(logging.WARNING, logger="src.api_server"),
        ):
            assert api_server._updater_probe() is False
        assert [r for r in caplog.records if r.levelno >= logging.WARNING]
