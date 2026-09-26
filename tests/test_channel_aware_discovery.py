"""A beta install must be able to see a newer beta (#1955, plan Layer 2).

Observed on a real FiestaPi running 9.0.0-beta.4 while 9.0.0-beta.5 was on
Docker Hub:

    current_version:  9.0.0-beta.4
    latest_version:   8.37.5
    update_available: false

Both discovery sources are blind to prereleases, and deliberately so:

* ``_check_dockerhub_for_latest`` keeps only tags whose dot-parts are all
  digits, so ``9.0.0-beta.5`` never survives the filter;
* ``_check_github_releases_for_latest`` calls ``/releases/latest``, which
  GitHub *defines* as excluding prereleases.

That exclusion is the entire mechanism keeping a beta away from someone who
never asked for one, so it must not be weakened. The fix is a second path
taken only when the install is ON the beta channel — which left the beta a
one-way door: you could join it and then never move again.

The most important tests here are the ones asserting the STABLE path is
unchanged. Everything else is additive.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

import src.system.update_service as us

#: A Docker Hub page carrying both stable and prerelease tags, as the real
#: registry does today.
MIXED_TAGS = {
    "results": [
        {"name": "latest"},
        {"name": "beta"},
        {"name": "8.37.5"},
        {"name": "8.37.4"},
        {"name": "9.0.0-beta.4"},
        {"name": "9.0.0-beta.5"},
        {"name": "9.0.0-beta.10"},
    ]
}


def _dockerhub(payload, *, next_page=None):
    body = dict(payload)
    body.setdefault("next", next_page)
    resp = MagicMock(status_code=200)
    resp.json.return_value = body
    resp.raise_for_status.return_value = None
    return resp


class TestStableIsUnchanged:
    """The guard rail. A beta must never leak into the stable channel."""

    def test_stable_ignores_every_prerelease_tag(self):
        with patch("src.system.update_service.requests.get", return_value=_dockerhub(MIXED_TAGS)):
            assert us._check_dockerhub_for_latest("stable") == "8.37.5"

    def test_stable_still_uses_releases_latest(self):
        """GitHub's /releases/latest is what excludes prereleases for us."""
        seen: list[str] = []

        def get(url, **_):
            seen.append(url)
            resp = MagicMock(status_code=200)
            resp.json.return_value = {"tag_name": "v8.37.5"}
            resp.raise_for_status.return_value = None
            return resp

        with patch("src.system.update_service.requests.get", side_effect=get):
            assert us._check_github_releases_for_latest("stable") == "8.37.5"
        assert seen[-1].endswith("/releases/latest"), seen


class TestBetaCanSeeBetas:
    def test_beta_picks_the_newest_prerelease(self):
        with patch("src.system.update_service.requests.get", return_value=_dockerhub(MIXED_TAGS)):
            assert us._check_dockerhub_for_latest("beta") == "9.0.0-beta.10"

    def test_beta_numbers_compare_numerically_not_as_text(self):
        """beta.10 is newer than beta.9; a string sort says otherwise."""
        tags = {"results": [{"name": "9.0.0-beta.9"}, {"name": "9.0.0-beta.10"}]}
        with patch("src.system.update_service.requests.get", return_value=_dockerhub(tags)):
            assert us._check_dockerhub_for_latest("beta") == "9.0.0-beta.10"

    def test_beta_prefers_a_final_release_over_its_prereleases(self):
        """Once 9.0.0 ships, a beta tester should be offered it."""
        tags = {"results": [{"name": "9.0.0-beta.5"}, {"name": "9.0.0"}]}
        with patch("src.system.update_service.requests.get", return_value=_dockerhub(tags)):
            assert us._check_dockerhub_for_latest("beta") == "9.0.0"

    def test_beta_reads_prereleases_from_the_github_list(self):
        def get(url, **_):
            resp = MagicMock(status_code=200)
            resp.raise_for_status.return_value = None
            if "/releases/latest" in url:
                resp.json.return_value = {"tag_name": "v8.37.5"}
            else:
                resp.json.return_value = [
                    {"tag_name": "v9.0.0-beta.5", "prerelease": True, "draft": False},
                    {"tag_name": "v8.37.5", "prerelease": False, "draft": False},
                ]
            return resp

        with patch("src.system.update_service.requests.get", side_effect=get):
            assert us._check_github_releases_for_latest("beta") == "9.0.0-beta.5"

    def test_drafts_are_not_offered(self):
        def get(url, **_):
            resp = MagicMock(status_code=200)
            resp.raise_for_status.return_value = None
            resp.json.return_value = [
                {"tag_name": "v9.0.0-beta.9", "prerelease": True, "draft": True},
                {"tag_name": "v9.0.0-beta.5", "prerelease": True, "draft": False},
            ]
            return resp

        with patch("src.system.update_service.requests.get", side_effect=get):
            assert us._check_github_releases_for_latest("beta") == "9.0.0-beta.5"


