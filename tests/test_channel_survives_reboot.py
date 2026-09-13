"""A release channel must survive a reboot (#1955 follow-on).

Switching channel retags the chosen image onto the reference the compose
file names. That is the only mechanism available — the app cannot edit the
compose file, and on a FiestaPi it does not even mount it.

But the compose file still says ``image: fiestaboard/fiestaboard:latest``
with ``pull_policy: always``, and the Pi's systemd unit runs
``docker compose pull`` before ``up -d`` on every boot. So the boot re-pulls
real stable straight over the retag. Measured end to end against the real
images:

    baseline            8.37.2
    switch to beta  ->  9.0.0-beta.4
    reboot          ->  8.37.2        <- silently reverted

Rewriting the compose file would fix it at the source, but nothing updates
``/opt/fiestaboard/docker-compose.yml`` on an app update and the sidecar
mounts it read-only, so that fix cannot reach the Pis already out there.

Instead the *choice* is persisted in the data dir — which is writable and
does survive — and re-asserted at startup when the build that came up does
not match it. One extra restart per boot while on beta, and it works on
installs that exist today.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import src.api_server as api_server


@pytest.fixture
def sidecar_ready(monkeypatch):
    monkeypatch.setenv("FIESTAUPDATER_TOKEN", "test-token")
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.delenv("FIESTABOARD_MANAGED_EXTERNALLY", raising=False)
    with (
        patch("src.api_server._updater_probe", return_value=True),
        patch(
            "src.api_server._updater_version",
            return_value={"image": "fiestaboard/fiestaboard:latest", "digest": "sha256:abc"},
        ),
    ):
        yield


class TestRememberingTheChoice:
    def test_switching_persists_the_channel(self, sidecar_ready, monkeypatch):
        """The retag is ephemeral, so the intent has to be written down."""
        monkeypatch.setenv("VERSION", "8.37.2")
        resp = MagicMock(status_code=202, text="{}")
        with (
            patch("src.api_server._updater_post", return_value=resp),
            patch("src.api_server._take_settings_snapshot", return_value=None),
        ):
            api_server._switch_channel_sync("beta")
        assert api_server._system_update_state_load().get("channel") == "beta"


class TestReassertingAtBoot:
    def test_a_beta_choice_reinstalls_when_stable_came_up(self, sidecar_ready, monkeypatch):
        monkeypatch.setenv("VERSION", "8.37.2")  # the reboot brought stable back
        api_server._system_update_state_update(channel="beta")

        calls: list[tuple] = []

        def post(path, json=None, **_):
            calls.append((path, json))
            return MagicMock(status_code=202, text="{}")

        with (
            patch("src.api_server._updater_post", side_effect=post),
            patch("src.api_server._take_settings_snapshot", return_value=None),
        ):
            api_server._reassert_release_channel()

        assert calls, "the persisted beta choice was not re-asserted after the reboot"
        path, payload = calls[-1]
        assert path.lstrip("/") == "install"
        assert payload["tag"] == "beta"

    def test_it_does_nothing_when_the_build_already_matches(self, sidecar_ready, monkeypatch):
        """The common case: it came up on the channel we asked for."""
        monkeypatch.setenv("VERSION", "9.0.0-beta.4")
        api_server._system_update_state_update(channel="beta")
        with patch("src.api_server._updater_post") as post:
            api_server._reassert_release_channel()
        assert not post.called, "reinstalled a channel the running build already is"

    def test_it_does_nothing_when_no_choice_was_ever_made(self, sidecar_ready, monkeypatch):
        """An install that never opted in must never be moved."""
        monkeypatch.setenv("VERSION", "8.37.2")
        state = api_server._system_update_state_load()
        state.pop("channel", None)
        api_server._system_update_state_save(state)
        with patch("src.api_server._updater_post") as post:
            api_server._reassert_release_channel()
        assert not post.called

    def test_a_home_assistant_install_is_never_touched(self, monkeypatch):
        """Supervisor owns updating there; our sidecar would race it.

        Everything EXCEPT the HA signal is made to look healthy — probe up,
        image reference resolvable — so the only thing that can stop the
        re-assert is the managed-externally check. An earlier version of
        this test left `_updater_version` unstubbed, so it passed because
        the resolve failed first; mutating the carve-out out did not break
        it, which is how that was caught.
        """
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "test-token")
        monkeypatch.setenv("SUPERVISOR_TOKEN", "ha-token")
        monkeypatch.setenv("VERSION", "8.37.2")
        api_server._system_update_state_update(channel="beta")
        with (
            patch("src.api_server._updater_probe", return_value=True),
            patch(
                "src.api_server._updater_version",
                return_value={"image": "fiestaboard/fiestaboard:latest", "digest": "sha256:abc"},
            ),
            patch("src.api_server._take_settings_snapshot", return_value=None),
            patch("src.api_server._updater_post") as post,
        ):
            api_server._reassert_release_channel()
        assert not post.called, "a Home Assistant install had its channel re-asserted"

    def test_no_sidecar_means_no_attempt(self, monkeypatch):
        monkeypatch.setenv("FIESTAUPDATER_TOKEN", "")
        monkeypatch.setenv("VERSION", "8.37.2")
        api_server._system_update_state_update(channel="beta")
        with patch("src.api_server._updater_post") as post:
            api_server._reassert_release_channel()
        assert not post.called

    def test_a_failed_reassert_does_not_raise(self, sidecar_ready, monkeypatch):
        """Boot must not be taken down by an unreachable registry."""
        monkeypatch.setenv("VERSION", "8.37.2")
        api_server._system_update_state_update(channel="beta")
        with (
            patch("src.api_server._updater_post", side_effect=RuntimeError("boom")),
            patch("src.api_server._take_settings_snapshot", return_value=None),
        ):
            api_server._reassert_release_channel()  # must not raise

    def test_switching_back_to_stable_is_remembered_too(self, sidecar_ready, monkeypatch):
        """Leaving beta must not leave 'beta' persisted, or boot would undo it."""
        monkeypatch.setenv("VERSION", "9.0.0-beta.4")
        resp = MagicMock(status_code=202, text="{}")
        with (
            patch("src.api_server._updater_post", return_value=resp),
            patch("src.api_server._take_settings_snapshot", return_value=None),
        ):
            api_server._switch_channel_sync("stable")
        assert api_server._system_update_state_load().get("channel") == "stable"


class TestAFailedSwitchIsNotRemembered:
    """Recording intent the sidecar refused would make every boot retry it.

    Found by driving the real endpoint against a stack whose token did not
    match: the switch returned 500, the box stayed on stable — and "beta"
    was already written to the state file. The boot re-assert would then
    attempt the same doomed install on every single boot, with the recorded
    channel permanently disagreeing with the running one and nothing in the
    UI to explain it.

    The sidecar answering 202 is the earliest honest moment: it means the
    work was accepted. Anything before that is a wish, not a choice.
    """

    @pytest.mark.parametrize(
        ("status", "why"),
        [(401, "token rejected"), (404, "sidecar too old"), (502, "sidecar error")],
    )
    def test_a_refused_switch_leaves_the_channel_alone(self, sidecar_ready, monkeypatch, status, why):
        monkeypatch.setenv("VERSION", "8.37.2")
        state = api_server._system_update_state_load()
        state.pop("channel", None)
        api_server._system_update_state_save(state)

        resp = MagicMock(status_code=status, text="nope")
        with (
            patch("src.api_server._updater_post", return_value=resp),
            patch("src.api_server._take_settings_snapshot", return_value=None),
            pytest.raises(HTTPException),
        ):
            api_server._switch_channel_sync("beta")

        assert api_server._system_update_state_load().get("channel") is None, (
            f"a switch the sidecar refused ({why}) was recorded anyway; every boot would retry it"
        )

    def test_an_unreachable_sidecar_leaves_the_channel_alone(self, sidecar_ready, monkeypatch):
        import requests as _requests

        monkeypatch.setenv("VERSION", "8.37.2")
        state = api_server._system_update_state_load()
        state.pop("channel", None)
        api_server._system_update_state_save(state)

        with (
            patch("src.api_server._updater_post", side_effect=_requests.ConnectionError("down")),
            patch("src.api_server._take_settings_snapshot", return_value=None),
            pytest.raises(HTTPException),
        ):
            api_server._switch_channel_sync("beta")

        assert api_server._system_update_state_load().get("channel") is None
