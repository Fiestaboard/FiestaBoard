"""Completed discovery invalidation must beat late catalog publication."""

import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from unittest.mock import patch

from src.config_manager import ConfigManager
from src.plugins.base import PluginBase, PluginResult
from src.plugins.manifest import PluginManifest
from src.plugins.registry import PluginRegistry
from src.plugins.service import PluginService


class Catalog(PluginBase):
    def __init__(self, identity):
        super().__init__({"id": identity})
        self.fail = False
        self.fetches = 0
        self.block_config = False
        self.invalid = False
        self.config_entered = threading.Event()
        self.config_release = threading.Event()

    @property
    def plugin_id(self):
        return self._manifest["id"]

    @PluginBase.config.setter
    def config(self, value):
        if self.block_config:
            self.config_entered.set()
            if not self.config_release.wait(3):
                raise RuntimeError("test config barrier timed out")
        PluginBase.config.fset(self, value)

    def validate_config(self, config):
        return ["synthetic invalid stored setting"] if self.invalid else []

    def fetch_data(self):
        self.fetches += 1
        return PluginResult(available=not self.fail, data={self.config["field"]: "value"})


class DiscoveryPublication(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.manager_patch = patch.object(ConfigManager, "_instance", None)
        self.manager_patch.start()
        root = Path(self.directory.name)
        self.manager = ConfigManager(str(root / "config.json"))
        self.registry = PluginRegistry(root / "plugins")
        for identity in ["probe", "other"]:
            plugin = Catalog(identity)
            self.registry._plugins[identity] = plugin
            self.registry._manifests[identity] = PluginManifest.from_dict(
                {"id": identity, "name": identity, "version": "1.0.0", "variables": {"auto_discover": True}}
            )
            config = {"enabled": True, "field": identity + "_old"}
            self.manager.set_plugin_config(identity, config)
            self.registry.set_plugin_config(identity, config)
            self.registry.enable_plugin(identity)
        self.plugin = self.registry.get_plugin("probe")
        self.service = PluginService(
            registry=self.registry, config_manager=self.manager, reset_display=lambda: None, reset_template=lambda: None
        )

    def tearDown(self):
        self.manager_patch.stop()
        self.directory.cleanup()

    @contextmanager
    def pending(self):
        entered = threading.Event()
        release = threading.Event()
        original = self.registry.fetch_plugin_data

        def pause_after_fetch(identity, board=None):
            result = original(identity, board)
            if identity == "probe":
                entered.set()
                if not release.wait(3):
                    raise RuntimeError("test barrier timed out")
            return result

        with ThreadPoolExecutor(max_workers=1) as pool:
            with patch.object(self.registry, "fetch_plugin_data", side_effect=pause_after_fetch):
                future = pool.submit(self.registry.get_all_variables)
                try:
                    self.assertTrue(entered.wait(3))
                    yield future
                finally:
                    release.set()
                    future.result(timeout=3)

    def change(self, identity="probe"):
        self.service.update_plugin_config(identity, {"enabled": True, "field": identity + "_new"})
        self.assertEqual(self.manager.get_plugin_config(identity)["field"], identity + "_new")

    def test_late_catalog_cannot_refill_cache_after_completed_config_save(self):
        with self.pending() as future:
            self.change()
        with self.subTest(boundary="returned catalog"):
            self.assertNotIn("probe_old", future.result().get("probe", []))
        with self.subTest(boundary="cache publication"):
            self.assertNotIn("probe", self.registry._discovered_vars)
        with self.subTest(boundary="next request"):
            self.assertEqual(self.registry.get_all_variables().get("probe", []), ["probe_new"])

    def test_obsolete_failed_discovery_does_not_back_off_healthy_new_config(self):
        self.plugin.fail = True
        with self.pending():
            self.change()
            self.plugin.fail = False
        with self.subTest(boundary="no obsolete backoff"):
            self.assertNotIn("probe", self.registry._discovery_failed_at)
        with self.subTest(boundary="immediate healthy discovery"):
            self.assertEqual(self.registry.get_all_variables().get("probe", []), ["probe_new"])

    def test_clear_all_invalidates_pending_catalog_publication(self):
        with self.pending() as future:
            self.registry.clear_discovered_cache()
        with self.subTest(boundary="returned catalog"):
            self.assertEqual(future.result().get("probe", []), [])
        with self.subTest(boundary="no old cache"):
            self.assertNotIn("probe", self.registry._discovered_vars)
        self.assertEqual(self.registry.get_all_variables().get("probe", []), ["probe_old"])

    def test_replaced_plugin_cannot_publish_retired_catalog(self):
        with self.pending():
            replacement = Catalog("probe")
            replacement.config = {"field": "replacement"}
            replacement.enabled = True
            with self.registry._lock:
                self.registry._plugins["probe"] = replacement
        with self.subTest(boundary="no retired cache"):
            self.assertNotIn("probe", self.registry._discovered_vars)
        with self.subTest(boundary="new instance discovery"):
            self.assertEqual(self.registry.get_all_variables().get("probe", []), ["replacement"])

    def test_disabled_plugin_cannot_publish_catalog(self):
        with self.pending():
            self.registry.disable_plugin("probe")
        with self.subTest(boundary="no disabled cache"):
            self.assertNotIn("probe", self.registry._discovered_vars)
        self.assertNotIn("probe", self.registry._discovery_failed_at)
        self.registry.enable_plugin("probe")
        self.assertEqual(self.registry.get_all_variables().get("probe", []), ["probe_old"])

    def test_disabled_failed_discovery_does_not_delay_healthy_reenable(self):
        self.plugin.fail = True
        with self.pending():
            self.registry.disable_plugin("probe")
        self.plugin.fail = False
        with self.subTest(boundary="no disabled failure backoff"):
            self.assertNotIn("probe", self.registry._discovery_failed_at)
        self.registry.enable_plugin("probe")
        with self.subTest(boundary="immediate healthy reenable"):
            self.assertEqual(self.registry.get_all_variables().get("probe", []), ["probe_old"])

    def test_unchanged_failure_keeps_normal_retry_backoff(self):
        self.plugin.fail = True
        self.assertEqual(self.registry.get_all_variables().get("probe", []), [])
        self.assertIn("probe", self.registry._discovery_failed_at)
        self.assertEqual(self.registry.get_all_variables().get("probe", []), [])
        self.assertEqual(self.plugin.fetches, 1)

    def test_config_application_completion_invalidates_discovery_started_after_preclear(self):
        for stored, failed in [(False, False), (True, False), (False, True), (True, True)]:
            with self.subTest(stored_fallback=stored, failed_fetch=failed):
                self.plugin.block_config = False
                self.plugin.invalid = False
                self.plugin.config_entered.clear()
                self.plugin.config_release.clear()
                self.service.update_plugin_config("probe", {"enabled": True, "field": "probe_old"})
                self.plugin.block_config = True
                self.plugin.invalid = stored
                self.plugin.fail = failed
                config = {"enabled": True, "field": "probe_new"}
                if stored:
                    self.manager.set_plugin_config("probe", config)
                    operation = partial(self.registry.apply_stored_config, "probe", config)
                else:
                    operation = partial(self.service.update_plugin_config, "probe", config)
                with ThreadPoolExecutor(max_workers=1) as pool:
                    config_future = pool.submit(operation)
                    try:
                        self.assertTrue(self.plugin.config_entered.wait(3))
                        with self.pending() as discovery:
                            self.plugin.config_release.set()
                            config_future.result(timeout=3)
                            self.plugin.fail = False
                            self.assertEqual(self.plugin.config["field"], "probe_new")
                    finally:
                        self.plugin.config_release.set()
                        config_future.result(timeout=3)
                with self.subTest(boundary="no stale return"):
                    self.assertNotIn("probe_old", discovery.result().get("probe", []))
                with self.subTest(boundary="no stale cache"):
                    self.assertNotIn("probe", self.registry._discovered_vars)
                with self.subTest(boundary="no stale backoff"):
                    self.assertNotIn("probe", self.registry._discovery_failed_at)
                with self.subTest(boundary="immediate current fields"):
                    self.assertEqual(self.registry.get_all_variables().get("probe", []), ["probe_new"])

    def test_other_plugin_config_change_preserves_current_catalog(self):
        with self.pending() as future:
            self.change("other")
        self.assertEqual(future.result().get("probe", []), ["probe_old"])
        self.assertEqual(self.registry._discovered_vars["probe"], ["probe_old"])
        self.assertEqual(self.registry.get_all_variables()["other"], ["other_new"])
