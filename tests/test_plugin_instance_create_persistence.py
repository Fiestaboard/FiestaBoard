"""Instance creation must publish only after its config can survive restart."""

import errno
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.config_manager import ConfigManager
from src.plugins.base import PluginBase, PluginResult
from src.plugins.errors import PluginOperationRejected
from src.plugins.registry import PluginRegistry
from src.plugins.service import PluginService


class LocalPlugin(PluginBase):
    @property
    def plugin_id(self):
        return self._manifest["id"]

    def fetch_data(self):
        return PluginResult(available=True, data={"value": self.config.get("value")})


class TestInstanceCreationPersistence(unittest.TestCase):
    @contextmanager
    def setup_plugins(self, stored=None, tombstone=False):
        with tempfile.TemporaryDirectory() as directory, patch.object(ConfigManager, "_instance", None):
            path = Path(directory) / "config.json"
            manager = ConfigManager(str(path))
            registry = PluginRegistry(Path(directory) / "plugins")
            base = LocalPlugin({"id": "probe"})
            registry._plugins["probe"] = base
            registry._manifests["probe"] = Mock()
            if stored is not None:
                manager.set_plugin_config("probe:home", stored)
            manager.set_plugin_config("other", {"enabled": True, "value": "unrelated"})
            if tombstone:
                manager.mark_plugin_removed("probe:home")
            made, resets = [], []

            def create(plugin_id):
                instance = LocalPlugin({"id": plugin_id})
                made.append(instance)
                return instance

            registry._loader.create_instance = Mock(side_effect=create)
            service = PluginService(
                registry=registry,
                config_manager=manager,
                reset_display=lambda: resets.append("display"),
                reset_template=lambda: resets.append("template"),
            )
            with patch("src.plugins.registry.retire_plugin_object") as retire:
                yield SimpleNamespace(
                    path=path,
                    manager=manager,
                    registry=registry,
                    service=service,
                    made=made,
                    resets=resets,
                    retire=retire,
                )

    def test_failed_fresh_creation_is_not_published_and_can_be_retried(self):
        with self.setup_plugins() as f:
            before = f.path.read_bytes()
            generation = f.manager.config_generation
            with patch("src.atomic_io.os.replace", side_effect=OSError(errno.ENOSPC, "synthetic disk full")):
                with self.assertRaises(OSError):
                    f.service.create_instance("probe", "HOME")
            self.assertIsNone(f.registry.get_plugin("probe:home"))
            self.assertEqual(f.path.read_bytes(), before)
            self.assertIsNone(f.manager.get_plugin_config("probe:home"))
            self.assertEqual(f.manager.config_generation, generation)
            self.assertEqual(f.resets, [])
            f.retire.assert_called_once()
            self.assertEqual(f.service.create_instance("probe", "HOME"), ("probe", "probe:home"))
            self.assertEqual(f.manager.config_generation, generation + 1)
            self.assertFalse(f.registry.is_enabled("probe:home"))
            self.assertEqual(f.manager.get_plugin_config("probe:home"), {"enabled": False})
            self.assertEqual(f.resets, ["display", "template"])

    def test_creation_and_tombstone_clear_are_one_durable_commit(self):
        from src.config_manager import write_json_atomic

        def reject_clear(path, data, **kwargs):
            if "probe:home" not in data.get("removed_plugins", []):
                with patch("src.atomic_io.os.replace", side_effect=OSError(errno.ENOSPC, "synthetic disk full")):
                    return write_json_atomic(path, data, **kwargs)
            return write_json_atomic(path, data, **kwargs)

        with self.setup_plugins(tombstone=True) as f:
            before = f.path.read_bytes()
            with patch("src.config_manager.write_json_atomic", side_effect=reject_clear):
                with self.assertRaises(OSError):
                    f.service.create_instance("probe", "home")
            self.assertEqual(f.path.read_bytes(), before)
            self.assertIsNone(f.registry.get_plugin("probe:home"))
            self.assertIn("probe:home", f.manager.get_removed_plugins())
            f.manager.set_plugin_config("unrelated", {"enabled": False})
            with patch.object(ConfigManager, "_instance", None):
                reloaded = ConfigManager(str(f.path))
                self.assertIsNone(reloaded.get_plugin_config("probe:home"))
                self.assertIn("probe:home", reloaded.get_removed_plugins())

    def test_failed_adoption_keeps_saved_config_and_successful_retry_adopts_it(self):
        from src.config_manager import write_json_atomic

        saved = {"enabled": True, "value": "saved-settings"}
        with self.setup_plugins(stored=saved, tombstone=True) as f:
            before = f.path.read_bytes()
            generation = f.manager.config_generation
            with patch("src.atomic_io.os.replace", side_effect=OSError(errno.ENOSPC, "synthetic disk full")):
                with self.assertRaises(OSError):
                    f.service.create_instance("probe", "home")
            self.assertIsNone(f.registry.get_plugin("probe:home"))
            self.assertEqual(f.path.read_bytes(), before)
            self.assertEqual(f.manager.get_plugin_config("probe:home"), saved)
            self.assertIn("probe:home", f.manager.get_removed_plugins())
            self.assertEqual(f.manager.config_generation, generation)
            with patch("src.config_manager.write_json_atomic", wraps=write_json_atomic) as writes:
                f.service.create_instance("probe", "home")
            self.assertEqual(writes.call_count, 1)
            self.assertEqual(f.manager.config_generation, generation + 1)
            self.assertTrue(f.registry.is_enabled("probe:home"))
            self.assertEqual(f.registry.get_plugin("probe:home").config, saved)
            self.assertEqual(json.loads(f.path.read_text())["plugins"]["probe:home"], saved)
            self.assertNotIn("probe:home", f.manager.get_removed_plugins())
            self.assertEqual(f.manager.get_plugin_config("other")["value"], "unrelated")

    def test_rejected_labels_duplicates_and_loader_failures_do_not_prepare_config(self):
        for reason in ("label", "duplicate", "loader"):
            with self.subTest(reason=reason), self.setup_plugins() as f:
                if reason == "duplicate":
                    f.service.create_instance("probe", "home")
                if reason == "loader":
                    f.registry._loader.create_instance.side_effect = None
                    f.registry._loader.create_instance.return_value = None
                before = f.path.read_bytes()
                generation = f.manager.config_generation
                resets = list(f.resets)
                with self.assertRaises(PluginOperationRejected):
                    f.service.create_instance("probe", "bad label" if reason == "label" else "home")
                self.assertEqual(f.path.read_bytes(), before)
                self.assertEqual(f.manager.config_generation, generation)
                self.assertEqual(f.resets, resets)
                f.retire.assert_not_called()

    def test_existing_saved_instance_without_tombstone_needs_no_rewrite(self):
        saved = {"enabled": True, "value": "existing"}
        with self.setup_plugins(stored=saved) as f:
            f.manager.mark_plugin_removed("probe:sibling")
            before = f.path.read_bytes()
            generation = f.manager.config_generation
            with patch("src.config_manager.write_json_atomic") as writes:
                f.service.create_instance("probe", "home")
            writes.assert_not_called()
            self.assertEqual(f.path.read_bytes(), before)
            self.assertEqual(f.manager.config_generation, generation)
            self.assertEqual(f.registry.get_plugin("probe:home").config, saved)
            self.assertTrue(f.registry.is_enabled("probe:home"))
            self.assertIn("probe:sibling", f.manager.get_removed_plugins())
