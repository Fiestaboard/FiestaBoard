"""A beta install must be able to step onto stable once stable overtakes it.

The beta channel is only usable if there is a way out of it. The safe way out
is not a downgrade — it is waiting for the release to catch up:

    9.0.0-beta.12  ->  9.0.0        same data generation, an ordinary update
    9.0.0-beta.12  ->  8.37.5       a downgrade across a major; refuses to
                                    read data the beta migrated (#1961)

Discovery already handles the first: ``_parse_version`` ranks ``9.0.0`` above
every ``9.0.0-beta.N``, so the box is told the release is available.

The apply path did not. ``CHANNEL_TAGS["beta"]`` is the *moving* ``:beta``
tag, so Update Now installed "whatever the newest beta is" rather than the
version the user had just been shown. In the window where ``9.0.0`` is the
newest thing published, the box reported ``9.0.0`` available, the user
clicked, and the sidecar reinstalled ``9.0.0-beta.12`` — told one thing,
given another, and no way forward.

Installing the *discovered* version instead fixes that, and does something
better on the way: ``current_channel()`` reads the running build, so a box
that lands on ``9.0.0`` — no prerelease identifier — reports itself as
stable from that moment on. Graduating off the beta needs no separate
control; it is what happens when the release catches up.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import src.system.update_service as update_service


def _accepted():
    resp = MagicMock(status_code=202, text='{"status":"queued"}')
    resp.json.return_value = {"status": "queued", "previous_digest": "sha256:abc"}
    return resp


@pytest.fixture
def sidecar(monkeypatch):
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
    ):
        yield posted


def _discovers(version):
    """What the update check would report as newest for this channel."""
    return patch("src.system.update_service._latest_for_channel", return_value=version)


class TestGraduatingOntoTheRelease:
    @pytest.mark.asyncio
    async def test_it_installs_the_release_once_it_overtakes_the_beta(self, sidecar, monkeypatch):
        monkeypatch.setenv("VERSION", "9.0.0-beta.12")
        with _discovers("9.0.0"):
            await update_service.apply_update()

        path, payload = sidecar[-1]
        assert path.lstrip("/") == "install"
        assert payload["tag"] == "9.0.0", (
            "the box was shown 9.0.0 and then sent the moving :beta tag, which "
            "reinstalls the older beta it is already running"
        )

    @pytest.mark.asyncio
    async def test_a_newer_beta_is_installed_by_exact_version(self, sidecar, monkeypatch):
        """Same mechanism keeps beta->beta honest: install what was shown."""
        monkeypatch.setenv("VERSION", "9.0.0-beta.12")
        with _discovers("9.0.0-beta.13"):
            await update_service.apply_update()
        assert sidecar[-1][1]["tag"] == "9.0.0-beta.13"

    @pytest.mark.asyncio
    async def test_landing_on_the_release_reports_the_stable_channel(self, monkeypatch):
        """The graduation itself — no separate opt-out needed for this case."""
        monkeypatch.setenv("VERSION", "9.0.0")
        assert update_service.current_channel() == "stable"

    @pytest.mark.asyncio
    async def test_a_beta_build_still_reports_beta(self, monkeypatch):
        monkeypatch.setenv("VERSION", "9.0.0-beta.12")
        assert update_service.current_channel() == "beta"


class TestFallingBackSafely:
    @pytest.mark.asyncio
    async def test_the_moving_tag_is_used_when_discovery_fails(self, sidecar, monkeypatch):
        """A registry hiccup must not block an update; :beta is still correct."""
        monkeypatch.setenv("VERSION", "9.0.0-beta.12")
        with _discovers(None):
            await update_service.apply_update()
        assert sidecar[-1][1]["tag"] == "beta"

    @pytest.mark.asyncio
    async def test_an_older_discovery_result_is_not_installed(self, sidecar, monkeypatch):
        """Never move a box backwards on an update.

        Today's stable (8.37.5) is genuinely older than the running beta, and
        a stale or wrong discovery result must not be able to downgrade a box
        across a major version. Leaving the beta is a deliberate act, not
        something Update Now does by accident.
        """
        monkeypatch.setenv("VERSION", "9.0.0-beta.12")
        with _discovers("8.37.5"):
            await update_service.apply_update()
        assert sidecar[-1][1]["tag"] == "beta", "an update moved the box backwards across a major"

    @pytest.mark.asyncio
    async def test_a_junk_discovery_result_is_ignored(self, sidecar, monkeypatch):
        monkeypatch.setenv("VERSION", "9.0.0-beta.12")
        with _discovers("not-a-version"):
            await update_service.apply_update()
        assert sidecar[-1][1]["tag"] == "beta"


class TestStableIsUntouched:
    @pytest.mark.asyncio
    async def test_a_stable_box_still_pulls_its_own_compose_file(self, sidecar, monkeypatch):
        monkeypatch.setenv("VERSION", "8.37.5")
        with _discovers("8.38.0"):
            await update_service.apply_update()
        assert sidecar[-1][0].lstrip("/") == "update"

    @pytest.mark.asyncio
    async def test_discovery_is_not_even_consulted_on_stable(self, sidecar, monkeypatch):
        """Stable's whole contract is that it pulls the tag the user chose."""
        monkeypatch.setenv("VERSION", "8.37.5")
        with patch("src.system.update_service._latest_for_channel") as latest:
            await update_service.apply_update()
        assert not latest.called
