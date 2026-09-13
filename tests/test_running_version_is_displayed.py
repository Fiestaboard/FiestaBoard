"""The UI must show the version that is actually running (#1955 follow-on).

Reported from a real FiestaPi that had successfully switched to the beta:
the sidebar read **v8.37.2** while the box was running **9.0.0-beta.4**.

Both numbers were honest in isolation. A beta's version lives only in the
``VERSION`` build-arg — it is deliberately never committed, because
``scripts/version-sync.js`` rejects a prerelease string and a committed one
would break the next stable release. So ``src/__init__.py`` still carries
whatever stable number the branch last synced from, and that is what
``package_version`` reports.

The UI rendered ``package_version``, so a beta tester sees a number that is
not what they are running, files bugs against it, and cannot tell which
build a symptom came from. ``/version`` now states the running version
outright rather than leaving each consumer to work it out — the sidebar,
the About card and anything added later then agree by construction.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src import __version__
from src.api_server import app


@pytest.fixture
def client():
    return TestClient(app)


class TestRunningVersion:
    def test_a_beta_build_reports_its_prerelease(self, client, monkeypatch):
        monkeypatch.setenv("VERSION", "9.0.0-beta.4")
        body = client.get("/version").json()
        assert body["running_version"] == "9.0.0-beta.4"

    def test_a_stable_build_reports_the_committed_version(self, client, monkeypatch):
        monkeypatch.setenv("VERSION", __version__)
        assert client.get("/version").json()["running_version"] == __version__

    def test_a_dev_build_falls_back_to_the_committed_version(self, client, monkeypatch):
        """`VERSION=dev` is not a version anyone can act on."""
        monkeypatch.setenv("VERSION", "dev")
        assert client.get("/version").json()["running_version"] == __version__

    def test_junk_falls_back_rather_than_being_displayed(self, client, monkeypatch):
        monkeypatch.setenv("VERSION", "not-a-version")
        assert client.get("/version").json()["running_version"] == __version__

    def test_the_original_fields_are_unchanged(self, client, monkeypatch):
        """Additive only — the About card shows both on purpose."""
        monkeypatch.setenv("VERSION", "9.0.0-beta.4")
        body = client.get("/version").json()
        assert body["package_version"] == __version__
        assert body["build_version"] == "9.0.0-beta.4"

    def test_the_beta_case_that_was_reported(self, client, monkeypatch):
        """The exact pairing seen on the Pi: don't show 8.37.2 for a beta."""
        monkeypatch.setenv("VERSION", "9.0.0-beta.4")
        body = client.get("/version").json()
        assert body["running_version"] != body["package_version"], (
            "a beta build reported the committed stable number as its running "
            "version, which is what put v8.37.2 in the sidebar of a box running "
            "9.0.0-beta.4"
        )
