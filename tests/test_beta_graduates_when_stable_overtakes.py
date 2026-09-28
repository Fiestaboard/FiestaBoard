"""A beta box that updates onto a newer stable must stay there.

Measured on a real FiestaPi running ``9.3.0-beta.50`` with ``9.3.1`` published
and correctly discovered (``update_available: true``, ``latest_version:
9.3.1``). Pressing Update Now produced:

    04:20:37  apply_update posts /install  tag=9.3.1
    04:21:00  sidecar reports  status=success  action=install
    04:21:12  container boots
    04:30:09  running_version STILL 9.3.0-beta.50

The install works. What undoes it is the next startup:
:func:`reassert_release_channel` reads the *stored* channel — still ``beta``,
written when the box joined — sees a stable build running, and calls
``switch_channel("beta")``, which installs ``:beta`` and puts the box back on
``9.3.0-beta.50``. Every update round-trips and the offer reappears forever.

``apply_update`` believes it handles this. Its comment says naming the exact
version "graduates the box off the beta for free: current_channel() reads the
running build, so landing on a release with no prerelease identifier reports
stable from then on". That is true of ``current_channel()`` and false of the
box, because ``reassert_release_channel`` consults stored state, not the
running build, and drags it back.

``leave_beta`` is not the answer here. It exists for the *downgrade* case —
abandoning a beta before the release catches up — and unconditionally restores
the configuration captured at join time. When stable has overtaken the beta,
as here, going forward is an ordinary update and the join-time settings must
not be resurrected.

So the graduation has to happen where the disagreement is detected: a stored
``beta`` preference is satisfied, not violated, by running a stable build that
is newer than anything the beta channel offers.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import pytest

import src.system.update_service as update_service


@contextmanager
def _running(monkeypatch, build: str):
    """Pin the build this box is on, the way the image would.

    Two different functions answer "what is running", and a test has to set
    both or it is testing a box that cannot exist. ``current_channel()`` reads
    the ``VERSION`` build-arg. ``running_version()`` reads ``VERSION`` only
    when it carries a prerelease, and otherwise falls back to ``__version__``
    baked into the package — which in a test is whatever this checkout is on,
    not the build being simulated.
    """
    monkeypatch.setenv("VERSION", build)
    with patch("src.system.update_service.running_version", return_value=build):
        yield


@pytest.fixture
def state(tmp_path, monkeypatch):
    """An isolated system-update state file, pre-joined to the beta."""
    monkeypatch.setattr(update_service, "SYSTEM_UPDATE_STATE_FILE", tmp_path / ".system-update.json")
    update_service._system_update_state_update(channel="beta")
    return tmp_path / ".system-update.json"


@pytest.fixture
def switchable(monkeypatch):
    """A box that is allowed to change channel, recording any switch."""
    monkeypatch.setenv("FIESTAUPDATER_TOKEN", "test-token")
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.delenv("FIESTABOARD_MANAGED_EXTERNALLY", raising=False)
    with (
        patch("src.system.update_service._updater_probe", return_value=True),
        patch("src.system.update_service.switch_channel") as switch,
    ):
        yield switch


class TestABetaBoxOvertakenByStable:
    """The running build is newer than every beta; the box has graduated."""

    def test_a_boot_on_the_newer_stable_does_not_reinstall_the_beta(self, state, switchable, monkeypatch):
        # 9.3.1 (stable) is newer than 9.3.0-beta.50, the newest beta there is.
        with (
            _running(monkeypatch, "9.3.1"),
            patch("src.system.update_service._newest_on_channel", return_value="9.3.0-beta.50"),
        ):
            update_service.reassert_release_channel()
        assert not switchable.called, (
            "the boot reinstalled the beta over a newer stable build — this is the loop that "
            "pinned a real Pi to 9.3.0-beta.50 while telling it 9.3.1 was available"
        )

    def test_the_stored_channel_is_updated_so_the_loop_cannot_restart(self, state, switchable, monkeypatch):
        """Not switching is not enough; the disagreement has to be resolved.

        Left as ``beta``, the very next boot re-runs the same comparison, and
        any code that consults the stored preference still believes this box
        wants a beta it is already ahead of.
        """
        with (
            _running(monkeypatch, "9.3.1"),
            patch("src.system.update_service._newest_on_channel", return_value="9.3.0-beta.50"),
        ):
            update_service.reassert_release_channel()
        assert update_service._system_update_state_load().get("channel") == "stable"


class TestABetaBoxStillBehind:
    """Unchanged behaviour: a boot that genuinely overrode the choice."""

    def test_a_boot_onto_older_stable_still_reasserts_the_beta(self, state, switchable, monkeypatch):
        # The #1977 case: `pull_policy: always` re-pulled :latest over the
        # retag and the box came up on a stable build OLDER than its beta.
        with (
            _running(monkeypatch, "9.2.5"),
            patch("src.system.update_service._newest_on_channel", return_value="9.3.0-beta.50"),
        ):
            update_service.reassert_release_channel()
        switchable.assert_called_once_with("beta")

    def test_a_box_already_on_its_beta_is_left_alone(self, state, switchable, monkeypatch):
        with (
            _running(monkeypatch, "9.3.0-beta.50"),
            patch("src.system.update_service._newest_on_channel", return_value="9.3.0-beta.50"),
        ):
            update_service.reassert_release_channel()
        assert not switchable.called

    def test_an_unreachable_registry_does_not_strand_the_box_on_stable(self, state, switchable, monkeypatch):
        """Discovery failing must not be read as "no beta exists, graduate".

        A boot must survive an unreachable registry (the function's own
        contract), and silently converting a beta tester to stable because
        Docker Hub was down would be a one-way door.
        """
        with (
            _running(monkeypatch, "9.2.5"),
            patch("src.system.update_service._newest_on_channel", return_value=None),
        ):
            update_service.reassert_release_channel()
        switchable.assert_called_once_with("beta")
        assert update_service._system_update_state_load().get("channel") == "beta"