class TestPagination:
    def test_it_follows_pages(self):
        """Tags are paginated; the newest need not be on page one.

        The pre-existing implementation read one page and stopped, which
        silently caps discovery once the tag list outgrows a page.
        """
        pages = [
            _dockerhub({"results": [{"name": "8.30.0"}]}, next_page="PAGE2"),
            _dockerhub({"results": [{"name": "8.37.5"}]}),
        ]
        with patch("src.system.update_service.requests.get", side_effect=pages):
            assert us._check_dockerhub_for_latest("stable") == "8.37.5"

    def test_pagination_is_bounded(self):
        """A registry that always reports another page must not hang a boot."""
        always_more = _dockerhub({"results": [{"name": "8.0.0"}]}, next_page="MORE")
        with patch("src.system.update_service.requests.get", return_value=always_more) as get:
            us._check_dockerhub_for_latest("stable")
        assert get.call_count <= 10, f"followed {get.call_count} pages unbounded"


class TestTheReportedSymptom:
    def test_a_beta_install_is_offered_the_newer_beta(self):
        """The exact case from the Pi: on beta.4, with beta.5 published."""
        with patch("src.system.update_service.requests.get", return_value=_dockerhub(MIXED_TAGS)):
            latest = us._check_dockerhub_for_latest("beta")
        assert us._is_newer_version(latest, "9.0.0-beta.4"), f"a beta install on 9.0.0-beta.4 was not offered {latest}"

    def test_a_stable_install_is_not_offered_a_beta(self):
        with patch("src.system.update_service.requests.get", return_value=_dockerhub(MIXED_TAGS)):
            latest = us._check_dockerhub_for_latest("stable")
        assert "beta" not in latest
        assert not us._is_newer_version(latest, "8.37.5")


class TestFailureHandling:
    @pytest.mark.parametrize("channel", ["stable", "beta"])
    def test_a_broken_source_returns_none_rather_than_raising(self, channel):
        with patch("src.system.update_service.requests.get", side_effect=RuntimeError("down")):
            assert us._check_dockerhub_for_latest(channel) is None
            assert us._check_github_releases_for_latest(channel) is None

    def test_unparseable_json_is_survivable(self):
        resp = MagicMock(status_code=200)
        resp.json.side_effect = json.JSONDecodeError("nope", "", 0)
        resp.raise_for_status.return_value = None
        with patch("src.system.update_service.requests.get", return_value=resp):
            assert us._check_dockerhub_for_latest("beta") is None


class TestTheCheckUsesTheRunningChannel:
    """Wiring: the discovery functions are only useful if the check calls them
    with the channel the box is actually on."""

    @pytest.mark.parametrize(
        ("version_env", "expected_channel"),
        [("9.0.0-beta.4", "beta"), ("8.37.5", "stable")],
    )
    def test_the_channel_reaches_both_sources(self, monkeypatch, version_env, expected_channel):
        import asyncio as _asyncio

        monkeypatch.setenv("VERSION", version_env)
        seen: list[str] = []

        def dh(channel="stable"):
            seen.append(f"dockerhub:{channel}")
            return

        def gh(channel="stable"):
            seen.append(f"github:{channel}")
            return

        with (
            patch("src.system.update_service._check_dockerhub_for_latest", side_effect=dh),
            patch("src.system.update_service._check_github_releases_for_latest", side_effect=gh),
        ):
            _asyncio.run(us._perform_update_check())

        assert f"dockerhub:{expected_channel}" in seen, seen
        assert f"github:{expected_channel}" in seen, seen
