"""Pressing Update Now on a beta box must not land it on stable (#1983 follow-on).

Measured on a real FiestaPi running ``9.0.0-beta.7`` with ``9.0.0-beta.8``
published and correctly discovered (``update_available: true``). Pressing
Update Now produced:

    16:07:55  9.0.0-beta.7   before
    16:08:28  8.37.5         <- the update pulled stable
    16:09:43  8.37.5
    16:10:47  8.37.5
    16:11:44  9.0.0-beta.8   <- the boot re-assert dragged it back

``apply_update`` posts a bodyless ``/update``, and the sidecar's
``handle_update`` runs ``docker compose pull`` against the user's compose
file — which says ``image: fiestaboard/fiestaboard:latest``. On a beta box
that fetches stable, so the "update" is a downgrade across a major version.

It self-heals because :func:`reassert_release_channel` runs at startup, but
the cost is four container recreations, ~4 minutes, and a window in which an
8.x build is pointed at data a 9.x build migrated. The forward-compat guard
added in #1961 makes that window *refuse to load settings* rather than
silently misread them — correct, and still a fault the user sees.

The fix reuses the mechanism that already works: on beta, install the
channel's tag through ``/install`` (added in #1969) instead of asking the
sidecar to pull whatever the compose file names.

Stable must be untouched. A stable box still posts ``/update``, because that
path pulls the user's own compose file and is what keeps a Docker user who
edited their tag on the tag they chose.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import src.system.update_service as update_service
from src.system.update_service import SidecarError


def _accepted():
    """A 202 whose body is real JSON — `apply_update` calls `.json()` on it."""
    resp = MagicMock()
    resp.status_code = 202
    resp.text = '{"status":"queued"}'
    resp.json.return_value = {"status": "queued", "previous_digest": "sha256:abc"}
    return resp


@pytest.fixture
def sidecar(monkeypatch):
    """A reachable, current sidecar; records every POST it receives."""
    monkeypatch.setenv("FIESTAUPDATER_TOKEN", "test-token")
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.delenv("FIESTABOARD_MANAGED_EXTERNALLY", raising=False)

    posted: list[tuple[str, dict]] = []

    def fake_post(path, json=None, **_):
        posted.append((path, json or {}))
        return _accepted()

    with (
        patch("src.system.update_service._updater_probe", return_value=True),
        patch(
            "src.system.update_service._updater_version",
            return_value={"image": "fiestaboard/fiestaboard:latest", "digest": "sha256:abc"},
        ),
        patch("src.system.update_service._updater_post", side_effect=fake_post),
        patch("src.system.update_service._take_settings_snapshot", return_value={"name": "s.json"}),
        # Discovery must be stubbed. The apply path consults it to install the
        # exact version it reported, so leaving it live made these tests call
        # Docker Hub and the GitHub API for real — slow, broken offline, and
        # the asserted tag became whatever happened to be published.
        patch("src.system.update_service._latest_for_channel", return_value=None),
    ):
        yield posted


def _on_beta(monkeypatch):
    """The channel is derived from the running build, not from stored state.

    That is deliberate (`current_channel`): a persisted channel can disagree
    with the image actually running, and on this very path that disagreement
    is what a wrong answer costs. `9.0.0-beta.7` is the build the Pi was on
    when the downgrade was measured.
    """
    monkeypatch.setenv("VERSION", "9.0.0-beta.7")


def _on_stable(monkeypatch):
    monkeypatch.setenv("VERSION", "8.37.5")


class TestABetaBoxStaysOnBeta:
    @pytest.mark.asyncio
    async def test_it_installs_the_beta_tag_rather_than_pulling_latest(self, sidecar, monkeypatch):
        _on_beta(monkeypatch)
        await update_service.apply_update()

        assert sidecar, "the sidecar was never called"
        path, payload = sidecar[-1]
        assert path.lstrip("/") == "install", (
            "a beta box asked the sidecar to pull its compose file's tag; that "
            "file says :latest, so the update fetched stable 8.x over a 9.x box"
        )
        # The moving `:beta` tag is the fallback used when discovery cannot
        # name a version (stubbed to None here). When discovery *does* answer,
        # the exact version is installed instead — see
        # test_beta_graduates_to_stable.py, which supersedes the narrower
        # "always the channel tag" contract this test originally encoded.
        assert payload["tag"] == "beta"
        assert payload["image"] == "fiestaboard/fiestaboard"

    @pytest.mark.asyncio
    async def test_it_never_posts_the_bare_update(self, sidecar, monkeypatch):
        """The bare /update IS the bug — it has no way to name a tag."""
        _on_beta(monkeypatch)
        await update_service.apply_update()
        assert not [p for p, _ in sidecar if p.lstrip("/") == "update"]

    @pytest.mark.asyncio
    async def test_it_still_snapshots_first(self, sidecar, monkeypatch):
        """The snapshot is the way back across a schema migration."""
        _on_beta(monkeypatch)
        order: list[str] = []

        def snap(*_a, **_k):
            order.append("snapshot")
            return {"name": "s.json"}

        def post(path, json=None, **_):
            order.append(path.lstrip("/"))
            return _accepted()

        with (
            patch("src.system.update_service._take_settings_snapshot", side_effect=snap),
            patch("src.system.update_service._updater_post", side_effect=post),
        ):
            await update_service.apply_update()
        assert order == ["snapshot", "install"], order


class TestStableIsUnchanged:
    """The whole value of the stable path is that it is boring."""

    @pytest.mark.asyncio
    async def test_a_stable_box_still_posts_update(self, sidecar, monkeypatch):
        _on_stable(monkeypatch)
        await update_service.apply_update()

        assert sidecar
        path, payload = sidecar[-1]
        assert path.lstrip("/") == "update", (
            "the stable path changed; it must keep pulling the user's own "
            "compose file so a Docker user who edited their tag keeps it"
        )
        assert payload in ({}, None)

    @pytest.mark.asyncio
    async def test_a_stable_box_never_installs_a_tag(self, sidecar, monkeypatch):
        _on_stable(monkeypatch)
        await update_service.apply_update()
        assert not [p for p, _ in sidecar if p.lstrip("/") == "install"]


class TestDegradingAgainstAnOldSidecar:
    @pytest.mark.asyncio
    async def test_a_sidecar_without_install_is_named_as_the_problem(self, monkeypatch):
        """/install shipped in #1969; anyone older gets a 404, not a mystery."""
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "test-token")
        monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
        _on_beta(monkeypatch)

        resp404 = MagicMock(status_code=404, text='{"error":"not_found"}')
        with (
            patch("src.system.update_service._updater_probe", return_value=True),
            patch(
                "src.system.update_service._updater_version",
                return_value={"image": "fiestaboard/fiestaboard:latest", "digest": "d"},
            ),
            patch("src.system.update_service._updater_post", return_value=resp404),
            patch("src.system.update_service._take_settings_snapshot", return_value=None),
            pytest.raises(SidecarError) as excinfo,
        ):
            await update_service.apply_update()

        detail = str(excinfo.value).lower()
        assert "too old" in detail, f"a 404 from an old sidecar surfaced as a generic error: {detail!r}"
        assert "docker compose pull" in detail, "no remedy given"
