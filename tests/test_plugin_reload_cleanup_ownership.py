"""Reload must retire each real plugin object once, including failed loads."""

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
def loaded_plugin():
    with (
        tempfile.TemporaryDirectory() as directory,
        patch.dict(os.environ, {"FIESTABOARD_DATA_DIR": directory}),
        patch.object(ConfigManager, "_instance", None),
    ):
        root = Path(directory)
        builtin = root / "builtin"
        builtin.mkdir()
        config_path = root / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "app_version_seen": __version__,
                    "plugins": {
                        "qa_reload": {"enabled": True, "label": "BASE"},
                        "qa_reload:one": {"enabled": True, "label": "ONE"},
                        "qa_reload:two": {"enabled": False, "label": "TWO"},
                    },
                    "plugin_migrations": {"v2_completed": True},
                }
            )
        )
        manager = ConfigManager(str(config_path))
        code = get_external_plugins_dir() / "qa_reload"
        code.mkdir()
        (code / "manifest.json").write_text(
            json.dumps(
                {
                    "id": "qa_reload",
                    "name": "QA reload",
                    "version": "1.0.0",
                    "settings_schema": {"type": "object", "properties": {"label": {"type": "string"}}},
                    "variables": {"simple": ["value", "release"]},
                }
            )
        )
        source = (
            "import threading\n"
            "from src.plugins.base import PluginBase, PluginResult\n"
            "RELEASE = 'OLD'\n"
            "class Fixture(PluginBase):\n"
            "    def __init__(self, manifest):\n"
            "        super().__init__(manifest)\n"
            "        self.cleanup_calls = 0\n"
            "        self.cleanup_lock = threading.Lock()\n"
            "        self.raise_on_cleanup = False\n"
            "    @property\n"
            "    def plugin_id(self): return 'qa_reload'\n"
            "    def fetch_data(self):\n"
            "        return PluginResult(available=True, data={'value':self.config.get('label'), 'release':RELEASE})\n"
            "    def cleanup(self):\n"
            "        with self.cleanup_lock: self.cleanup_calls += 1\n"
            "        if self.raise_on_cleanup: raise RuntimeError('synthetic cleanup failure')\n"
        )
        (code / "__init__.py").write_text(source)
        registry = PluginRegistry(builtin)
        with patch.object(registry, "_auto_install_seeded_outputs", return_value=[]):
            registry.initialize()
        assert set(registry.plugins) == {"qa_reload", "qa_reload:one", "qa_reload:two"}
        yield manager, registry, code, config_path, source


@contextmanager
def joined_cleanup():
    """Observe actual daemon cleanup by joining only threads this test made."""
    constructor = threading.Thread
    threads = []

    def make(*args, **kwargs):
        thread = constructor(*args, **kwargs)
        threads.append(thread)
        return thread

    try:
        with patch("threading.Thread", make):
            yield
    finally:
        for thread in threads:
            thread.join(3)
            if thread.is_alive():
                raise AssertionError("test cleanup thread did not finish")


