"""Uninstall releases each actual plugin object's resources once."""

import json
import os
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from src import __version__
from src.config_manager import ConfigManager
from src.plugins.registry import PluginRegistry
from src.plugins.sources import get_external_plugins_dir


@contextmanager
def installed_plugin():
    with (
        tempfile.TemporaryDirectory() as directory,
        patch.dict(os.environ, {"FIESTABOARD_DATA_DIR": directory}),
        patch.object(ConfigManager, "_instance", None),
    ):
        root = Path(directory)
        builtins = root / "builtins"
        builtins.mkdir()
        config_path = root / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "app_version_seen": __version__,
                    "plugins": {
                        "qa_uninstall": {"enabled": True, "label": "BASE"},
                        "qa_uninstall:one": {"enabled": True, "label": "ONE"},
                        "qa_uninstall:two": {"enabled": False, "label": "TWO"},
                    },
                    "plugin_migrations": {"v2_completed": True},
                }
            )
        )
        manager = ConfigManager(str(config_path))
        code = get_external_plugins_dir() / "qa_uninstall"
        code.mkdir()
        (code / "manifest.json").write_text(
            json.dumps(
                {
                    "id": "qa_uninstall",
                    "name": "QA uninstall",
                    "version": "1.0.0",
                    "settings_schema": {
                        "type": "object",
                        "properties": {
                            "enabled": {"type": "boolean"},
                            "label": {"type": "string"},
                        },
                    },
                    "variables": {"simple": ["value"]},
                }
            )
        )
        (code / "__init__.py").write_text(
            "from src.plugins.base import PluginBase, PluginResult\n"
            "class Fixture(PluginBase):\n"
            "    def __init__(self, manifest):\n"
            "        super().__init__(manifest)\n"
            "        self.cleanup_calls = 0\n"
            "        self.raise_on_cleanup = False\n"
            "    @property\n"
            "    def plugin_id(self): return 'qa_uninstall'\n"
            "    def fetch_data(self): return PluginResult(available=True,data={'value':'WORKING'})\n"
            "    def cleanup(self):\n"
            "        self.cleanup_calls += 1\n"
            "        if self.raise_on_cleanup: raise RuntimeError('synthetic cleanup failure')\n"
        )
        registry = PluginRegistry(builtins)
        with patch.object(registry, "_auto_install_seeded_outputs", return_value=[]):
            registry.initialize()
        assert set(registry.plugins) == {"qa_uninstall", "qa_uninstall:one", "qa_uninstall:two"}
        yield manager, registry, code, config_path


@contextmanager
def join_cleanup_threads():
    """Keep actual async cleanup, but join test-owned threads before checking."""
    create_thread = threading.Thread
    workers = []

    def tracked_thread(*args, **kwargs):
        thread = create_thread(*args, **kwargs)
        workers.append(thread)
        return thread

    try:
        with patch("threading.Thread", tracked_thread):
            yield
    finally:
        for worker in workers:
            worker.join(3)
            if worker.is_alive():
                raise AssertionError("test cleanup thread did not finish")


class UninstallCleanupOwnership(unittest.TestCase):
    def test_base_and_named_instances_each_release_resources_once(self):
        with installed_plugin() as (manager, registry, code, config_path):
            original = registry.plugins
            with join_cleanup_threads():
                self.assertEqual(registry.uninstall_external_plugin("qa_uninstall"), [])
            for identity, plugin in original.items():
                with self.subTest(identity=identity):
                    self.assertEqual(plugin.cleanup_calls, 1)
            self.assertEqual(registry.plugins, {})
            self.assertFalse(code.exists())
            self.assertEqual(manager.get_all_plugin_configs(), {})
            self.assertTrue(manager.is_plugin_removed("qa_uninstall"))
            self.assertEqual(json.loads(config_path.read_text())["plugins"], {})
            with join_cleanup_threads():
                registry.uninstall_external_plugin("qa_uninstall")
            self.assertTrue(all(p.cleanup_calls == 1 for p in original.values()))

    def test_a_cleanup_error_is_not_retried_on_the_same_object(self):
        with installed_plugin() as (_, registry, _, _):
            original = registry.plugins
            original["qa_uninstall"].raise_on_cleanup = True
            with self.assertLogs("src.plugins.loader", level="ERROR"), join_cleanup_threads():
                self.assertEqual(registry.uninstall_external_plugin("qa_uninstall"), [])
            for identity, plugin in original.items():
                with self.subTest(identity=identity):
                    self.assertEqual(plugin.cleanup_calls, 1)

    def test_different_loader_and_registry_objects_are_both_retired(self):
        with installed_plugin() as (_, registry, _, _):
            loader_owned = registry.get_plugin("qa_uninstall")
            registry_owned = type(loader_owned)(loader_owned.manifest)
            registry._plugins["qa_uninstall"] = registry_owned
            with join_cleanup_threads():
                self.assertEqual(registry.uninstall_external_plugin("qa_uninstall"), [])
            self.assertEqual(loader_owned.cleanup_calls, 1)
            self.assertEqual(registry_owned.cleanup_calls, 1)

    def test_registry_owned_object_is_retired_when_loader_has_no_entry(self):
        with installed_plugin() as (_, registry, _, _):
            original = registry.plugins
            registry._loader._loaded_plugins.pop("qa_uninstall")
            with join_cleanup_threads():
                self.assertEqual(registry.uninstall_external_plugin("qa_uninstall"), [])
            self.assertTrue(all(p.cleanup_calls == 1 for p in original.values()))


if __name__ == "__main__":
    unittest.main()
