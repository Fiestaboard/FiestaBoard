"""Tests for the install-time gate in src/plugins/sources.py.

Policy under test:
  * a FRESH install that cannot work is rejected and cleaned up
  * an UPDATE that breaks an already-installed plugin is left in place and
    reported, because removing a plugin that may be driving a board is worse
"""

import json
from pathlib import Path
from unittest.mock import patch

from src.plugins import sources


def write_plugin(plugin_dir: Path, *, data_files=None, ships=None, requirements=None):
    """Materialise a plugin directory as a clone would leave it."""
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "__init__.py").write_text("class Plugin:\n    pass\n")
    manifest = {"id": plugin_dir.name, "name": plugin_dir.name, "version": "1.0.0"}
    if data_files is not None:
        manifest["data_files"] = data_files
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest))
    for name, content in (ships or {}).items():
        (plugin_dir / name).write_text(content)
    if requirements:
        (plugin_dir / "requirements.txt").write_text(requirements)


class TestVerifyInstalledPlugin:
    def test_rejects_a_plugin_missing_its_declared_data(self, tmp_path):
        plugin_dir = tmp_path / "star_trek_quotes"
        write_plugin(plugin_dir, data_files=["quotes.json"])
        ok, reason = sources.verify_installed_plugin("star_trek_quotes", plugin_dir)
        assert ok is False
        assert "quotes.json" in reason

    def test_accepts_the_same_plugin_once_it_ships_the_file(self, tmp_path):
        plugin_dir = tmp_path / "star_trek_quotes"
        write_plugin(plugin_dir, data_files=["quotes.json"], ships={"quotes.json": "{}"})
        ok, reason = sources.verify_installed_plugin("star_trek_quotes", plugin_dir)
        assert ok is True, reason

    def test_rejects_a_plugin_needing_an_absent_package(self, tmp_path):
        plugin_dir = tmp_path / "volcano"
        write_plugin(plugin_dir, requirements="definitely-not-a-real-package\n")
        ok, reason = sources.verify_installed_plugin("volcano", plugin_dir)
        assert ok is False
        assert "definitely-not-a-real-package" in reason

    def test_rejects_an_unreadable_manifest(self, tmp_path):
        plugin_dir = tmp_path / "broken"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("")
        (plugin_dir / "manifest.json").write_text("{ not json")
        ok, _reason = sources.verify_installed_plugin("broken", plugin_dir)
        assert ok is False

    def test_a_warning_alone_does_not_reject(self, tmp_path):
        """No data_files declaration warns, but must still install."""
        plugin_dir = tmp_path / "weather"
        write_plugin(plugin_dir)
        ok, reason = sources.verify_installed_plugin("weather", plugin_dir)
        assert ok is True, reason


class TestFreshInstallIsBlocked:
    def test_broken_fresh_install_is_rejected_and_removed(self, tmp_path):
        external = tmp_path / "external"
        external.mkdir()

        def fake_clone(repo_url, plugin_id, branch, external_dir):
            write_plugin(external_dir / plugin_id, data_files=["quotes.json"])
            return True, ""

        with patch.object(sources, "clone_or_update_repo", side_effect=fake_clone):
            ok, err = sources._install_and_verify("https://x/y", "star_trek_quotes", "", external)

        assert ok is False
        assert "was not installed" in err
        assert "quotes.json" in err
        assert not (external / "star_trek_quotes").exists(), "broken clone must be cleaned up"

    def test_healthy_fresh_install_succeeds_and_remains(self, tmp_path):
        external = tmp_path / "external"
        external.mkdir()

        def fake_clone(repo_url, plugin_id, branch, external_dir):
            write_plugin(external_dir / plugin_id, data_files=["quotes.json"], ships={"quotes.json": "{}"})
            return True, ""

        with patch.object(sources, "clone_or_update_repo", side_effect=fake_clone):
            ok, err = sources._install_and_verify("https://x/y", "star_trek_quotes", "", external)

        assert ok is True, err
        assert (external / "star_trek_quotes" / "quotes.json").exists()

    def test_a_clone_failure_is_returned_unchanged(self, tmp_path):
        external = tmp_path / "external"
        external.mkdir()
        with patch.object(sources, "clone_or_update_repo", return_value=(False, "network down")):
            ok, err = sources._install_and_verify("https://x/y", "p", "", external)
        assert ok is False
        assert err == "network down"


class TestUpdateIsNotBlocked:
    def test_update_that_breaks_a_plugin_leaves_it_installed(self, tmp_path):
        """An installed plugin may be driving a board; do not tear it out."""
        external = tmp_path / "external"
        external.mkdir()
        # Already installed and healthy.
        write_plugin(external / "star_trek_quotes", data_files=["quotes.json"], ships={"quotes.json": "{}"})

        def fake_clone_drops_the_file(repo_url, plugin_id, branch, external_dir):
            (external_dir / plugin_id / "quotes.json").unlink()
            return True, ""

        with patch.object(sources, "clone_or_update_repo", side_effect=fake_clone_drops_the_file):
            ok, err = sources._install_and_verify("https://x/y", "star_trek_quotes", "", external)

        assert ok is True, "an update must not fail the caller"
        assert err == ""
        assert (external / "star_trek_quotes").exists(), "must not be removed"

    def test_the_broken_update_is_logged_as_an_error(self, tmp_path, caplog):
        external = tmp_path / "external"
        external.mkdir()
        write_plugin(external / "p", data_files=["d.json"], ships={"d.json": "{}"})

        def fake_clone(repo_url, plugin_id, branch, external_dir):
            (external_dir / plugin_id / "d.json").unlink()
            return True, ""

        with (
            patch.object(sources, "clone_or_update_repo", side_effect=fake_clone),
            caplog.at_level("ERROR"),
        ):
            sources._install_and_verify("https://x/y", "p", "", external)

        assert any("left installed" in r.message or "left installed" in r.getMessage() for r in caplog.records)