class ReloadCleanupOwnership(unittest.TestCase):
    def test_successful_reload_retires_each_old_object_once_and_preserves_state(self):
        with loaded_plugin() as (manager, registry, code, path, source):
            old = registry.plugins
            before = path.read_bytes()
            (code / "__init__.py").write_text(source.replace("'OLD'", "'NEW'"))
            with joined_cleanup():
                replacement = registry.reload_plugin("qa_reload")
            self.assertIsNotNone(replacement)
            self.assertIs(registry.get_plugin("qa_reload"), replacement)
            self.assertEqual(set(registry.plugins), set(old))
            for identity, plugin in old.items():
                with self.subTest(identity=identity):
                    self.assertEqual(plugin.cleanup_calls, 1)
                    fresh = registry.get_plugin(identity)
                    self.assertIsNot(fresh, plugin)
                    self.assertEqual(fresh.cleanup_calls, 0)
                    self.assertEqual(fresh.enabled, identity != "qa_reload:two")
                    self.assertEqual(fresh.fetch_data().data["release"], "NEW")
                    self.assertEqual(
                        fresh.config["label"],
                        {"qa_reload": "BASE", "qa_reload:one": "ONE", "qa_reload:two": "TWO"}[identity],
                    )
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(manager.get_all_plugin_configs()["qa_reload:one"]["label"], "ONE")

    def test_reload_does_not_retry_a_raising_cleanup_on_the_same_object(self):
        with loaded_plugin() as (_, registry, _, _, _):
            old = registry.plugins
            old["qa_reload"].raise_on_cleanup = True
            with self.assertLogs("src.plugins.loader", level="ERROR"), joined_cleanup():
                replacement = registry.reload_plugin("qa_reload")
            self.assertIsNotNone(replacement)
            self.assertEqual(old["qa_reload"].cleanup_calls, 1)
            self.assertTrue(all(plugin.cleanup_calls == 1 for plugin in old.values()))
            self.assertTrue(all(plugin.cleanup_calls == 0 for plugin in registry.plugins.values()))

    def test_failed_load_then_retry_does_not_retire_the_old_base_twice(self):
        with loaded_plugin() as (_, registry, code, path, source):
            old = registry.plugins
            before = path.read_bytes()
            (code / "__init__.py").write_text("raise ImportError('synthetic failed reload')\n")
            with joined_cleanup():
                self.assertIsNone(registry.reload_plugin("qa_reload"))
            self.assertIsNone(registry.get_plugin("qa_reload"))
            with self.subTest(phase="failed"):
                self.assertEqual(old["qa_reload"].cleanup_calls, 1)
            for identity in ("qa_reload:one", "qa_reload:two"):
                self.assertIs(registry.get_plugin(identity), old[identity])
                self.assertEqual(old[identity].cleanup_calls, 0)
            (code / "__init__.py").write_text(source.replace("'OLD'", "'RETRY'"))
            with joined_cleanup():
                self.assertIsNotNone(registry.reload_plugin("qa_reload"))
            with self.subTest(phase="retry"):
                self.assertEqual(old["qa_reload"].cleanup_calls, 1)
            for identity in ("qa_reload:one", "qa_reload:two"):
                self.assertEqual(old[identity].cleanup_calls, 1)
                self.assertEqual(registry.get_plugin(identity).fetch_data().data["release"], "RETRY")
            self.assertEqual(path.read_bytes(), before)

    def test_distinct_registry_and_loader_objects_are_both_retired_once(self):
        with loaded_plugin() as (_, registry, _, _, _):
            owned = registry.get_plugin("qa_reload")
            distinct = registry._loader.create_instance("qa_reload")
            self.assertIsNotNone(distinct)
            self.assertIsNot(distinct, owned)
            registry._plugins["qa_reload"] = distinct
            with joined_cleanup():
                self.assertIsNotNone(registry.reload_plugin("qa_reload"))
            self.assertEqual(owned.cleanup_calls, 1)
            self.assertEqual(distinct.cleanup_calls, 1)

    def test_registry_only_object_is_retired_when_loader_has_no_owner(self):
        with loaded_plugin() as (_, registry, _, _, _):
            old = registry.get_plugin("qa_reload")
            registry._loader._loaded_plugins.pop("qa_reload")
            with joined_cleanup():
                self.assertIsNotNone(registry.reload_plugin("qa_reload"))
            self.assertEqual(old.cleanup_calls, 1)

    def test_disable_enable_then_reload_keeps_both_distinct_cleanup_events(self):
        with loaded_plugin() as (_, registry, _, _, _):
            old = registry.get_plugin("qa_reload")
            self.assertTrue(registry.disable_plugin("qa_reload"))
            self.assertEqual(old.cleanup_calls, 1)
            self.assertTrue(registry.enable_plugin("qa_reload"))
            with joined_cleanup():
                self.assertIsNotNone(registry.reload_plugin("qa_reload"))
            self.assertEqual(old.cleanup_calls, 2)


if __name__ == "__main__":
    unittest.main()
