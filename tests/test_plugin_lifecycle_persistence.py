"""Rejected enable/disable writes must not change running data plugins."""

import errno
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from src.atomic_io import write_json_atomic
from src.config_manager import ConfigManager
from src.plugins.base import PluginBase, PluginResult
from src.plugins.errors import PluginOperationRejected
from src.plugins.registry import PluginRegistry
from src.plugins.service import PluginService


class LocalPlugin(PluginBase):
    def __init__(self, plugin_id, path):
        self.identity = plugin_id
        super().__init__({"id": plugin_id, "settings_schema": {"properties": {}}})
        self.path = path
        self.transitions = []
        self.cleanups = 0

    @property
    def plugin_id(self):
        return self.identity

    @property
    def enabled(self):
        return PluginBase.enabled.fget(self)

    @enabled.setter
    def enabled(self, value):
        before = self.enabled
        PluginBase.enabled.fset(self, value)
        if before != value:
            stored = json.loads(self.path.read_text())["plugins"][self.plugin_id]["enabled"]
            self.transitions.append((value, stored))

    def cleanup(self):
        self.cleanups += 1

    def fetch_data(self):
        return PluginResult(available=True, data={"value": "synthetic"})


class TestPluginLifecyclePersistence(unittest.TestCase):
    @contextmanager
    def setup_plugins(self, enabled):
        with tempfile.TemporaryDirectory() as directory, patch.object(ConfigManager, "_instance", None):
            path = Path(directory) / "config.json"
            manager = ConfigManager(str(path))
            registry = PluginRegistry(Path(directory) / "plugins")
            for identity, initial in (("probe", enabled), ("other", False)):
                manager.set_plugin_config(identity, {"enabled": initial, "api_key": "synthetic-secret"})
                plugin = LocalPlugin(identity, path)
                registry._plugins[identity] = plugin
                registry.set_plugin_config(identity, manager.get_plugin_config(identity))
                if initial:
                    registry.enable_plugin(identity)
                plugin.transitions.clear()
                plugin.cleanups = 0
            resets = []
            service = PluginService(
                registry=registry,
                config_manager=manager,
                reset_display=lambda: resets.append("display"),
                reset_template=lambda: resets.append("template"),
            )
            yield path, manager, registry, service, resets

    @contextmanager
    def failed_save(self):
        with patch("src.atomic_io.os.replace", side_effect=OSError(errno.ENOSPC, "synthetic disk full")):
            with self.assertRaises(OSError):
                yield

    def test_failed_enable_or_disable_preserves_live_state_and_callbacks(self):
        for method, initial in (("enable_plugin", False), ("disable_plugin", True)):
            with self.subTest(method=method), self.setup_plugins(initial) as (path, manager, registry, service, resets):
                before = path.read_bytes()
                with self.failed_save():
                    getattr(service, method)("probe")
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(registry.is_enabled("probe"), initial)
                self.assertEqual(registry.get_plugin("probe").enabled, initial)
                self.assertEqual(registry.get_plugin("probe").transitions, [])
                self.assertEqual(registry.get_plugin("probe").cleanups, 0)
                self.assertEqual(resets, [])
                self.assertFalse(registry.is_enabled("other"))
                self.assertEqual(registry.get_plugin("other").transitions, [])

    def test_failed_flag_write_preserves_config_and_generation(self):
        for method, initial in (("enable_plugin", False), ("disable_plugin", True)):
            with self.subTest(method=method), self.setup_plugins(initial) as (_, manager, _, _, _):
                generation = manager.config_generation
                with self.failed_save():
                    getattr(manager, method)("probe")
                self.assertEqual(manager.is_plugin_enabled("probe"), initial)
                self.assertEqual(manager.config_generation, generation)
                self.assertEqual(manager.get_plugin_config("probe")["api_key"], "synthetic-secret")

    def test_unrelated_success_and_reload_do_not_persist_rejected_flag(self):
        for method, initial in (("enable_plugin", False), ("disable_plugin", True)):
            with self.subTest(method=method), self.setup_plugins(initial) as (path, manager, registry, service, _):
                with self.failed_save():
                    getattr(service, method)("probe")
                service.enable_plugin("other")
                with patch.object(ConfigManager, "_instance", None):
                    restarted = ConfigManager(str(path))
                    self.assertEqual(restarted.is_plugin_enabled("probe"), initial)
                    self.assertTrue(restarted.is_plugin_enabled("other"))
                self.assertEqual(registry.is_enabled("probe"), initial)
                self.assertTrue(registry.is_enabled("other"))
                self.assertEqual(registry.get_plugin("other").transitions, [(True, True)])

    def test_retry_applies_once_after_durable_save_and_preserves_second_plugin(self):
        for method, initial, target in (("enable_plugin", False, True), ("disable_plugin", True, False)):
            with self.subTest(method=method), self.setup_plugins(initial) as (_, manager, registry, service, resets):
                with self.failed_save():
                    getattr(service, method)("probe")
                getattr(service, method)("probe")
                self.assertEqual(registry.get_plugin("probe").transitions, [(target, target)])
                self.assertEqual(registry.get_plugin("probe").cleanups, int(not target))
                self.assertEqual(manager.is_plugin_enabled("probe"), target)
                self.assertEqual(registry.is_enabled("probe"), target)
                self.assertEqual(resets, ["display", "template"])
                self.assertFalse(registry.is_enabled("other"))
                self.assertFalse(manager.is_plugin_enabled("other"))
                self.assertEqual(registry.get_plugin("other").transitions, [])

    def test_target_removed_after_service_precheck_does_not_persist_or_reset(self):
        for method, initial in (("enable_plugin", False), ("disable_plugin", True)):
            with self.subTest(method=method), self.setup_plugins(initial) as (path, manager, registry, service, resets):
                before = path.read_bytes()
                generation = manager.config_generation

                def removed_target(_plugin_id):
                    with registry._lock:
                        registry._plugins.pop("probe")
                    return None

                with (
                    patch.object(registry, "get_manifest", side_effect=removed_target),
                    patch("src.plugins.registry.load_registry", return_value=[]),
                    self.assertRaises(PluginOperationRejected),
                ):
                    getattr(service, method)("probe")

                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(manager.config_generation, generation)
                self.assertEqual(manager.is_plugin_enabled("probe"), initial)
                self.assertEqual(resets, [])
                self.assertFalse(registry.is_enabled("other"))

    def test_successful_unchanged_flag_save_still_advances_generation(self):
        for method, initial in (("enable_plugin", True), ("disable_plugin", False)):
            with self.subTest(method=method), self.setup_plugins(initial) as (path, manager, registry, _, _):
                before = path.read_bytes()
                generation = manager.config_generation
                writes = []

                def record_write(*args, **kwargs):
                    writes.append(write_json_atomic(*args, **kwargs))
                    return writes[-1]

                with patch("src.config_manager.write_json_atomic", side_effect=record_write):
                    getattr(manager, method)("probe")
                self.assertEqual(writes, [False])
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(manager.config_generation, generation + 1)
                self.assertEqual(manager.is_plugin_enabled("probe"), initial)
                self.assertEqual(registry.is_enabled("probe"), initial)
                self.assertFalse(manager.is_plugin_enabled("other"))
