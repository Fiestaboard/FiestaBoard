"""Tests for the external plugin sources module."""

import json
import os
import subprocess
import textwrap
from pathlib import Path
from unittest import mock

import pytest

from src.plugins.sources import (
    REGISTRY_PREFIX,
    PluginSource,
    RegistryEntry,
    _repo_name_from_url,
    clone_or_update_repo,
    get_external_plugins_dir,
    install_git_plugin,
    install_registry_plugin,
    load_registry,
    plugin_id_from_repo_name,
    remove_external_plugin,
    validate_registry_repo_name,
)


# ── PluginSource ─────────────────────────────────────────────────────────────


class TestPluginSource:
    def test_to_dict(self):
        src = PluginSource(source_type="builtin", local_path="/a/b")
        assert src.to_dict() == {
            "source_type": "builtin",
            "repository_url": "",
            "local_path": "/a/b",
        }

    def test_default_values(self):
        src = PluginSource(source_type="external")
        assert src.repository_url == ""
        assert src.local_path == ""


# ── RegistryEntry ────────────────────────────────────────────────────────────


class TestRegistryEntry:
    def test_from_dict_full(self):
        data = {
            "id": "my_plugin",
            "name": "My Plugin",
            "description": "desc",
            "repository": "https://github.com/FiestaBoard/fiestaboard-plugin--my-plugin",
            "branch": "main",
            "author": "Alice",
        }
        entry = RegistryEntry.from_dict(data)
        assert entry.plugin_id == "my_plugin"
        assert entry.name == "My Plugin"
        assert entry.repository == data["repository"]
        assert entry.branch == "main"
        assert entry.author == "Alice"

    def test_from_dict_minimal(self):
        entry = RegistryEntry.from_dict({"id": "foo", "name": "Foo"})
        assert entry.plugin_id == "foo"
        assert entry.repository == ""
        assert entry.branch == ""


# ── Naming convention ────────────────────────────────────────────────────────


class TestNamingConvention:
    def test_valid_names(self):
        ok, _ = validate_registry_repo_name(
            "https://github.com/FiestaBoard/fiestaboard-plugin--weather"
        )
        assert ok

    def test_valid_name_with_dashes(self):
        ok, _ = validate_registry_repo_name(
            "https://github.com/FiestaBoard/fiestaboard-plugin--my-cool-plugin"
        )
        assert ok

    def test_invalid_missing_prefix(self):
        ok, reason = validate_registry_repo_name(
            "https://github.com/someone/my-plugin"
        )
        assert not ok
        assert "fiestaboard-plugin--" in reason

    def test_invalid_uppercase(self):
        ok, _ = validate_registry_repo_name(
            "https://github.com/FiestaBoard/Fiestaboard-plugin--Weather"
        )
        assert not ok

    def test_repo_name_extraction(self):
        assert (
            _repo_name_from_url(
                "https://github.com/FiestaBoard/fiestaboard-plugin--foo.git"
            )
            == "fiestaboard-plugin--foo"
        )

    def test_repo_name_no_git_suffix(self):
        assert (
            _repo_name_from_url(
                "https://github.com/FiestaBoard/fiestaboard-plugin--bar"
            )
            == "fiestaboard-plugin--bar"
        )

    def test_repo_name_trailing_slash(self):
        assert (
            _repo_name_from_url(
                "https://github.com/FiestaBoard/fiestaboard-plugin--baz/"
            )
            == "fiestaboard-plugin--baz"
        )


class TestPluginIdFromRepoName:
    def test_with_prefix(self):
        assert plugin_id_from_repo_name("fiestaboard-plugin--my-weather") == "my_weather"

    def test_without_prefix(self):
        assert plugin_id_from_repo_name("my-cool-plugin") == "my_cool_plugin"

    def test_simple(self):
        assert plugin_id_from_repo_name("fiestaboard-plugin--stocks") == "stocks"


# ── load_registry ────────────────────────────────────────────────────────────


