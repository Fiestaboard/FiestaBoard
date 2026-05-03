"""Integration tests for the plugin install/update/uninstall system.

These tests perform real ``git clone`` and ``git pull`` operations against
actual Fiestaboard plugin repositories on GitHub.  They require network
access and a working ``git`` binary.

Run explicitly with::

    pytest -m integration tests/test_plugin_install_integration.py -v

They are intentionally excluded from the main coverage run so they do not
slow down fast, offline unit tests.
"""

import subprocess

import pytest

from src.plugins.sources import (
    RegistryEntry,
    clone_or_update_repo,
    install_git_plugin,
    install_registry_plugin,
    load_registry,
    remove_external_plugin,
)

pytestmark = pytest.mark.integration

# Use dad_jokes for registry flow (tiny repo, no API key required)
REGISTRY_PLUGIN_ID = "dad_jokes"
REGISTRY_REPO_URL = "https://github.com/Fiestaboard/fiestaboard-plugin--dad-jokes"

# Use star_trek_quotes for the arbitrary git URL flow (also tiny, no API key)
GIT_PLUGIN_ID = "star_trek_quotes"
GIT_REPO_URL = "https://github.com/Fiestaboard/fiestaboard-plugin--star-trek-quotes"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git_log(path, n=3):
    """Return the last n commit hashes from a local repo."""
    result = subprocess.run(
        ["git", "log", f"-{n}", "--format=%H"],
        cwd=path,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip().splitlines()


def _has_git():
    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


# ---------------------------------------------------------------------------
# clone_or_update_repo — raw git layer
# ---------------------------------------------------------------------------


class TestCloneOrUpdateRepoIntegration:
    def test_fresh_clone(self, tmp_path):
        """Cloning a real repo succeeds and creates expected plugin files."""
        ok, err = clone_or_update_repo(REGISTRY_REPO_URL, REGISTRY_PLUGIN_ID, external_dir=tmp_path)

        assert ok, f"clone failed: {err}"
        assert err == ""
        dest = tmp_path / REGISTRY_PLUGIN_ID
        assert dest.is_dir()
        assert (dest / "manifest.json").exists()
        assert (dest / "__init__.py").exists()

    def test_clone_creates_valid_git_repo(self, tmp_path):
        """Cloned directory is a proper git repo with commit history."""
        clone_or_update_repo(REGISTRY_REPO_URL, REGISTRY_PLUGIN_ID, external_dir=tmp_path)

        dest = tmp_path / REGISTRY_PLUGIN_ID
        commits = _git_log(dest)
        assert len(commits) >= 1, "expected at least one commit in cloned repo"

    def test_update_existing_clone_via_pull(self, tmp_path):
        """Re-running clone_or_update_repo on an existing directory runs git pull."""
        # First clone
        ok, err = clone_or_update_repo(REGISTRY_REPO_URL, REGISTRY_PLUGIN_ID, external_dir=tmp_path)
        assert ok, f"initial clone failed: {err}"
        dest = tmp_path / REGISTRY_PLUGIN_ID
        commits_before = _git_log(dest)

        # Second call should succeed (pull, already up-to-date is fine)
        ok, err = clone_or_update_repo(REGISTRY_REPO_URL, REGISTRY_PLUGIN_ID, external_dir=tmp_path)
        assert ok, f"update (git pull) failed: {err}"

        commits_after = _git_log(dest)
        # History must be at least as long (pull never loses commits)
        assert len(commits_after) >= len(commits_before)

    def test_invalid_url_returns_error(self, tmp_path):
        """Cloning a non-existent repo returns (False, <error message>)."""
        ok, err = clone_or_update_repo(
            "https://github.com/Fiestaboard/fiestaboard-plugin--does-not-exist-xyz",
            "nonexistent",
            external_dir=tmp_path,
        )
        assert not ok
        assert err  # some error message present
        dest = tmp_path / "nonexistent"
        assert not dest.exists()


# ---------------------------------------------------------------------------
# install_registry_plugin — registry path
# ---------------------------------------------------------------------------


class TestInstallRegistryPluginIntegration:
    def test_installs_from_registry_entry(self, tmp_path):
        """install_registry_plugin clones the repo into external_dir/plugin_id."""
        registry = load_registry()
        entry = next((e for e in registry if e.plugin_id == REGISTRY_PLUGIN_ID), None)
        assert entry is not None, f"{REGISTRY_PLUGIN_ID} not found in plugin-registry.json"

        ok, err = install_registry_plugin(entry, external_dir=tmp_path)

        assert ok, f"registry install failed: {err}"
        dest = tmp_path / REGISTRY_PLUGIN_ID
        assert dest.is_dir()
        assert (dest / "manifest.json").exists()
        assert (dest / "__init__.py").exists()

    def test_manifest_has_expected_fields(self, tmp_path):
        """Cloned manifest contains the required fields set during extraction."""
        import json

        registry = load_registry()
        entry = next((e for e in registry if e.plugin_id == REGISTRY_PLUGIN_ID), None)
        assert entry is not None

        install_registry_plugin(entry, external_dir=tmp_path)
        manifest = json.loads((tmp_path / REGISTRY_PLUGIN_ID / "manifest.json").read_text())

        assert manifest.get("id") == REGISTRY_PLUGIN_ID
        assert "name" in manifest
        assert "version" in manifest
        assert "fiestaboard_version" in manifest, "fiestaboard_version must be set during extraction"

    def test_rejects_non_registry_naming(self, tmp_path):
        """install_registry_plugin refuses repos that don't follow the naming convention."""
        entry = RegistryEntry(
            plugin_id="bad",
            name="Bad",
            repository="https://github.com/someone/my-random-repo",
        )
        ok, err = install_registry_plugin(entry, external_dir=tmp_path)

        assert not ok
        assert "fiestaboard-plugin--" in err


# ---------------------------------------------------------------------------
# install_git_plugin — arbitrary git URL path
# ---------------------------------------------------------------------------


class TestInstallGitPluginIntegration:
    def test_installs_from_arbitrary_url(self, tmp_path):
        """install_git_plugin clones any valid Fiestaboard plugin URL."""
        ok, err = install_git_plugin(GIT_REPO_URL, external_dir=tmp_path)

        assert ok, f"git URL install failed: {err}"
        dest = tmp_path / GIT_PLUGIN_ID
        assert dest.is_dir()
        assert (dest / "manifest.json").exists()
        assert (dest / "__init__.py").exists()

    def test_plugin_id_derived_from_repo_name(self, tmp_path):
        """Plugin directory name is correctly derived from the repository name."""
        install_git_plugin(GIT_REPO_URL, external_dir=tmp_path)

        # fiestaboard-plugin--star-trek-quotes → star_trek_quotes
        assert (tmp_path / GIT_PLUGIN_ID).is_dir()

    def test_plugin_id_override(self, tmp_path):
        """Explicit plugin_id overrides the name derived from the URL."""
        ok, err = install_git_plugin(
            GIT_REPO_URL,
            plugin_id="custom_alias",
            external_dir=tmp_path,
        )

        assert ok, f"install with override id failed: {err}"
        assert (tmp_path / "custom_alias").is_dir()
        assert not (tmp_path / GIT_PLUGIN_ID).exists()


# ---------------------------------------------------------------------------
# remove_external_plugin — uninstall path
# ---------------------------------------------------------------------------


class TestUninstallIntegration:
    def test_uninstall_removes_cloned_directory(self, tmp_path):
        """Uninstalling a real cloned plugin removes its directory from disk."""
        registry = load_registry()
        entry = next((e for e in registry if e.plugin_id == REGISTRY_PLUGIN_ID), None)
        assert entry is not None

        install_registry_plugin(entry, external_dir=tmp_path)
        dest = tmp_path / REGISTRY_PLUGIN_ID
        assert dest.exists(), "plugin directory should exist before uninstall"

        removed = remove_external_plugin(dest)

        assert removed
        assert not dest.exists(), "plugin directory should be gone after uninstall"

    def test_uninstall_then_reinstall(self, tmp_path):
        """A plugin can be reinstalled cleanly after being uninstalled."""
        registry = load_registry()
        entry = next((e for e in registry if e.plugin_id == REGISTRY_PLUGIN_ID), None)
        assert entry is not None

        dest = tmp_path / REGISTRY_PLUGIN_ID

        install_registry_plugin(entry, external_dir=tmp_path)
        assert dest.exists()

        remove_external_plugin(dest)
        assert not dest.exists()

        ok, err = install_registry_plugin(entry, external_dir=tmp_path)
        assert ok, f"reinstall after uninstall failed: {err}"
        assert dest.exists()
        assert (dest / "manifest.json").exists()
