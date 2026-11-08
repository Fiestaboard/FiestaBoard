"""A rejected config write must not reconfigure a running data plugin."""

import errno
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.config_manager import ConfigManager
from src.plugins.base import PluginBase, PluginResult
from src.plugins.errors import PluginConfigInvalid
from src.plugins.registry import PluginRegistry
from src.plugins.service import PluginService


class LocalPlugin(PluginBase):
    def __init__(self, path):
        super().__init__({"id": "probe", "settings_schema": {"properties": {}}})
        self.path = path
        self.changes = []

    @property
    def plugin_id(self):
        return "probe"

    def fetch_data(self):
        return PluginResult(available=True, data={"value": self.config.get("value")})

    def validate_config(self, config):
        return ["value is invalid"] if config.get("value") == "invalid" else []

    def on_config_change(self, old_config, new_config):
        persisted = json.loads(self.path.read_text())["plugins"]["probe"]
        self.changes.append((dict(new_config), persisted))


class TestPluginConfigPersistence(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "config.json"
        singleton = patch.object(ConfigManager, "_instance", None)
        singleton.start()
        self.addCleanup(singleton.stop)
        self.manager = ConfigManager(str(self.path))
        self.old = {"value": "original", "enabled": True}
        self.manager.set_plugin_config("probe", dict(self.old))
        self.registry = PluginRegistry(Path(self.directory.name) / "plugins")
        self.plugin = LocalPlugin(self.path)
        self.registry._plugins["probe"] = self.plugin
        self.registry.set_plugin_config("probe", dict(self.old))
        self.plugin.changes.clear()
        self.resets = []
        self.service = PluginService(
            registry=self.registry,
            config_manager=self.manager,
            reset_display=lambda: self.resets.append("display"),
            reset_template=lambda: self.resets.append("template"),
        )

    def test_failed_write_preserves_live_plugin_and_does_not_run_callbacks(self):
        before = self.path.read_bytes()
        with patch("src.atomic_io.os.replace", side_effect=OSError(errno.ENOSPC, "synthetic disk full")):
            with self.assertRaises(OSError):
                self.service.update_plugin_config("probe", {"value": "rejected", "enabled": True})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.plugin.fetch_data().data, {"value": "original"})
        self.assertEqual(self.registry.get_plugin_config("probe"), self.old)
        self.assertEqual(self.plugin.changes, [])
        self.assertEqual(self.resets, [])

    def test_failed_write_is_not_persisted_by_a_later_unrelated_save(self):
        generation = self.manager.config_generation
        with patch("src.atomic_io.os.replace", side_effect=OSError(errno.ENOSPC, "synthetic disk full")):
            with self.assertRaises(OSError):
                self.manager.set_plugin_config("probe", {"value": "rejected"})
        self.assertEqual(self.manager.config_generation, generation)
        self.assertEqual(self.manager.get_plugin_config("probe", include_env_overrides=False), self.old)
        self.manager.set_plugin_config("unrelated", {"enabled": False})
        self.assertEqual(self.manager.config_generation, generation + 1)
        self.assertEqual(json.loads(self.path.read_text())["plugins"]["probe"], self.old)

    def test_successful_retry_persists_before_callback_and_resets_runtime(self):
        with patch("src.atomic_io.os.replace", side_effect=OSError(errno.ENOSPC, "synthetic disk full")):
            with self.assertRaises(OSError):
                self.service.update_plugin_config("probe", {"value": "new", "enabled": True})
        self.plugin.changes.clear()
        expected = {"value": "new", "enabled": True}
        self.service.update_plugin_config("probe", dict(expected))
        self.assertEqual(self.plugin.changes, [(expected, expected)])
        self.assertEqual(self.plugin.fetch_data().data, {"value": "new"})
        self.assertEqual(self.resets, ["display", "template"])

    def test_invalid_config_does_not_write_or_apply(self):
        before = self.path.read_bytes()
        with self.assertRaises(PluginConfigInvalid):
            self.service.update_plugin_config("probe", {"value": "invalid"})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.plugin.fetch_data().data, {"value": "original"})
        self.assertEqual(self.plugin.changes, [])
        self.assertEqual(self.resets, [])

    def test_environment_overlay_is_live_only_and_masked_secret_comes_from_storage(self):
        stored = {"value": "original", "api_key": "synthetic-stored"}
        self.manager.set_plugin_config("probe", dict(stored))
        self.registry.set_plugin_config("probe", dict(stored))
        with (
            patch.dict("src.config_manager.ENV_PLUGIN_OVERRIDES", {"QA_PROBE_KEY": ("probe", "api_key", str)}),
            patch.dict(os.environ, {"QA_PROBE_KEY": "synthetic-environment"}),
        ):
            self.service.update_plugin_config("probe", {"value": "new", "api_key": "***"})
        self.assertEqual(json.loads(self.path.read_text())["plugins"]["probe"]["api_key"], "synthetic-stored")
        self.assertEqual(self.plugin.config["api_key"], "synthetic-environment")
        self.assertEqual(self.plugin.config["value"], "new")

    def test_committed_config_is_applied_when_validation_changes_after_commit(self):
        expected = {"value": "new"}

        def changed_validation(config):
            return ["validation changed"] if json.loads(self.path.read_text())["plugins"]["probe"] == expected else []

        with patch.object(self.plugin, "validate_config", side_effect=changed_validation):
            self.service.update_plugin_config("probe", dict(expected))
        self.assertEqual(self.plugin.config, expected)
        self.assertEqual(self.plugin.changes, [(expected, expected)])
        self.assertEqual(self.resets, ["display", "template"])
