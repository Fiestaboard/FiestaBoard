"""A rejected instance deletion must preserve live and durable state."""

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
        return PluginResult(available=True, data={"value": "working"})


class TestInstanceDeletionPersistence(unittest.TestCase):
    @contextmanager
    def setup_instance(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(ConfigManager, "_instance", None):
            path = Path(directory) / "config.json"
            manager = ConfigManager(str(path))
            registry = PluginRegistry(Path(directory) / "plugins")
            for identity in ("probe:home", "probe:other"):
                plugin = LocalPlugin({"id": identity})
                registry._plugins[identity] = plugin
                config = {"enabled": True, "value": identity}
                manager.set_plugin_config(identity, config)
                registry.set_plugin_config(identity, config)
                registry.enable_plugin(identity)
            resets = []
            service = PluginService(
                registry=registry,
                config_manager=manager,
                reset_display=lambda: resets.append("display"),
                reset_template=lambda: resets.append("template"),
            )
            with (
                patch("src.plugins.registry.retire_plugin_object") as retire,
                patch("src.oauth.service.get_oauth_service", return_value=Mock()) as oauth,
            ):
                yield SimpleNamespace(
                    path=path,
                    manager=manager,
                    registry=registry,
                    service=service,
                    instance=registry.get_plugin("probe:home"),
                    other=registry.get_plugin("probe:other"),
                    resets=resets,
                    retire=retire,
                    oauth=oauth.return_value,
                )

    def test_rejected_first_write_preserves_live_instance_and_lifecycle(self):
        with self.setup_instance() as f:
            before = f.path.read_bytes()
            generation = f.manager.config_generation
            with patch("src.atomic_io.os.replace", side_effect=OSError(errno.ENOSPC, "synthetic disk full")):
                with self.assertRaises(OSError):
                    f.service.delete_instance("probe", "home")
            self.assertEqual(f.path.read_bytes(), before)
            self.assertIs(f.registry.get_plugin("probe:home"), f.instance)
            self.assertTrue(f.registry.is_enabled("probe:home"))
            self.assertEqual(f.manager.get_plugin_config("probe:home")["value"], "probe:home")
            self.assertEqual(f.manager.config_generation, generation)
            f.retire.assert_not_called()
            f.oauth.forget.assert_not_called()
            self.assertEqual(f.resets, [])

    def test_tombstone_failure_does_not_commit_half_a_delete_or_leak_on_later_save(self):
        from src.config_manager import write_json_atomic

        def reject_tombstone(path, data, **kwargs):
            if "probe:home" in data.get("removed_plugins", []):
                with patch("src.atomic_io.os.replace", side_effect=OSError(errno.ENOSPC, "synthetic disk full")):
                    return write_json_atomic(path, data, **kwargs)
            return write_json_atomic(path, data, **kwargs)

        with self.setup_instance() as f:
            before = f.path.read_bytes()
            with patch("src.config_manager.write_json_atomic", side_effect=reject_tombstone):
                with self.assertRaises(OSError):
                    f.service.delete_instance("probe", "home")
            self.assertEqual(f.path.read_bytes(), before)
            self.assertIs(f.registry.get_plugin("probe:home"), f.instance)
            f.manager.set_plugin_config("unrelated", {"enabled": False})
            with patch.object(ConfigManager, "_instance", None):
                reloaded = ConfigManager(str(f.path))
                self.assertEqual(reloaded.get_plugin_config("probe:home")["value"], "probe:home")
                self.assertNotIn("probe:home", reloaded.get_removed_plugins())
            f.retire.assert_not_called()
            f.oauth.forget.assert_not_called()

    def test_retry_commits_config_removal_and_tombstone_once_before_retirement(self):
        from src.config_manager import write_json_atomic

        with self.setup_instance() as f:
            with patch("src.atomic_io.os.replace", side_effect=OSError(errno.ENOSPC, "synthetic disk full")):
                with self.assertRaises(OSError):
                    f.service.delete_instance("probe", "home")

            def retired(*args, **kwargs):
                stored = json.loads(f.path.read_text())
                self.assertNotIn("probe:home", stored["plugins"])
                self.assertIn("probe:home", stored["removed_plugins"])

            f.retire.side_effect = retired
            with patch("src.config_manager.write_json_atomic", wraps=write_json_atomic) as writes:
                self.assertEqual(f.service.delete_instance("probe", "HOME"), ("probe", "probe:home"))
            self.assertEqual(writes.call_count, 1)
            self.assertIsNone(f.registry.get_plugin("probe:home"))
            self.assertIs(f.registry.get_plugin("probe:other"), f.other)
            self.assertTrue(f.registry.is_enabled("probe:other"))
            self.assertEqual(f.manager.get_plugin_config("probe:other")["value"], "probe:other")
            f.retire.assert_called_once()
            f.oauth.forget.assert_called_once_with("probe:home")
            self.assertEqual(f.resets, ["display", "template"])

    def test_successful_delete_is_published_and_survives_unrelated_save_and_reload(self):
        with self.setup_instance() as f:
            generation = f.manager.config_generation
            f.service.delete_instance("probe", "home")
            with self.subTest(boundary="published configuration"):
                self.assertIsNone(f.manager.get_plugin_config("probe:home"))
                self.assertIn("probe:home", f.manager.get_removed_plugins())
            with self.subTest(boundary="published generation"):
                self.assertEqual(f.manager.config_generation, generation + 1)
            f.manager.set_plugin_config("unrelated", {"enabled": False})
            with patch.object(ConfigManager, "_instance", None):
                reloaded = ConfigManager(str(f.path))
                self.assertIsNot(reloaded, f.manager)
                with self.subTest(boundary="unrelated save and cold reload"):
                    self.assertIsNone(reloaded.get_plugin_config("probe:home"))
                    self.assertIn("probe:home", reloaded.get_removed_plugins())
                    self.assertEqual(reloaded.get_plugin_config("unrelated"), {"enabled": False})
                    self.assertEqual(reloaded.get_plugin_config("probe:other")["value"], "probe:other")

    def test_target_disappearing_before_registry_acceptance_does_not_persist_deletion(self):
        with self.setup_instance() as f:
            before = f.path.read_bytes()
            delete = f.registry.delete_instance

            def removed_before_acceptance(*args, **kwargs):
                with f.registry._lock:
                    f.registry._plugins.pop("probe:home")
                return delete(*args, **kwargs)

            with patch.object(f.registry, "delete_instance", side_effect=removed_before_acceptance):
                with self.assertRaises(PluginOperationRejected):
                    f.service.delete_instance("probe", "home")
            self.assertEqual(f.path.read_bytes(), before)
            self.assertNotIn("probe:home", f.manager.get_removed_plugins())
            f.retire.assert_not_called()
            f.oauth.forget.assert_not_called()
            self.assertEqual(f.resets, [])