class TestLoadRegistry:
    def test_loads_valid_registry(self, tmp_path):
        registry = {
            "version": "1.0.0",
            "plugins": [
                {
                    "id": "ext_weather",
                    "name": "External Weather",
                    "repository": "https://github.com/Org/fiestaboard-plugin--ext-weather",
                }
            ],
        }
        path = tmp_path / "plugin-registry.json"
        path.write_text(json.dumps(registry))

        entries = load_registry(path)
        assert len(entries) == 1
        assert entries[0].plugin_id == "ext_weather"

    def test_skips_invalid_entries(self, tmp_path):
        registry = {
            "plugins": [
                {"id": "good", "name": "G", "repository": "https://github.com/x/y"},
                {"name": "Missing id"},  # no id
                {"id": "no_repo", "name": "N"},  # no repository
            ]
        }
        path = tmp_path / "plugin-registry.json"
        path.write_text(json.dumps(registry))

        entries = load_registry(path)
        assert len(entries) == 1
        assert entries[0].plugin_id == "good"

    def test_missing_file_returns_empty(self, tmp_path):
        entries = load_registry(tmp_path / "nonexistent.json")
        assert entries == []

    def test_invalid_json_returns_empty(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json")
        entries = load_registry(path)
        assert entries == []

    def test_empty_plugins_array(self, tmp_path):
        path = tmp_path / "empty.json"
        path.write_text(json.dumps({"plugins": []}))
        entries = load_registry(path)
        assert entries == []


# ── git URL validation ───────────────────────────────────────────────────────


class TestGitUrlValidation:
    def test_rejects_non_https(self):
        from src.plugins.sources import _validate_git_url

        ok, _ = _validate_git_url("git@github.com:Org/repo.git")
        assert not ok

    def test_rejects_path_traversal(self):
        from src.plugins.sources import _validate_git_url

        ok, _ = _validate_git_url("https://github.com/../../etc/passwd")
        assert not ok

    def test_accepts_valid_https(self):
        from src.plugins.sources import _validate_git_url

        ok, _ = _validate_git_url("https://github.com/FiestaBoard/fiestaboard-plugin--x")
        assert ok


# ── clone_or_update_repo ─────────────────────────────────────────────────────


class TestCloneOrUpdateRepo:
    @mock.patch("src.plugins.sources.subprocess.run")
    def test_clone_fresh(self, mock_run, tmp_path):
        dest = tmp_path / "my_plugin"
        ok, err = clone_or_update_repo("https://github.com/Org/repo", dest)
        assert ok
        assert err == ""
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "clone" in cmd

    @mock.patch("src.plugins.sources.subprocess.run")
    def test_pull_existing(self, mock_run, tmp_path):
        dest = tmp_path / "my_plugin"
        dest.mkdir()
        (dest / ".git").mkdir()  # Simulate existing clone
        ok, err = clone_or_update_repo("https://github.com/Org/repo", dest)
        assert ok
        cmd = mock_run.call_args[0][0]
        assert "pull" in cmd

    @mock.patch(
        "src.plugins.sources.subprocess.run",
        side_effect=subprocess.SubprocessError("network error"),
    )
    def test_clone_failure(self, mock_run, tmp_path):
        dest = tmp_path / "fail_plugin"
        ok, err = clone_or_update_repo("https://github.com/Org/repo", dest)
        assert not ok
        assert "network error" in err

    def test_rejects_ssh_url(self, tmp_path):
        dest = tmp_path / "ssh_plugin"
        ok, err = clone_or_update_repo("git@github.com:Org/repo.git", dest)
        assert not ok
        assert "HTTPS" in err


# ── install helpers ──────────────────────────────────────────────────────────


class TestInstallRegistryPlugin:
    @mock.patch("src.plugins.sources.clone_or_update_repo", return_value=(True, ""))
    def test_valid_install(self, mock_clone, tmp_path):
        entry = RegistryEntry(
            plugin_id="ext_weather",
            name="Weather",
            repository="https://github.com/FiestaBoard/fiestaboard-plugin--ext-weather",
        )
        ok, err = install_registry_plugin(entry, external_dir=tmp_path)
        assert ok
        assert err == ""
        mock_clone.assert_called_once()

    def test_rejects_bad_name(self, tmp_path):
        entry = RegistryEntry(
            plugin_id="bad",
            name="Bad",
            repository="https://github.com/someone/bad-name",
        )
        ok, err = install_registry_plugin(entry, external_dir=tmp_path)
        assert not ok
        assert "fiestaboard-plugin--" in err


class TestInstallGitPlugin:
    @mock.patch("src.plugins.sources.clone_or_update_repo", return_value=(True, ""))
    def test_install_custom(self, mock_clone, tmp_path):
        ok, err = install_git_plugin(
            "https://github.com/someone/my-cool-plugin",
            external_dir=tmp_path,
        )
        assert ok
        assert err == ""

    @mock.patch("src.plugins.sources.clone_or_update_repo", return_value=(True, ""))
    def test_install_with_override_id(self, mock_clone, tmp_path):
        ok, err = install_git_plugin(
            "https://github.com/someone/repo",
            plugin_id="custom_id",
            external_dir=tmp_path,
        )
        assert ok
        # Check that the dest directory used the override id
        dest = mock_clone.call_args[0][1]
        assert dest == tmp_path / "custom_id"


# ── remove_external_plugin ───────────────────────────────────────────────────


class TestRemoveExternalPlugin:
    def test_removes_existing(self, tmp_path):
        d = tmp_path / "to_remove"
        d.mkdir()
        (d / "manifest.json").write_text("{}")
        assert remove_external_plugin(d)
        assert not d.exists()

    def test_returns_false_for_missing(self, tmp_path):
        assert not remove_external_plugin(tmp_path / "nonexistent")


# ── get_external_plugins_dir ─────────────────────────────────────────────────


class TestGetExternalPluginsDir:
    def test_creates_directory(self, tmp_path):
        d = get_external_plugins_dir(tmp_path)
        assert d.exists()
        assert d.name == "external_plugins"
