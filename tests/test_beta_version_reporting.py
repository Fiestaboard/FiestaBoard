"""A beta build must know it is a beta (#1955 follow-on).

The beta version lives only in the ``VERSION`` build-arg. It is deliberately
NOT committed: ``scripts/version-sync.js`` hard-matches ``X.Y.Z`` and throws
on a prerelease string, so writing ``9.0.0-beta.2`` into ``package.json``
would break the next *stable* release.

The consequence, confirmed against the published image:

    $ docker run fiestaboard/fiestaboard:beta
    GET /api/version -> {"package_version": "8.35.5",
                         "build_version": "9.0.0-beta.2", ...}

The update checker compares against ``__version__`` — ``package_version`` —
so a beta install believed it was running stable 8.35.5. Two things follow,
and the second is the dangerous one:

1. it would never recognise a newer beta as an update;
2. once ``main`` ships 8.36.0, the checker would compare 8.36.0 against
   8.35.5, call it newer, and offer a stable build to a beta install as an
   *upgrade* — silently walking the user backwards off the channel they
   opted into, across a schema the older build refuses to read.

So the running version has to be the prerelease when there is one, and the
comparator has to order prereleases the way semver says: ``9.0.0-beta.2``
is newer than ``8.35.5`` but older than ``9.0.0``.
"""

from __future__ import annotations

import pytest

from src import __version__
from src.system.update_service import _is_newer_version, _parse_version, running_version


class TestRunningVersion:
    def test_a_beta_build_reports_its_prerelease(self, monkeypatch):
        monkeypatch.setenv("VERSION", "9.0.0-beta.2")
        assert running_version() == "9.0.0-beta.2"

    def test_a_stable_build_reports_the_package_version(self, monkeypatch):
        """Stable images set VERSION to the same X.Y.Z that is committed."""
        monkeypatch.setenv("VERSION", __version__)
        assert running_version() == __version__

    def test_a_dev_build_reports_the_package_version(self, monkeypatch):
        monkeypatch.setenv("VERSION", "dev")
        assert running_version() == __version__

    def test_an_absent_version_env_reports_the_package_version(self, monkeypatch):
        monkeypatch.delenv("VERSION", raising=False)
        assert running_version() == __version__

    def test_a_junk_version_env_does_not_win(self, monkeypatch):
        """Only a parseable prerelease may override the committed version."""
        monkeypatch.setenv("VERSION", "not-a-version")
        assert running_version() == __version__


class TestPrereleaseOrdering:
    @pytest.mark.parametrize(
        ("older", "newer"),
        [
            ("9.0.0-beta.2", "9.0.0"),  # a prerelease precedes its release
            ("8.35.5", "9.0.0-beta.1"),  # ...but still follows the last stable
            ("9.0.0-beta.2", "9.0.0-beta.10"),  # numeric, not lexicographic
            ("9.0.0-beta.9", "9.0.0-beta.10"),
            ("8.35.5", "8.36.0"),  # plain releases keep working
        ],
    )
    def test_ordering(self, older, newer):
        assert _parse_version(older) < _parse_version(newer), f"{older} should sort below {newer}"
        assert _is_newer_version(newer, older)
        assert not _is_newer_version(older, newer)

    def test_still_fails_closed_on_garbage(self):
        """Unparseable input must not be treated as an update."""
        assert not _is_newer_version("not-a-version", "8.35.5")
        assert not _is_newer_version("8.35.5", "not-a-version")


class TestTheDowngradeTrap:
    def test_a_beta_is_not_offered_an_older_stable_as_an_update(self, monkeypatch):
        """The bug this file exists for.

        A beta install must not be told that the stable release it is ahead
        of is an available upgrade.
        """
        monkeypatch.setenv("VERSION", "9.0.0-beta.2")
        current = running_version()
        assert not _is_newer_version("8.36.0", current), (
            "a beta install was offered stable 8.36.0 as an update — that is a "
            "downgrade across a schema the older build refuses to read"
        )

    def test_a_beta_is_still_offered_a_newer_beta(self, monkeypatch):
        monkeypatch.setenv("VERSION", "9.0.0-beta.2")
        assert _is_newer_version("9.0.0-beta.3", running_version())

    def test_a_beta_is_offered_its_own_final_release(self, monkeypatch):
        """9.0.0 final is a genuine upgrade from 9.0.0-beta.N."""
        monkeypatch.setenv("VERSION", "9.0.0-beta.2")
        assert _is_newer_version("9.0.0", running_version())
