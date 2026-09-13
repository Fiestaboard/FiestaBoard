"""Opting into the beta channel from a stable install (#1955).

The chicken-and-egg this solves: if the opt-in only ships on the beta, you
can only find it after you have already opted in. So the control has to live
on the stable line, which is this file.

Switching is one-way here on purpose. Joining the beta lands you on 9.x,
which carries the leave half — there is no reason to write that twice.

Mechanically the app never edits a compose file (it cannot: the sidecar
mounts it read-only and the Pi image's app container does not mount it at
all). It asks the sidecar to pull a named tag and retag it onto whatever
reference the compose file already names — ``POST /install``, added to
fiestaupdater in #1969.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sidecar(monkeypatch):
    """A reachable sidecar that accepts /install."""
    monkeypatch.setenv("FIESTAUPDATER_TOKEN", "test-token")
    monkeypatch.delenv("FIESTABOARD_MANAGED_EXTERNALLY", raising=False)
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)

    posted: list[tuple[str, dict]] = []

    def fake_post(path, json=None, **_):
        posted.append((path, json or {}))
        resp = MagicMock()
        resp.status_code = 202
        resp.text = '{"status":"queued"}'
        return resp

    with (
        patch("src.api_server._updater_probe", return_value=True),
        patch(
            "src.api_server._updater_version",
            return_value={"image": "fiestaboard/fiestaboard:latest", "digest": "sha256:abc"},
        ),
        patch("src.api_server._updater_post", side_effect=fake_post),
    ):
        yield posted


class TestReadingTheChannel:
    def test_a_stable_build_reports_stable(self, client, sidecar, monkeypatch):
        monkeypatch.setenv("VERSION", "8.35.5")
        body = client.get("/system/channel").json()
        assert body["channel"] == "stable"

    def test_a_beta_build_reports_beta(self, client, sidecar, monkeypatch):
        """Derived from the build version — no persisted state to drift."""
        monkeypatch.setenv("VERSION", "9.0.0-beta.3")
        assert client.get("/system/channel").json()["channel"] == "beta"

    def test_switching_is_offered_when_the_sidecar_is_there(self, client, sidecar, monkeypatch):
        monkeypatch.setenv("VERSION", "8.35.5")
        assert client.get("/system/channel").json()["can_switch"] is True

    def test_switching_is_refused_without_the_sidecar(self, client, monkeypatch):
        """No sidecar means no way to install a tag. Say so, do not offer it."""
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "")
        body = client.get("/system/channel").json()
        assert body["can_switch"] is False
        assert body["reason"]

    def test_switching_is_refused_on_a_home_assistant_install(self, client, monkeypatch):
        """HA Supervisor owns updating; our sidecar would race it."""
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "test-token")
        monkeypatch.setenv("SUPERVISOR_TOKEN", "ha-token")
        body = client.get("/system/channel").json()
        assert body["can_switch"] is False
        assert "home assistant" in body["reason"].lower()


class TestJoiningTheBeta:
    def test_it_asks_the_sidecar_for_the_beta_tag(self, client, sidecar, monkeypatch):
        monkeypatch.setenv("VERSION", "8.35.5")
        response = client.post("/system/channel", json={"channel": "beta"})
        assert response.status_code == 200

        assert sidecar, "the sidecar was never called"
        path, payload = sidecar[-1]
        assert path.lstrip("/") == "install"
        assert payload["tag"] == "beta"
        # The repo only — the tag is the other field, and sending
        # "repo:tag" as the image would ask for "repo:tag:beta".
        assert payload["image"] == "fiestaboard/fiestaboard"

    def test_it_snapshots_before_switching(self, client, sidecar, monkeypatch):
        """The snapshot IS the way back. It has to exist before we move."""
        monkeypatch.setenv("VERSION", "8.35.5")
        with patch("src.api_server._take_settings_snapshot") as snap:
            snap.return_value = {"name": "pre-update-x.json"}
            client.post("/system/channel", json={"channel": "beta"})
        assert snap.called, "switched channel without taking a snapshot first"

    def test_the_snapshot_is_taken_before_the_sidecar_call(self, client, sidecar, monkeypatch):
        """Ordering matters: a snapshot taken after the swap is worthless."""
        monkeypatch.setenv("VERSION", "8.35.5")
        order: list[str] = []

        def snap(*_a, **_k):
            order.append("snapshot")
            return {"name": "pre-update-x.json"}

        def post(path, json=None, **_):
            order.append("install")
            resp = MagicMock()
            resp.status_code = 202
            resp.text = "{}"
            return resp

        with (
            patch("src.api_server._take_settings_snapshot", side_effect=snap),
            patch("src.api_server._updater_post", side_effect=post),
        ):
            client.post("/system/channel", json={"channel": "beta"})
        assert order == ["snapshot", "install"], order

    def test_an_unknown_channel_is_rejected(self, client, sidecar):
        assert client.post("/system/channel", json={"channel": "nightly"}).status_code == 422

    def test_a_missing_channel_is_rejected(self, client, sidecar):
        assert client.post("/system/channel", json={}).status_code == 422

    def test_home_assistant_installs_cannot_switch(self, client, monkeypatch):
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "test-token")
        monkeypatch.setenv("SUPERVISOR_TOKEN", "ha-token")
        assert client.post("/system/channel", json={"channel": "beta"}).status_code == 503

    def test_an_old_sidecar_is_reported_as_needing_an_update(self, client, monkeypatch):
        """A sidecar without /install 404s. That must not read as 'broken'.

        The endpoint shipped in #1969; anyone who has not pulled the sidecar
        since gets a 404, and the only useful thing to tell them is to pull.
        """
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "test-token")
        monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
        resp404 = MagicMock()
        resp404.status_code = 404
        resp404.text = '{"error":"not_found"}'

        with (
            patch("src.api_server._updater_probe", return_value=True),
            patch(
                "src.api_server._updater_version",
                return_value={"image": "fiestaboard/fiestaboard:latest", "digest": "d"},
            ),
            patch("src.api_server._updater_post", return_value=resp404),
            patch("src.api_server._take_settings_snapshot", return_value=None),
        ):
            response = client.post("/system/channel", json={"channel": "beta"})

        assert response.status_code == 503
        detail = str(response.json().get("detail", "")).lower()
        assert "sidecar" in detail or "updater" in detail
        assert "pull" in detail or "update" in detail
