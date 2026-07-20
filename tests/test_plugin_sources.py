"""Tests for the external plugin sources module."""

import json
import subprocess
from pathlib import Path
from unittest import mock

from src.plugins.loader import _check_version_constraint, _parse_version
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
        ok, _ = validate_registry_repo_name("https://github.com/FiestaBoard/fiestaboard-plugin--weather")
        assert ok

    def test_valid_name_with_dashes(self):
        ok, _ = validate_registry_repo_name("https://github.com/FiestaBoard/fiestaboard-plugin--my-cool-plugin")
        assert ok

    def test_invalid_missing_prefix(self):
        ok, reason = validate_registry_repo_name("https://github.com/someone/my-plugin")
        assert not ok
        assert "fiestaboard-plugin--" in reason

    def test_invalid_uppercase(self):
        ok, _ = validate_registry_repo_name("https://github.com/FiestaBoard/Fiestaboard-plugin--Weather")
        assert not ok

    def test_repo_name_extraction(self):
        assert (
            repo_name_from_url("https://github.com/FiestaBoard/fiestaboard-plugin--foo.git")
            == "fiestaboard-plugin--foo"
        )

    def test_repo_name_no_git_suffix(self):
        assert repo_name_from_url("https://github.com/FiestaBoard/fiestaboard-plugin--bar") == "fiestaboard-plugin--bar"

    def test_repo_name_trailing_slash(self):
        assert (
            repo_name_from_url("https://github.com/FiestaBoard/fiestaboard-plugin--baz/") == "fiestaboard-plugin--baz"
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
        """Fresh install uses git init + config write + fetch + reset (no git clone)."""
        plugin_dest = tmp_path / "my_plugin"

        def _fake_run(cmd, **kwargs):
            if "init" in cmd:
                plugin_dest.mkdir(parents=True, exist_ok=True)
                (plugin_dest / ".git").mkdir(exist_ok=True)
            return mock.MagicMock()

        mock_run.side_effect = _fake_run
        ok, err = clone_or_update_repo("https://github.com/Org/repo", "my_plugin", external_dir=tmp_path)
        assert ok, f"expected ok but got err={err!r}"
        assert err == ""
        assert mock_run.call_count == 3  # git init, git fetch, git reset
        calls = [c[0][0] for c in mock_run.call_args_list]
        assert "init" in calls[0]
        assert "fetch" in calls[1]
        assert calls[1][-1] == "HEAD", "Fresh install without branch must fetch 'HEAD' explicitly"
        assert "reset" in calls[2]

    @mock.patch("src.plugins.sources.subprocess.run")
    def test_clone_fresh_with_explicit_branch(self, mock_run, tmp_path):
        """Fresh install with an explicit branch fetches that branch, not HEAD."""
        plugin_dest = tmp_path / "my_plugin"

        def _fake_run(cmd, **kwargs):
            if "init" in cmd:
                plugin_dest.mkdir(parents=True, exist_ok=True)
                (plugin_dest / ".git").mkdir(exist_ok=True)
            return mock.MagicMock()

        mock_run.side_effect = _fake_run
        ok, err = clone_or_update_repo(
            "https://github.com/Org/repo", "my_plugin", branch="develop", external_dir=tmp_path
        )
        assert ok, f"expected ok but got err={err!r}"
        fetch_cmd = mock_run.call_args_list[1][0][0]
        assert "fetch" in fetch_cmd
        assert fetch_cmd[-1] == "develop", "Explicit branch should be the final fetch argument"

    @mock.patch("src.plugins.sources.subprocess.run")
    def test_fetch_reset_existing(self, mock_run, tmp_path):
        """Update path uses fetch+reset, not pull, and works without a URL."""
        dest = tmp_path / "my_plugin"
        dest.mkdir()
        (dest / ".git").mkdir()  # Simulate existing shallow clone
        ok, err = clone_or_update_repo("", "my_plugin", external_dir=tmp_path)
        assert ok
        assert err == ""
        # Two subprocess calls: fetch then reset
        assert mock_run.call_count == 2
        fetch_cmd = mock_run.call_args_list[0][0][0]
        reset_cmd = mock_run.call_args_list[1][0][0]
        assert "fetch" in fetch_cmd
        assert "--depth=1" in fetch_cmd
        # Must fetch "HEAD" explicitly so repos with multiple branches (e.g.
        # gh-pages) don't leave FETCH_HEAD pointing at a non-default branch,
        # which would cause every subsequent update-check to see a SHA mismatch.
        assert fetch_cmd[-1] == "HEAD", "Update path must fetch 'origin HEAD', not bare 'origin'"
        assert "reset" in reset_cmd
        assert "FETCH_HEAD" in reset_cmd

    @mock.patch("src.plugins.sources.subprocess.run")
    def test_update_does_not_require_url(self, mock_run, tmp_path):
        """Passing an empty or invalid URL is fine when the clone already exists."""
        dest = tmp_path / "my_plugin"
        dest.mkdir()
        (dest / ".git").mkdir()
        ok, _err = clone_or_update_repo("git@github.com:Org/repo.git", "my_plugin", external_dir=tmp_path)
        assert ok, "Update path should succeed regardless of URL"

    @mock.patch(
        "src.plugins.sources.subprocess.run",
        side_effect=subprocess.SubprocessError("network error"),
    )
    def test_clone_failure(self, mock_run, tmp_path):
        """Subprocess failure during fresh install surfaces as an error."""
        ok, err = clone_or_update_repo("https://github.com/Org/repo", "fail_plugin", external_dir=tmp_path)
        assert not ok
        # git init raises SubprocessError; caught and wrapped as "git clone failed: ..."
        assert "clone" in err and "failed" in err

    @mock.patch(
        "src.plugins.sources.subprocess.run",
        side_effect=subprocess.SubprocessError("fetch failed"),
    )
    def test_update_failure(self, mock_run, tmp_path):
        """Fetch failure in the update path is surfaced as an error."""
        dest = tmp_path / "my_plugin"
        dest.mkdir()
        (dest / ".git").mkdir()
        ok, err = clone_or_update_repo("", "my_plugin", external_dir=tmp_path)
        assert not ok
        assert "fetch" in err.lower() or "failed" in err.lower()

    def test_rejects_ssh_url_for_fresh_clone(self, tmp_path):
        """SSH URLs are rejected only for fresh clones (URL validation skipped for updates)."""
        ok, err = clone_or_update_repo("git@github.com:Org/repo.git", "ssh_plugin", external_dir=tmp_path)
        assert not ok
        assert "HTTPS" in err

    @mock.patch("src.plugins.sources.subprocess.run")
    def test_rejects_invalid_plugin_id(self, mock_run, tmp_path):
        """A plugin_id with path separators or invalid characters is rejected."""
        ok, _err = clone_or_update_repo("https://github.com/Org/repo", "../escaped", external_dir=tmp_path)
        assert not ok
        mock_run.assert_not_called()

    @mock.patch("src.plugins.sources.subprocess.run")
    def test_rejects_path_traversal_via_plugin_id(self, mock_run, tmp_path):
        """A plugin_id that would escape via '..' is caught by _safe_external_dest."""
        ext_dir = tmp_path / "external_plugins"
        ext_dir.mkdir()
        ok, _err = clone_or_update_repo("https://github.com/Org/repo", "../../escaped", external_dir=ext_dir)
        assert not ok
        mock_run.assert_not_called()


class TestCloneOrUpdateRepoPathSafety:
    """Verify the path-containment check in clone_or_update_repo via plugin_id."""

    def test_rejects_invalid_plugin_id_characters(self):
        """Plugin ids with path separators or shell chars are rejected."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            from pathlib import Path

            ext_dir = Path(tmp) / "external_plugins"
            ext_dir.mkdir()
            ok, _err = clone_or_update_repo("https://github.com/Org/repo", "../../etc/passwd", external_dir=ext_dir)
            assert not ok

    def test_accepts_valid_plugin_id(self, tmp_path):
        """A valid plugin_id is accepted and the path is computed correctly."""
        allowed_root = tmp_path / "external_plugins"
        allowed_root.mkdir()
        plugin_dest = allowed_root / "my_plugin"

        def _fake_run(cmd, **kwargs):
            if "init" in cmd:
                plugin_dest.mkdir(parents=True, exist_ok=True)
                (plugin_dest / ".git").mkdir(exist_ok=True)
            return mock.MagicMock()

        with mock.patch("src.plugins.sources.subprocess.run", side_effect=_fake_run):
            ok, err = clone_or_update_repo("https://github.com/Org/repo", "my_plugin", external_dir=allowed_root)
        assert ok
        assert err == ""

    def test_rejects_symlinked_external_dir_escape(self, tmp_path):
        """Path containment uses ``Path.resolve()`` so symlink escapes are caught.

        Mitigation for CodeQL ``py/path-injection``: even if the resolved
        external dir is itself a symlink, the candidate must remain inside
        its real target.
        """
        real_root = tmp_path / "real_plugins"
        real_root.mkdir()
        link_root = tmp_path / "linked_plugins"
        link_root.symlink_to(real_root)

        # Valid plugin_id under the symlinked root resolves into real_plugins.
        # That's allowed.
        plugin_dest = real_root / "ok_plugin"

        def _fake_run(cmd, **kwargs):
            if "init" in cmd:
                plugin_dest.mkdir(parents=True, exist_ok=True)
                (plugin_dest / ".git").mkdir(exist_ok=True)
            return mock.MagicMock()

        with mock.patch("src.plugins.sources.subprocess.run", side_effect=_fake_run):
            ok, err = clone_or_update_repo("https://github.com/Org/repo", "ok_plugin", external_dir=link_root)
        assert ok, err

    def test_rejects_root_as_candidate(self, tmp_path):
        """If plugin_id resolves to the external root itself, refuse — avoids
        wiping the entire external_plugins directory on rmtree."""
        from src.plugins.sources import _PLUGIN_ID_ALLOWED, PLUGIN_ID_RE

        # We can't easily trigger this via a normal plugin_id (it always
        # appends a subdir), so just sanity-check the regex/character set
        # are still in effect (the empty-id case is rejected upstream).
        assert not PLUGIN_ID_RE.fullmatch("")
        assert "/" not in _PLUGIN_ID_ALLOWED
        assert "." not in _PLUGIN_ID_ALLOWED


class TestCloneOrUpdateRepoErrorMessages:
    """Stderr from CalledProcessError should appear in the returned error string."""

    @mock.patch("src.plugins.sources.subprocess.run")
    def test_fresh_clone_includes_stderr(self, mock_run, tmp_path):
        exc = subprocess.CalledProcessError(128, ["git", "fetch"])
        exc.stderr = "fatal: repository 'https://github.com/x/y' not found"
        mock_run.side_effect = exc
        ok, err = clone_or_update_repo("https://github.com/x/y", "my_plugin", external_dir=tmp_path)
        assert not ok
        assert "not found" in err

    @mock.patch("src.plugins.sources.subprocess.run")
    def test_update_includes_stderr(self, mock_run, tmp_path):
        dest = tmp_path / "my_plugin"
        dest.mkdir()
        (dest / ".git").mkdir()
        exc = subprocess.CalledProcessError(128, ["git", "fetch"])
        exc.stderr = "fatal: unable to access"
        mock_run.side_effect = exc
        ok, err = clone_or_update_repo("", "my_plugin", external_dir=tmp_path)
        assert not ok
        assert "unable to access" in err

    @mock.patch("src.plugins.sources.subprocess.run")
    def test_empty_stderr_falls_back_to_exc_str(self, mock_run, tmp_path):
        exc = subprocess.CalledProcessError(128, ["git", "fetch"])
        exc.stderr = ""
        mock_run.side_effect = exc
        ok, err = clone_or_update_repo("https://github.com/x/y", "my_plugin", external_dir=tmp_path)
        assert not ok
        assert "clone" in err and "failed" in err


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
        ok, _err = install_git_plugin(
            "https://github.com/someone/repo",
            plugin_id="custom_id",
            external_dir=tmp_path,
        )
        assert ok
        # Check that the plugin_id used is the override id
        plugin_id_arg = mock_clone.call_args[0][1]
        assert plugin_id_arg == "custom_id"


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
        entry = RegistryEntry.from_dict(
            {
                "id": "weather",
                "name": "Weather",
                "repository": "https://github.com/Fiestaboard/fiestaboard-plugin--weather",
                "fiestaboard_version": ">=2.10.0",
                "icon": "cloud-sun",
                "category": "weather",
            }
        )
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

    @mock.patch("src.plugins.sources.subprocess.run")
    def test_falls_back_to_remote_head_on_branch_mismatch(self, mock_run, tmp_path):
        """When local branch (e.g. 'master') doesn't exist on remote (e.g. 'main'),
        fall back to querying remote HEAD so updates are still detected."""
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
                m.stdout = "master\n"  # local branch is "master"
            elif "ls-remote" in cmd and "--heads" in cmd:
                # remote has no "master" branch
                m.returncode = 0
                m.stdout = ""
            elif "ls-remote" in cmd:
                # fallback: remote HEAD
                m.returncode = 0
                m.stdout = "deadbeef\tHEAD\n"
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


# ── External plugins dir: data-volume location + legacy migration ────────────


class TestExternalPluginsDirUnderData:
    """The clone cache must live inside the persistent ``data/`` volume.

    ``data/`` is the mount every deployment persists (it holds config.json).
    The old ``<root>/external_plugins`` location only survived upgrades when
    the user's compose file had a second bind mount for it — boards without
    that mount lost all plugin code on every container recreate and re-cloned
    everything from GitHub on the next boot.
    """

    def test_dir_lives_under_data(self, tmp_path):
        result = get_external_plugins_dir(project_root=tmp_path)
        assert result == tmp_path / "data" / "external_plugins"
        assert result.is_dir()

    def test_legacy_plugins_migrate_to_data_dir(self, tmp_path):
        legacy_plugin = tmp_path / "external_plugins" / "weather"
        (legacy_plugin / ".git").mkdir(parents=True)
        (legacy_plugin / "manifest.json").write_text('{"id": "weather"}')

        get_external_plugins_dir(project_root=tmp_path)

        migrated = tmp_path / "data" / "external_plugins" / "weather"
        assert migrated.joinpath("manifest.json").read_text() == '{"id": "weather"}'
        # .git must come along or the update path (fetch/reset) breaks
        assert migrated.joinpath(".git").is_dir()

    def test_migration_does_not_overwrite_existing_plugin(self, tmp_path):
        legacy_plugin = tmp_path / "external_plugins" / "weather"
        legacy_plugin.mkdir(parents=True)
        (legacy_plugin / "manifest.json").write_text("stale-legacy-copy")
        new_plugin = tmp_path / "data" / "external_plugins" / "weather"
        new_plugin.mkdir(parents=True)
        (new_plugin / "manifest.json").write_text("current")

        get_external_plugins_dir(project_root=tmp_path)

        assert (new_plugin / "manifest.json").read_text() == "current"

    def test_migration_runs_only_once(self, tmp_path):
        """A plugin uninstalled after migration must not be resurrected from
        the legacy directory on a later call (the #937 invariant)."""
        import shutil

        legacy_plugin = tmp_path / "external_plugins" / "weather"
        legacy_plugin.mkdir(parents=True)
        (legacy_plugin / "manifest.json").write_text("x")

        migrated = tmp_path / "data" / "external_plugins" / "weather"
        get_external_plugins_dir(project_root=tmp_path)
        assert migrated.is_dir()

        shutil.rmtree(migrated)  # deliberate uninstall

        get_external_plugins_dir(project_root=tmp_path)
        assert not migrated.exists()

    def test_no_legacy_dir_is_fine(self, tmp_path):
        result = get_external_plugins_dir(project_root=tmp_path)
        assert result.is_dir()

    def test_migration_ignores_stray_files(self, tmp_path):
        legacy = tmp_path / "external_plugins"
        legacy.mkdir()
        (legacy / "stray.txt").write_text("junk")

        result = get_external_plugins_dir(project_root=tmp_path)

        assert not (result / "stray.txt").exists()

    def test_crashed_migration_attempt_is_cleaned_and_retried(self, tmp_path):
        """A temp dir left by a crash mid-copy must be removed and the plugin
        migrated fresh — never half-migrated, never treated as done."""
        legacy_plugin = tmp_path / "external_plugins" / "weather"
        legacy_plugin.mkdir(parents=True)
        (legacy_plugin / "manifest.json").write_text("complete")

        stale_tmp = tmp_path / "data" / "external_plugins" / ".weather.fbmigrate-tmp"
        stale_tmp.mkdir(parents=True)
        (stale_tmp / "manifest.json").write_text("partial")

        result = get_external_plugins_dir(project_root=tmp_path)

        assert not stale_tmp.exists()
        assert (result / "weather" / "manifest.json").read_text() == "complete"

    def test_failed_copy_leaves_no_partial_target(self, tmp_path, monkeypatch):
        """If the copy dies partway (disk full, I/O error), the destination
        must not contain a partial plugin dir that later boots would skip as
        'already migrated'."""
        import shutil as _shutil

        legacy_plugin = tmp_path / "external_plugins" / "weather"
        legacy_plugin.mkdir(parents=True)
        (legacy_plugin / "manifest.json").write_text("x")

        def exploding_copytree(src, dst, **kwargs):
            Path(dst).mkdir(parents=True, exist_ok=True)  # partial work
            raise OSError("disk full")

        monkeypatch.setattr(_shutil, "copytree", exploding_copytree)
        result = get_external_plugins_dir(project_root=tmp_path)

        assert not (result / "weather").exists()
        # legacy source untouched — retried after the transient error clears
        assert (legacy_plugin / "manifest.json").exists()
