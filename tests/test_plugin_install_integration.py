"""Integration tests for the plugin install/update/uninstall system.

These tests exercise the real ``git`` binary end-to-end — the ``git init`` +
``fetch`` + ``reset`` install path, the fetch/reset update path, and
uninstall — but against **local fixture repositories** (``file://`` URLs)
rather than the live plugin repos on GitHub.

They used to clone ``fiestaboard-plugin--dad-jokes`` and
``fiestaboard-plugin--star-trek-quotes`` for real. Every CI run then counted
as a fresh "unique cloner" in those repos' GitHub traffic stats, inflating
the numbers shown on fiestaboard.app/stats far above the real fleet
baseline (each Actions runner IP is a new unique). Local fixtures keep the
same git mechanics under test with zero external traffic and no network
flake.

Run explicitly with::

    pytest -m integration tests/test_plugin_install_integration.py -v

They are intentionally excluded from the main coverage run so they do not
slow down fast unit tests.
"""

import json
import subprocess
from pathlib import Path

import pytest

from src.plugins import sources
from src.plugins.sources import (
    RegistryEntry,
    clone_or_update_repo,
    install_git_plugin,
    install_registry_plugin,
    load_registry,
    remove_external_plugin,
)

pytestmark = pytest.mark.integration

# The fixture repo follows the registry naming convention so it passes
# validate_registry_repo_name and plugin-id derivation, exactly like a
# published plugin repo would.
FIXTURE_REPO_NAME = "fiestaboard-plugin--ci-fixture"
FIXTURE_PLUGIN_ID = "ci_fixture"


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", "-c", "user.email=ci-fixture@example.com", "-c", "user.name=CI Fixture", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _git_log(path, n=3):
    """Return the last n commit hashes from a local repo."""
    result = subprocess.run(
        ["git", "log", f"-{n}", "--format=%H"],
        cwd=path,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip().splitlines()


def _make_plugin_repo(base: Path, repo_name: str = FIXTURE_REPO_NAME) -> Path:
    """Create a local git repo that looks like a published plugin repo."""
    src = base / repo_name
    src.mkdir(parents=True)
    manifest = {
        "id": FIXTURE_PLUGIN_ID,
        "name": "CI Fixture",
        "version": "1.0.0",
        "description": "Local fixture plugin for install integration tests",
        "fiestaboard_version": "1.0.0",
    }
    (src / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (src / "__init__.py").write_text('"""CI fixture plugin."""\n')
    _git("init", "--quiet", "-b", "main", cwd=src)
    _git("add", ".", cwd=src)
    _git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "initial", cwd=src)
    return src


@pytest.fixture(autouse=True)
def _allow_file_urls(monkeypatch):
    """Bypass the https-only URL validation for local ``file://`` fixtures.

    Production only ever clones ``https://`` URLs; the validation rules
    themselves are unit-tested in test_plugin_sources.py. Bypassing here
    lets the full git install path run against local repos.
    """
    monkeypatch.setattr(sources, "_validate_git_url", lambda url: (True, ""))


@pytest.fixture
def fixture_repo(tmp_path):
    """A local plugin source repo. Returns (file_url, source_path)."""
    src = _make_plugin_repo(tmp_path / "remote")
    return src.as_uri(), src


@pytest.fixture
def external_dir(tmp_path):
    """The external-plugins install target, separate from the source repo."""
    dest = tmp_path / "external"
    dest.mkdir()
    return dest


# ---------------------------------------------------------------------------
# clone_or_update_repo — raw git layer
# ---------------------------------------------------------------------------


class TestCloneOrUpdateRepoIntegration:
    def test_fresh_clone(self, fixture_repo, external_dir):
        """Cloning a real repo succeeds and creates expected plugin files."""
        url, _ = fixture_repo
        ok, err = clone_or_update_repo(url, FIXTURE_PLUGIN_ID, external_dir=external_dir)

        assert ok, f"clone failed: {err}"
        assert err == ""
        dest = external_dir / FIXTURE_PLUGIN_ID
        assert dest.is_dir()
        assert (dest / "manifest.json").exists()
        assert (dest / "__init__.py").exists()

    def test_clone_creates_valid_git_repo(self, fixture_repo, external_dir):
        """Cloned directory is a proper git repo with commit history."""
        url, _ = fixture_repo
        clone_or_update_repo(url, FIXTURE_PLUGIN_ID, external_dir=external_dir)

        dest = external_dir / FIXTURE_PLUGIN_ID
        commits = _git_log(dest)
        assert len(commits) >= 1, "expected at least one commit in cloned repo"

    def test_update_existing_clone_fetches_new_commits(self, fixture_repo, external_dir):
        """Re-running clone_or_update_repo picks up new upstream commits."""
        url, src = fixture_repo
        ok, err = clone_or_update_repo(url, FIXTURE_PLUGIN_ID, external_dir=external_dir)
        assert ok, f"initial clone failed: {err}"
        dest = external_dir / FIXTURE_PLUGIN_ID
        assert not (dest / "NEW_FILE.txt").exists()

        # Land a new commit upstream, then update.
        (src / "NEW_FILE.txt").write_text("updated\n")
        _git("add", ".", cwd=src)
        _git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "update", cwd=src)

        ok, err = clone_or_update_repo(url, FIXTURE_PLUGIN_ID, external_dir=external_dir)
        assert ok, f"update (git fetch/reset) failed: {err}"
        assert (dest / "NEW_FILE.txt").exists(), "update did not fetch the new commit"

    def test_missing_repo_returns_error(self, tmp_path, external_dir):
        """Cloning a non-existent repo returns (False, <error message>)."""
        missing_url = (tmp_path / "remote" / "fiestaboard-plugin--does-not-exist").as_uri()
        ok, err = clone_or_update_repo(missing_url, "nonexistent", external_dir=external_dir)

        assert not ok
        assert err  # some error message present
        dest = external_dir / "nonexistent"
        assert not dest.exists()


