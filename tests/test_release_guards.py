"""Release guards: Changesets pre mode per branch, the changeset requirement,
and the release decision (scripts/release/*.py).

See docs/internal/development/RELEASING.md for the flow these protect.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.release.changeset_check import (
    SKIP_LABEL,
    check_changeset,
    is_changeset_file,
    is_shipped,
)
from scripts.release.plan import plan_release
from scripts.release.pre_mode import (
    PreJson,
    alpha_release_action,
    check_pre_mode_for_base,
    read_pre_json,
)

ROOT = Path(__file__).resolve().parent.parent

PRE = PreJson(mode="pre", tag="beta")
EXITING = PreJson(mode="exit", tag="beta")
WRONG_TAG = PreJson(mode="pre", tag="alpha")


# ---------------------------------------------------------------------------
# pre_mode.py
# ---------------------------------------------------------------------------


class TestPreModeForBase:
    def test_main_without_pre_json_is_ok(self):
        assert check_pre_mode_for_base("main", None).ok

    def test_main_in_pre_mode_is_blocked(self):
        result = check_pre_mode_for_base("main", PRE)
        assert not result.ok
        assert "changeset pre exit" in result.reason

    def test_main_accepts_exit_mode_for_the_promotion(self):
        assert check_pre_mode_for_base("main", EXITING).ok

    def test_alpha_in_beta_pre_mode_is_ok(self):
        assert check_pre_mode_for_base("alpha", PRE).ok

    def test_alpha_in_exit_mode_is_ok_while_promoting(self):
        assert check_pre_mode_for_base("alpha", EXITING).ok

    @pytest.mark.parametrize("pre", [None, WRONG_TAG])
    def test_alpha_must_keep_the_beta_tag(self, pre):
        result = check_pre_mode_for_base("alpha", pre)
        assert not result.ok
        assert "changeset pre enter beta" in result.reason

    def test_other_bases_are_unchecked(self):
        assert check_pre_mode_for_base("feature/x", PRE).ok

    def test_reasons_are_one_line(self):
        for base in ("main", "alpha", "other"):
            for pre in (None, PRE, EXITING, WRONG_TAG):
                assert "\n" not in check_pre_mode_for_base(base, pre).reason


class TestAlphaReleaseAction:
    def test_releases_in_pre_mode(self):
        assert alpha_release_action(PRE) == "release"

    def test_skips_during_a_promotion(self):
        assert alpha_release_action(EXITING) == "skip"

    @pytest.mark.parametrize("pre", [None, WRONG_TAG])
    def test_refuses_without_beta_pre_mode(self, pre):
        with pytest.raises(ValueError, match="Refusing to release from alpha"):
            alpha_release_action(pre)


def test_read_pre_json(tmp_path):
    assert read_pre_json(tmp_path / "missing.json") is None
    path = tmp_path / "pre.json"
    # The shape `changeset pre enter beta` writes.
    path.write_text(json.dumps({"mode": "pre", "tag": "beta", "initialVersions": {}, "changesets": []}))
    assert read_pre_json(path) == PRE


def test_committed_pre_json_is_one_a_release_branch_accepts():
    """This suite runs on main and on alpha, so it can't know which branch it
    is on: whether pre.json belongs here is release-guards' job (per base
    branch). What holds on both: if pre.json exists it is beta pre mode, or
    exit mode during a promotion.
    """
    pre = read_pre_json(ROOT / ".changeset" / "pre.json")
    assert pre is None or (pre.tag in ("beta", "alpha") and pre.mode in ("pre", "exit"))


# ---------------------------------------------------------------------------
# changeset_check.py
# ---------------------------------------------------------------------------


def _check(files, added=(), head_ref="feat/x", labels=()):
    return check_changeset(files=list(files), added_files=list(added), head_ref=head_ref, labels=list(labels))


class TestChangesetFiles:
    @pytest.mark.parametrize("path", [".changeset/brave-owls-sing.md", ".changeset/issue-12.md"])
    def test_counts(self, path):
        assert is_changeset_file(path)

    @pytest.mark.parametrize(
        "path",
        [".changeset/README.md", ".changeset/config.json", ".changeset/pre.json", ".changeset/pre/old.md", "docs/x.md"],
    )
    def test_does_not_count(self, path):
        assert not is_changeset_file(path)


class TestShipped:
    @pytest.mark.parametrize(
        "path",
        [
            "src/main.py",
            "src/system/update_service.py",
            "web/app/page.tsx",
            "web/package.json",
            "web/package-lock.json",
            "plugins/weather/__init__.py",
            "plugins/weather/manifest.json",
            "requirements.txt",
            "Dockerfile",
            "nginx.conf",
            "entrypoint.sh",
            "supervisord.conf",
            "plugin-registry.json",
            "outputs.lock.json",
            "scripts/seed_outputs.py",
            "pi-image/stage-fiestaboard/01-install-fiestaboard/files/docker-compose.yml",
        ],
    )
    def test_ships(self, path):
        assert is_shipped(path)

    @pytest.mark.parametrize(
        "path",
        [
            "README.md",
            "docs/setup/quick-start.md",
            "plugins/weather/README.md",
            "tests/test_main.py",
            "plugins/weather/tests/test_weather.py",
            "web/src/__tests__/foo.test.tsx",
            "web/app/page.test.tsx",
            "web/tests/a11y.spec.ts",
            "web/tests/fixtures/board.json",
            ".github/workflows/ci.yml",
            "scripts/version-sync.js",
            "scripts/release/plan.py",
            "docker-compose.hub.yml",
            "package.json",
            "CHANGELOG.md",
            ".changeset/config.json",
        ],
    )
    def test_does_not_ship(self, path):
        assert not is_shipped(path)

    def test_a_sidecar_only_change_does_not_ship(self):
        """The updater sidecar has its own image and cadence (#1969 / 8.36.0).

        A sidecar-only PR once cut an app release whose image was byte-identical
        to the previous one, and every install was prompted to take it.
        """
        assert not is_shipped("fiestaupdater/handler.sh")
        assert _check(["fiestaupdater/handler.sh", "fiestaupdater/tests/handler.bats"]).ok

    def test_the_sidecar_still_publishes_itself(self):
        """Not shipping it here is only safe because it has its own lane."""
        workflow = (ROOT / ".github" / "workflows" / "build-fiestaupdater.yml").read_text(encoding="utf-8")
        assert "fiestaupdater/" in workflow

    def test_every_dockerfile_copy_source_is_covered(self):
        """A new COPY in the Dockerfile must not silently escape the check."""
        sources = []
        for line in (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines():
            match = re.match(r"^\s*COPY\s+(?!--from)(.+)$", line)
            if not match:
                continue
            parts = [p for p in match.group(1).split() if not p.startswith("--")]
            sources.extend(p.rstrip("*") for p in parts[:-1])
        assert sources, "parsed no COPY sources from the Dockerfile"
        uncovered = []
        for source in sources:
            if source.rstrip("/") == "tests":
                continue  # copied in, but tests never change behaviour
            probe = source + "x.py" if source.endswith("/") else source
            if not is_shipped(probe):
                uncovered.append(source)
        assert not uncovered, f"Dockerfile COPY sources missing from SHIPPED_PATTERNS: {uncovered}"


class TestCheckChangeset:
    def test_shipped_change_without_a_changeset_fails(self):
        result = _check(["src/main.py", "tests/test_main.py"])
        assert not result.ok
        assert "npx changeset" in result.reason
        assert SKIP_LABEL in result.reason

    def test_a_changeset_satisfies_it(self):
        assert _check(["src/main.py", ".changeset/cool-cats.md"], added=[".changeset/cool-cats.md"]).ok

    def test_a_modified_changeset_does_not_count(self):
        """Only an added file is this PR's changeset; editing someone else's is not."""
        assert not _check(["src/main.py", ".changeset/old.md"], added=[]).ok

    def test_nothing_shipped_needs_nothing(self):
        assert _check(["docs/x.md", ".github/workflows/ci.yml", "tests/test_x.py"]).ok

    def test_the_label_waives_it(self):
        assert _check(["src/main.py"], labels=["backend", SKIP_LABEL]).ok

    @pytest.mark.parametrize(
        "head_ref",
        [
            "changeset-release/main",
            "changeset-release/alpha",
            "main",
            "alpha",
            "dependabot/npm_and_yarn/web/npm-dependencies-1",
        ],
    )
    def test_exempt_head_refs(self, head_ref):
        assert _check(["web/package-lock.json"], head_ref=head_ref).ok

    @pytest.mark.parametrize("head_ref", ["main", "alpha", "changeset-release/main", "dependabot/pip/x"])
    def test_fork_prs_are_never_exempt_by_branch_name(self, head_ref):
        """A contributor's PR from their fork's main is ordinary work, not a sync."""
        assert not check_changeset(
            files=["src/main.py"], added_files=[], head_ref=head_ref, labels=[], same_repo=False
        ).ok

    def test_the_fiestaui_upgrade_pr_is_not_exempt(self):
        """It changes the shipped UI, so it must carry its own changeset."""
        assert not _check(["web/package.json", "web/package-lock.json"], head_ref="fiestaui-upgrade").ok

    def test_a_branch_merely_containing_main_is_not_exempt(self):
        assert not _check(["src/main.py"], head_ref="fix/main-loop").ok

    def test_long_lists_are_truncated(self):
        result = _check([f"src/m{i}.py" for i in range(8)])
        assert "and 3 more" in result.reason
        assert "\n" not in result.reason


# ---------------------------------------------------------------------------
# plan.py
# ---------------------------------------------------------------------------


class TestPlanRelease:
    def test_an_existing_release_means_nothing_to_do(self):
        plan = plan_release(branch="main", version="10.3.2", release_exists=True)
        assert not plan.release

    def test_main_releases_an_unreleased_stable_version(self):
        plan = plan_release(branch="main", version="10.4.0", release_exists=False)
        assert plan.release and not plan.prerelease
        assert plan.tag == "v10.4.0"

    def test_alpha_releases_an_unreleased_beta(self):
        plan = plan_release(branch="alpha", version="10.4.0-beta.0", release_exists=False)
        assert plan.release and plan.prerelease

    def test_main_refuses_a_prerelease(self):
        with pytest.raises(ValueError, match="main would release prerelease"):
            plan_release(branch="main", version="10.4.0-beta.0", release_exists=False)

    @pytest.mark.parametrize("version", ["10.4.0", "10.4.0-alpha.0", "10.4.0-rc.1"])
    def test_alpha_refuses_anything_but_a_beta(self, version):
        with pytest.raises(ValueError, match="alpha would release"):
            plan_release(branch="alpha", version=version, release_exists=False)

    def test_alpha_fresh_from_main_has_nothing_to_release(self):
        """Right after `pre enter`, alpha still carries main's released version."""
        assert not plan_release(branch="alpha", version="10.3.2", release_exists=True).release

    @pytest.mark.parametrize("version", ["v10.4.0", "10.4", "10.4.0+build", "dev"])
    def test_junk_versions_fail(self, version):
        with pytest.raises(ValueError):
            plan_release(branch="main", version=version, release_exists=False)

    def test_main_mid_promotion_carries_a_released_beta(self):
        """After alpha (in exit mode) squash-merges into main, main's package.json
        still says the last beta until main's Version PR lands. That beta is
        released, so this is a no-op, not an error."""
        assert not plan_release(branch="main", version="10.4.0-beta.3", release_exists=True).release

    def test_a_beta_must_sort_above_the_newest_stable(self):
        """Beta installs take the newest version on either channel (#1992)."""
        assert plan_release(
            branch="alpha", version="10.4.0-beta.0", release_exists=False, newest_stable="10.3.2"
        ).release
        for stale in ("10.3.2-beta.0", "10.3.1-beta.4"):
            with pytest.raises(ValueError, match="Restart alpha"):
                plan_release(branch="alpha", version=stale, release_exists=False, newest_stable="10.3.2")

    def test_a_stable_release_must_move_forward(self):
        with pytest.raises(ValueError, match="went backwards"):
            plan_release(branch="main", version="10.3.2", release_exists=False, newest_stable="10.3.2")
        assert plan_release(branch="main", version="10.3.10", release_exists=False, newest_stable="10.3.9").release

    def test_other_branches_never_release(self):
        with pytest.raises(ValueError, match="not a release branch"):
            plan_release(branch="feature/x", version="10.4.0", release_exists=False)


# ---------------------------------------------------------------------------
# Repository wiring
# ---------------------------------------------------------------------------


def test_changesets_is_configured():
    config = json.loads((ROOT / ".changeset" / "config.json").read_text(encoding="utf-8"))
    assert config["baseBranch"] == "main"
    assert config["changelog"][0] == "@changesets/changelog-github"
    assert config["changelog"][1]["repo"] == "Fiestaboard/FiestaBoard"
    # The root package is private: Changesets must still version it, and must
    # not tag it (release.yml tags after the image is pushed).
    assert config["privatePackages"] == {"version": True, "tag": False}

    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["private"] is True
    assert package["scripts"]["version-packages"] == "changeset version && node scripts/version-sync.js"
    assert "@changesets/cli" in package["devDependencies"]


def test_version_files_agree():
    """version-sync.js keeps these equal; a Version PR that skipped it would not."""
    version = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
    assert json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))["version"] == version
    assert json.loads((ROOT / "web" / "package.json").read_text(encoding="utf-8"))["version"] == version
    assert json.loads((ROOT / "web" / "package-lock.json").read_text(encoding="utf-8"))["version"] == version
    init = (ROOT / "src" / "__init__.py").read_text(encoding="utf-8")
    assert f'__version__ = "{version}"' in init
