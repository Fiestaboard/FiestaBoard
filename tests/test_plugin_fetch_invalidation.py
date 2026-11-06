"""A completed invalidation must win over an older in-flight fetch."""

import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from unittest.mock import patch

from src.config_manager import ConfigManager
from src.devices import BoardContext
from src.plugins.base import PluginBase, PluginResult
from src.plugins.registry import PluginRegistry
from src.plugins.service import PluginService


class BarrierPlugin(PluginBase):
    def __init__(self, identity="probe", live=False):
        super().__init__({"id": identity, "live_data": live})
        self.entered = threading.Event()
        self.release = threading.Event()
        self.block_next = False
        self.fetches = 0

    @property
    def plugin_id(self):
        return self._manifest["id"]

    def fetch_data(self):
        value = self.config.get("value", "old")
        key = self.board.key if self.board else "default"
        self.fetches += 1
        if self.block_next:
            self.block_next = False
            self.entered.set()
            if not self.release.wait(10):
                raise AssertionError("test did not release synthetic fetch")
        return PluginResult(available=True, data={"value": value, "board": key})


class TestPluginFetchInvalidation(unittest.TestCase):
    @contextmanager
    def setup_plugins(self, live=False):
        with tempfile.TemporaryDirectory() as directory, patch.object(ConfigManager, "_instance", None):
            manager = ConfigManager(str(Path(directory) / "config.json"))
            registry = PluginRegistry(Path(directory) / "plugins")
            for identity in ("probe", "other"):
                plugin = BarrierPlugin(identity, live)
                registry._plugins[identity] = plugin
                config = {"enabled": True, "value": "old"}
                manager.set_plugin_config(identity, config)
                registry.set_plugin_config(identity, config)
                registry.enable_plugin(identity)
            service = PluginService(
                registry=registry,
                config_manager=manager,
                reset_display=lambda: None,
                reset_template=lambda: None,
            )
            yield registry, registry.get_plugin("probe"), service, manager

    @contextmanager
    def pending(self, plugin, operation):
        plugin.block_next = True
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(operation)
            try:
                self.assertTrue(plugin.entered.wait(5), "synthetic fetch never started")
                yield future
            finally:
                plugin.release.set()
                future.result(timeout=5)

    def test_config_save_discards_old_result_and_does_not_repopulate_cache(self):
        with self.setup_plugins() as (registry, plugin, service, manager):
            with self.pending(plugin, lambda: registry.fetch_plugin_data("probe")) as future:
                service.update_plugin_config("probe", {"enabled": True, "value": "new"})
                self.assertEqual(manager.get_plugin_config("probe")["value"], "new")
                plugin.release.set()
                result = future.result(timeout=5)
            self.assertFalse(result.available, "old-config payload escaped to its caller")
            self.assertIsNone(plugin.cached_result())
            self.assertEqual(registry.fetch_plugin_data("probe").data["value"], "new")

    def test_explicit_clear_discards_inflight_and_the_next_call_refetches(self):
        with self.setup_plugins() as (registry, plugin, _, _):
            with self.pending(plugin, lambda: registry.fetch_plugin_data("probe")) as future:
                plugin.clear_cache()
                plugin.release.set()
                result = future.result(timeout=5)
            with self.subTest(boundary="invalidated return"):
                self.assertFalse(result.available)
            with self.subTest(boundary="invalidated cache"):
                self.assertIsNone(plugin.cached_result())
            self.assertTrue(registry.fetch_plugin_data("probe").available)
            self.assertEqual(plugin.fetches, 2)

    def test_self_clear_discards_that_fetch_without_poisoning_a_later_fetch(self):
        with self.setup_plugins() as (registry, plugin, _, _):
            fetch = plugin.fetch_data

            def clear_once():
                result = fetch()
                if plugin.fetches == 1:
                    plugin.clear_cache()
                return result

            with patch.object(plugin, "fetch_data", side_effect=clear_once):
                result = registry.fetch_plugin_data("probe")
                with self.subTest(boundary="invalidated return"):
                    self.assertFalse(result.available)
                with self.subTest(boundary="invalidated cache"):
                    self.assertIsNone(plugin.cached_result())
                self.assertTrue(registry.fetch_plugin_data("probe").available)
            self.assertEqual(plugin.fetches, 2)

    def test_old_fetch_cannot_overwrite_a_new_config_cache(self):
        with self.setup_plugins() as (registry, plugin, service, _):
            with self.pending(plugin, lambda: registry.fetch_plugin_data("probe")) as future:
                service.update_plugin_config("probe", {"enabled": True, "value": "new"})
                fresh = registry.fetch_plugin_data("probe")
                self.assertEqual(fresh.data["value"], "new")
                plugin.release.set()
                future.result(timeout=5)
            self.assertIs(plugin.cached_result(), fresh)
            self.assertIs(registry.fetch_plugin_data("probe"), fresh)

    def test_context_omits_invalidated_fetch_but_retains_other_plugin(self):
        with self.setup_plugins() as (registry, plugin, service, _):
            with self.pending(plugin, registry.build_template_context) as future:
                service.update_plugin_config("probe", {"enabled": True, "value": "new"})
                plugin.release.set()
                context = future.result(timeout=5)
            self.assertNotIn("probe", context)
            self.assertEqual(context["other"]["value"], "old")
            self.assertEqual(registry.build_template_context()["probe"]["value"], "new")

    def test_disable_and_reenable_discard_old_context_and_cache(self):
        for reenable in (False, True):
            with self.subTest(reenable=reenable), self.setup_plugins() as (registry, plugin, _, _):
                with self.pending(plugin, registry.build_template_context) as future:
                    registry.disable_plugin("probe")
                    if reenable:
                        registry.enable_plugin("probe")
                    plugin.release.set()
                    context = future.result(timeout=5)
                self.assertNotIn("probe", context)
                self.assertIsNone(plugin.cached_result())
                if reenable:
                    self.assertTrue(registry.fetch_plugin_data("probe").available)
                    self.assertEqual(plugin.fetches, 2)

    def test_replacement_cannot_return_retired_instance_data(self):
        with self.setup_plugins() as (registry, plugin, _, _):
            with self.pending(plugin, registry.build_template_context) as future:
                replacement = BarrierPlugin()
                replacement.config = {"value": "replacement"}
                replacement.enabled = True
                # Synthetic equivalent of the registry's locked reload swap.
                with registry._lock:
                    registry._plugins["probe"] = replacement
                plugin.release.set()
                context = future.result(timeout=5)
            self.assertNotIn("probe", context)
            self.assertIsNone(replacement.cached_result())
            self.assertEqual(registry.build_template_context()["probe"]["value"], "replacement")

    def test_live_data_result_is_invalidated_too(self):
        with self.setup_plugins(live=True) as (registry, plugin, service, _):
            with self.pending(plugin, lambda: registry.fetch_plugin_data("probe")) as future:
                service.update_plugin_config("probe", {"enabled": True, "value": "new"})
                plugin.release.set()
                result = future.result(timeout=5)
            self.assertFalse(result.available)
            self.assertEqual(registry.fetch_plugin_data("probe").data["value"], "new")

    def test_unchanged_config_and_other_plugin_preserve_inflight_result(self):
        with self.setup_plugins() as (registry, plugin, service, _):
            with self.pending(plugin, lambda: registry.fetch_plugin_data("probe")) as future:
                service.update_plugin_config("probe", {"enabled": True, "value": "old"})
                service.update_plugin_config("other", {"enabled": True, "value": "new"})
                plugin.release.set()
                result = future.result(timeout=5)
            self.assertTrue(result.available)
            self.assertIs(plugin.cached_result(), result)
            self.assertEqual(plugin.fetches, 1)

    def test_config_invalidation_covers_all_board_keys_without_cross_contamination(self):
        with self.setup_plugins() as (registry, plugin, service, _):
            small = BoardContext("pixels", rows=8, cols=8)
            large = BoardContext("pixels", rows=64, cols=64)
            other = registry.fetch_plugin_data("other", large)
            with self.pending(plugin, lambda: registry.fetch_plugin_data("probe", small)) as future:
                service.update_plugin_config("probe", {"enabled": True, "value": "new"})
                fresh_large = registry.fetch_plugin_data("probe", large)
                plugin.release.set()
                future.result(timeout=5)
            self.assertIsNone(plugin.cached_result(small))
            self.assertIs(plugin.cached_result(large), fresh_large)
            fresh_small = registry.fetch_plugin_data("probe", small)
            self.assertEqual(fresh_small.data, {"value": "new", "board": small.key})
            self.assertEqual(fresh_large.data, {"value": "new", "board": large.key})
            self.assertIs(registry.fetch_plugin_data("other", large), other)

    def test_context_rechecks_completed_and_cached_answers_after_other_fetches(self):
        for warm in (False, True):
            with self.subTest(warm=warm), self.setup_plugins() as (registry, plugin, service, _):
                answered = threading.Event()
                if warm:
                    registry.fetch_plugin_data("probe")
                    original = registry.get_cached_plugin_data

                    def observe(identity, board=None, original=original, answered=answered):
                        result = original(identity, board)
                        if identity == "probe":
                            answered.set()
                        return result

                    target, attribute = registry, "get_cached_plugin_data"
                else:
                    original = registry.fetch_plugin_data

                    def observe(identity, board=None, original=original, answered=answered):
                        result = original(identity, board)
                        if identity == "probe":
                            answered.set()
                        return result

                    target, attribute = registry, "fetch_plugin_data"
                fingerprints = {}
                other = registry.get_plugin("other")
                build_context = partial(registry.build_template_context, fingerprints=fingerprints)
                with patch.object(target, attribute, observe):
                    with self.pending(other, build_context) as future:
                        self.assertTrue(answered.wait(5), "probe never answered")
                        service.update_plugin_config("probe", {"enabled": True, "value": "new"})
                        other.release.set()
                        context = future.result(timeout=5)
                self.assertNotIn("probe", context)
                self.assertNotIn("probe", fingerprints)
                self.assertEqual(set(fingerprints), set(context))
                self.assertEqual(context["other"]["value"], "old")

    def test_registry_rechecks_generation_after_provider_returns(self):
        with self.setup_plugins() as (registry, plugin, service, _):
            answered = threading.Event()
            original = plugin.get_data

            def observe(board=None):
                result = original(board)
                answered.set()
                return result

            with patch.object(plugin, "get_data", observe):
                with self.pending(plugin, lambda: registry.fetch_plugin_data("probe")) as future:
                    with registry._lock:
                        plugin.release.set()
                        self.assertTrue(answered.wait(5), "provider never returned")
                        service.update_plugin_config("probe", {"enabled": True, "value": "new"})
                    result = future.result(timeout=5)
            self.assertFalse(result.available)
            self.assertEqual(registry.fetch_plugin_data("probe").data["value"], "new")
