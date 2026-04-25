"""Tests for the external plugin sources module."""

import json
import subprocess
from unittest import mock


from src.plugins.sources import (
    PluginSource,
    RegistryEntry,
    check_plugin_update_available,
    clone_or_update_repo,
    get_external_plugins_dir,
    get_local_head_sha,
    get_remote_head_sha,
    install_git_plugin,
    install_registry_plugin,
    load_registry,
    plugin_id_from_repo_name,
    remove_external_plugin,
    repo_name_from_url,
    validate_registry_repo_name,
)
from src.plugins.loader import _check_version_constraint, _parse_version


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
            repo_name_from_url(
                "https://github.com/FiestaBoard/fiestaboard-plugin--foo.git"
            )
            == "fiestaboard-plugin--foo"
        )

    def test_repo_name_no_git_suffix(self):
        assert (
            repo_name_from_url(
                "https://github.com/FiestaBoard/fiestaboard-plugin--bar"
            )
            == "fiestaboard-plugin--bar"
        )

    def test_repo_name_trailing_slash(self):
        assert (
            repo_name_from_url(
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
        with mock.patch(
            "src.plugins.sources.get_external_plugins_dir", return_value=tmp_path
        ):
            ok, err = clone_or_update_repo("https://github.com/Org/repo", dest)
        assert ok
        assert err == ""
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "clone" in cmd

    @mock.patch("src.plugins.sources.subprocess.run")
    def test_fetch_reset_existing(self, mock_run, tmp_path):
        """Update path uses fetch+reset, not pull, and works without a URL."""
        dest = tmp_path / "my_plugin"
        dest.mkdir()
        (dest / ".git").mkdir()  # Simulate existing shallow clone
        with mock.patch(
            "src.plugins.sources.get_external_plugins_dir", return_value=tmp_path
        ):
            ok, err = clone_or_update_repo("", dest)
        assert ok
        assert err == ""
        # Two subprocess calls: fetch then reset
        assert mock_run.call_count == 2
        fetch_cmd = mock_run.call_args_list[0][0][0]
        reset_cmd = mock_run.call_args_list[1][0][0]
        assert "fetch" in fetch_cmd
        assert "--depth=1" in fetch_cmd
        assert "reset" in reset_cmd
        assert "FETCH_HEAD" in reset_cmd

    @mock.patch("src.plugins.sources.subprocess.run")
    def test_update_does_not_require_url(self, mock_run, tmp_path):
        """Passing an empty or invalid URL is fine when the clone already exists."""
        dest = tmp_path / "my_plugin"
        dest.mkdir()
        (dest / ".git").mkdir()
        with mock.patch(
            "src.plugins.sources.get_external_plugins_dir", return_value=tmp_path
        ):
            ok, err = clone_or_update_repo("git@github.com:Org/repo.git", dest)
        assert ok, "Update path should succeed regardless of URL"

    @mock.patch(
        "src.plugins.sources.subprocess.run",
        side_effect=subprocess.SubprocessError("network error"),
    )
    def test_clone_failure(self, mock_run, tmp_path):
        dest = tmp_path / "fail_plugin"
        with mock.patch(
            "src.plugins.sources.get_external_plugins_dir", return_value=tmp_path
        ):
            ok, err = clone_or_update_repo("https://github.com/Org/repo", dest)
        assert not ok
        assert "network error" in err

    @mock.patch(
        "src.plugins.sources.subprocess.run",
        side_effect=subprocess.SubprocessError("fetch failed"),
    )
    def test_update_failure(self, mock_run, tmp_path):
        """Fetch failure in the update path is surfaced as an error."""
        dest = tmp_path / "my_plugin"
        dest.mkdir()
        (dest / ".git").mkdir()
        with mock.patch(
            "src.plugins.sources.get_external_plugins_dir", return_value=tmp_path
        ):
            ok, err = clone_or_update_repo("", dest)
        assert not ok
        assert "fetch" in err.lower() or "failed" in err.lower()

    def test_rejects_ssh_url_for_fresh_clone(self, tmp_path):
        """SSH URLs are rejected only for fresh clones (URL validation skipped for updates)."""
        dest = tmp_path / "ssh_plugin"
        with mock.patch(
            "src.plugins.sources.get_external_plugins_dir", return_value=tmp_path
        ):
            ok, err = clone_or_update_repo("git@github.com:Org/repo.git", dest)
        assert not ok
        assert "HTTPS" in err

    def test_rejects_dest_outside_external_plugins_dir(self, tmp_path):
        """Destination outside the external plugins root is rejected."""
        external_root = tmp_path / "external_plugins"
        external_root.mkdir()
        outside_dest = tmp_path / "escape" / "my_plugin"
        with mock.patch(
            "src.plugins.sources.get_external_plugins_dir",
            return_value=external_root,
        ):
            ok, err = clone_or_update_repo(
                "https://github.com/Org/repo", outside_dest
            )
        assert not ok
        assert "outside external plugins dir" in err.lower()


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


# ── RegistryEntry fiestaboard_version ────────────────────────────────────────


class TestRegistryEntryVersionField:
    def test_from_dict_with_version(self):
        entry = RegistryEntry.from_dict({
            "id": "weather",
            "name": "Weather",
            "repository": "https://github.com/Fiestaboard/fiestaboard-plugin--weather",
            "fiestaboard_version": ">=2.10.0",
            "icon": "cloud-sun",
            "category": "weather",
        })
        assert entry.fiestaboard_version == ">=2.10.0"
        assert entry.icon == "cloud-sun"
        assert entry.category == "weather"

    def test_from_dict_without_version_defaults_empty(self):
        entry = RegistryEntry.from_dict({"id": "foo", "name": "Foo"})
        assert entry.fiestaboard_version == ""
        assert entry.icon == "puzzle"
        assert entry.category == "utility"


# ── Version constraint parsing & checking ────────────────────────────────────


class TestParseVersion:
    def test_standard_version(self):
        assert _parse_version("2.10.0") == (2, 10, 0)

    def test_leading_zeros_handled(self):
        assert _parse_version("1.0.0") == (1, 0, 0)

    def test_invalid_returns_zeros(self):
        assert _parse_version("not-a-version") == (0, 0, 0)

    def test_extracts_from_longer_string(self):
        assert _parse_version("2.10.0-beta") == (2, 10, 0)


class TestCheckVersionConstraint:
    def test_gte_satisfied(self):
        ok, _ = _check_version_constraint(">=2.10.0", "2.10.0")
        assert ok

    def test_gte_satisfied_higher(self):
        ok, _ = _check_version_constraint(">=2.10.0", "3.0.0")
        assert ok

    def test_gte_not_satisfied(self):
        ok, reason = _check_version_constraint(">=2.10.0", "2.9.0")
        assert not ok
        assert "2.9.0" in reason

    def test_gt_not_satisfied_equal(self):
        ok, _ = _check_version_constraint(">2.10.0", "2.10.0")
        assert not ok

    def test_lte_satisfied(self):
        ok, _ = _check_version_constraint("<=3.0.0", "2.10.0")
        assert ok

    def test_eq_satisfied(self):
        ok, _ = _check_version_constraint("==2.10.0", "2.10.0")
        assert ok

    def test_eq_not_satisfied(self):
        ok, _ = _check_version_constraint("==2.10.0", "2.9.0")
        assert not ok

    def test_neq_satisfied(self):
        ok, _ = _check_version_constraint("!=2.10.0", "2.9.0")
        assert ok

    def test_empty_constraint_always_passes(self):
        ok, _ = _check_version_constraint("", "2.10.0")
        assert ok

    def test_future_version_requirement(self):
        ok, reason = _check_version_constraint(">=99.0.0", "2.10.0")
        assert not ok
        assert "99.0.0" in reason

    def test_unrecognised_constraint_passes_with_warning(self):
        ok, reason = _check_version_constraint("~2.10.0", "2.10.0")
        assert ok  # Soft failure -- unrecognised but doesn't block load
        assert "Unrecognised" in reason


# ── Update checking helpers ───────────────────────────────────────────────────


class TestGetLocalHeadSha:
    def test_returns_none_for_missing_dir(self, tmp_path):
        assert get_local_head_sha(tmp_path / "nonexistent") is None

    def test_returns_none_for_non_git_dir(self, tmp_path):
        d = tmp_path / "not_git"
        d.mkdir()
        assert get_local_head_sha(d) is None

    @mock.patch("src.plugins.sources.subprocess.run")
    def test_returns_sha_for_valid_git_repo(self, mock_run, tmp_path):
        d = tmp_path / "plugin"
        d.mkdir()
        (d / ".git").mkdir()
        mock_run.return_value = mock.Mock(returncode=0, stdout="abc123\n")
        sha = get_local_head_sha(d)
        assert sha == "abc123"


class TestGetRemoteHeadSha:
    def test_returns_none_for_missing_dir(self, tmp_path):
        assert get_remote_head_sha(tmp_path / "nonexistent") is None

    def test_returns_none_for_non_git_dir(self, tmp_path):
        d = tmp_path / "not_git"
        d.mkdir()
        assert get_remote_head_sha(d) is None

    @mock.patch("src.plugins.sources.subprocess.run")
    def test_returns_sha_from_remote(self, mock_run, tmp_path):
        d = tmp_path / "plugin"
        d.mkdir()
        (d / ".git").mkdir()

        def side_effect(cmd, **kwargs):
            m = mock.Mock()
            if "remote" in cmd:
                m.returncode = 0
                m.stdout = "https://github.com/Org/repo\n"
            elif "rev-parse" in cmd:
                m.returncode = 0
                m.stdout = "main\n"
            elif "ls-remote" in cmd:
                m.returncode = 0
                m.stdout = "deadbeef\trefs/heads/main\n"
            return m

        mock_run.side_effect = side_effect
        sha = get_remote_head_sha(d)
        assert sha == "deadbeef"


class TestCheckPluginUpdateAvailable:
    @mock.patch("src.plugins.sources.get_local_head_sha", return_value="abc")
    @mock.patch("src.plugins.sources.get_remote_head_sha", return_value="abc")
    def test_no_update_when_shas_match(self, _remote, _local, tmp_path):
        d = tmp_path / "plugin"
        d.mkdir()
        assert not check_plugin_update_available(d)

    @mock.patch("src.plugins.sources.get_local_head_sha", return_value="abc")
    @mock.patch("src.plugins.sources.get_remote_head_sha", return_value="def")
    def test_update_available_when_shas_differ(self, _remote, _local, tmp_path):
        d = tmp_path / "plugin"
        d.mkdir()
        assert check_plugin_update_available(d)

    @mock.patch("src.plugins.sources.get_local_head_sha", return_value=None)
    @mock.patch("src.plugins.sources.get_remote_head_sha", return_value="def")
    def test_no_update_when_local_sha_missing(self, _remote, _local, tmp_path):
        d = tmp_path / "plugin"
        d.mkdir()
        assert not check_plugin_update_available(d)


class TestRegistryPluginDependencies:
    """Verify that Python packages required by registry plugins are importable.

    Registry plugins are external repos that are cloned at install time.
    Their Python dependencies must be present in requirements.txt so they
    are available in the Docker image.  If a dependency is missing the
    plugin loader will fail with an ImportError and the API will return
    a 400 response.
    """

    def test_calendar_sub_dependencies_available(self):
        """calendar_sub requires icalendar and recurring_ical_events (GH issue)."""
        import icalendar
        import recurring_ical_events

        assert icalendar is not None
        assert recurring_ical_events is not None