# ---------------------------------------------------------------------------
# install_registry_plugin — registry path
# ---------------------------------------------------------------------------


class TestInstallRegistryPluginIntegration:
    def test_real_registry_parses(self):
        """plugin-registry.json loads and contains known plugins (no cloning)."""
        registry = load_registry()
        ids = {e.plugin_id for e in registry}
        assert "dad_jokes" in ids, "dad_jokes not found in plugin-registry.json"

    def test_installs_from_registry_entry(self, fixture_repo, external_dir):
        """install_registry_plugin clones the repo into external_dir/plugin_id."""
        url, _ = fixture_repo
        entry = RegistryEntry(plugin_id=FIXTURE_PLUGIN_ID, name="CI Fixture", repository=url)

        ok, err = install_registry_plugin(entry, external_dir=external_dir)

        assert ok, f"registry install failed: {err}"
        dest = external_dir / FIXTURE_PLUGIN_ID
        assert dest.is_dir()
        assert (dest / "manifest.json").exists()
        assert (dest / "__init__.py").exists()

    def test_manifest_has_expected_fields(self, fixture_repo, external_dir):
        """Cloned manifest contains the required fields set during extraction."""
        url, _ = fixture_repo
        entry = RegistryEntry(plugin_id=FIXTURE_PLUGIN_ID, name="CI Fixture", repository=url)

        install_registry_plugin(entry, external_dir=external_dir)
        manifest = json.loads((external_dir / FIXTURE_PLUGIN_ID / "manifest.json").read_text())

        assert manifest.get("id") == FIXTURE_PLUGIN_ID
        assert "name" in manifest
        assert "version" in manifest
        assert "fiestaboard_version" in manifest, "fiestaboard_version must be set during extraction"

    def test_rejects_non_registry_naming(self, external_dir):
        """install_registry_plugin refuses repos that don't follow the naming convention."""
        entry = RegistryEntry(
            plugin_id="bad",
            name="Bad",
            repository="https://github.com/someone/my-random-repo",
        )
        ok, err = install_registry_plugin(entry, external_dir=external_dir)

        assert not ok
        assert "fiestaboard-plugin--" in err


# ---------------------------------------------------------------------------
# install_git_plugin — arbitrary git URL path
# ---------------------------------------------------------------------------


class TestInstallGitPluginIntegration:
    def test_installs_from_arbitrary_url(self, fixture_repo, external_dir):
        """install_git_plugin clones any valid Fiestaboard plugin URL."""
        url, _ = fixture_repo
        ok, err = install_git_plugin(url, external_dir=external_dir)

        assert ok, f"git URL install failed: {err}"
        dest = external_dir / FIXTURE_PLUGIN_ID
        assert dest.is_dir()
        assert (dest / "manifest.json").exists()
        assert (dest / "__init__.py").exists()

    def test_plugin_id_derived_from_repo_name(self, fixture_repo, external_dir):
        """Plugin directory name is correctly derived from the repository name."""
        url, _ = fixture_repo
        install_git_plugin(url, external_dir=external_dir)

        # fiestaboard-plugin--ci-fixture → ci_fixture
        assert (external_dir / FIXTURE_PLUGIN_ID).is_dir()

    def test_plugin_id_override(self, fixture_repo, external_dir):
        """Explicit plugin_id overrides the name derived from the URL."""
        url, _ = fixture_repo
        ok, err = install_git_plugin(
            url,
            plugin_id="custom_alias",
            external_dir=external_dir,
        )

        assert ok, f"install with override id failed: {err}"
        assert (external_dir / "custom_alias").is_dir()
        assert not (external_dir / FIXTURE_PLUGIN_ID).exists()


# ---------------------------------------------------------------------------
# remove_external_plugin — uninstall path
# ---------------------------------------------------------------------------


class TestUninstallIntegration:
    def test_uninstall_removes_cloned_directory(self, fixture_repo, external_dir):
        """Uninstalling a real cloned plugin removes its directory from disk."""
        url, _ = fixture_repo
        entry = RegistryEntry(plugin_id=FIXTURE_PLUGIN_ID, name="CI Fixture", repository=url)

        install_registry_plugin(entry, external_dir=external_dir)
        dest = external_dir / FIXTURE_PLUGIN_ID
        assert dest.exists(), "plugin directory should exist before uninstall"

        removed = remove_external_plugin(dest)

        assert removed
        assert not dest.exists(), "plugin directory should be gone after uninstall"

    def test_uninstall_then_reinstall(self, fixture_repo, external_dir):
        """A plugin can be reinstalled cleanly after being uninstalled."""
        url, _ = fixture_repo
        entry = RegistryEntry(plugin_id=FIXTURE_PLUGIN_ID, name="CI Fixture", repository=url)

        dest = external_dir / FIXTURE_PLUGIN_ID

        install_registry_plugin(entry, external_dir=external_dir)
        assert dest.exists()

        remove_external_plugin(dest)
        assert not dest.exists()

        ok, err = install_registry_plugin(entry, external_dir=external_dir)
        assert ok, f"reinstall after uninstall failed: {err}"
        assert dest.exists()
        assert (dest / "manifest.json").exists()
