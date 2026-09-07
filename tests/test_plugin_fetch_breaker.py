"""Plugin-fetch circuit breaker and reserved pool capacity (issue #1884).

The shared bounded pool (``PLUGIN_FETCH_MAX_WORKERS``) fixed the thread leak
of #1751, but a wedged fetch OCCUPIES its worker until the plugin returns —
which for a genuinely wedged data source is never. Once that many distinct
referenced plugins wedge, every worker is gone and healthy plugins are starved
off the board permanently.

Two defects are pinned here:

1. **Starvation.** The audit's repro — 12 referenced plugins, 8 of them
   permanently wedged, 60 ticks. The four healthy plugins must be in the
   context on every tick once the breaker has opened, and the wedged ones must
   stop being submitted.
2. **The 15s render stall.** A single wedged *referenced* plugin made every
   render wait the full ``CONTEXT_BUILD_TIMEOUT_SECONDS`` — 15s in production —
   forever. After the breaker opens the render must not wait for it at all.

Timing here is only ever used to separate "waited for the timeout" from "did
not wait at all"; the assertions on presence and submission counts are exact.
"""

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import src.plugins.registry as registry_module
from src.plugins.base import PluginBase, PluginResult
from src.plugins.registry import PluginRegistry

WEDGED = 8
HEALTHY = 4
TICKS = 60
TIMEOUT = 0.05
# Ticks allowed for the breaker to notice and quarantine the wedged plugins.
# Deliberately expressed as a plain number rather than as the threshold
# constant so this test measures BEHAVIOR on both sides of the fix.
SETTLE_TICKS = 10


def _make_registry() -> PluginRegistry:
    loader = MagicMock()
    loader.load_all_plugins.return_value = {}
    loader.load_errors = {}
    loader.get_manifest.return_value = None
    with patch("src.plugins.registry.PluginLoader", return_value=loader):
        return PluginRegistry(plugins_dir=Path("/fake/plugins"))


def _install(registry: PluginRegistry, plugin_id: str, get_data=None):
    plugin = MagicMock(spec=PluginBase)
    plugin.plugin_id = plugin_id
    plugin.supports_triggers = False
    if get_data is not None:
        plugin.get_data.side_effect = get_data
    else:
        plugin.get_data.return_value = PluginResult(available=True, data={"value": plugin_id.upper()})
    registry._plugins[plugin_id] = plugin
    registry._enabled[plugin_id] = True
    return plugin


@pytest.fixture
def fresh_pool():
    """Private shared-pool lifetime so occupancy is this test's alone."""
    registry_module.shutdown_plugin_fetch_executor()
    yield
    registry_module.shutdown_plugin_fetch_executor()


@pytest.fixture
def registry(monkeypatch, fresh_pool):
    reg = _make_registry()
    monkeypatch.setattr("src.plugins.registry.get_plugin_registry", lambda: reg)
    monkeypatch.setattr(registry_module, "CONTEXT_BUILD_TIMEOUT_SECONDS", TIMEOUT)
    return reg


@pytest.fixture
def release():
    """An event every wedged fetch waits on; set in teardown so no thread leaks."""
    ev = threading.Event()
    yield ev
    ev.set()


def _wedge(release: threading.Event):
    def _hang(board=None):
        release.wait(timeout=30)
        return PluginResult(available=False, error="released")

    return _hang


class TestStarvationUnderWedgedPlugins:
    def test_healthy_plugins_are_served_every_tick_despite_eight_wedged_ones(self, registry, release):
        """The audit repro: 8 wedged + 4 healthy referenced plugins, 60 ticks.

        Pre-fix the eight wedged fetches took all eight pool workers on tick 1
        and never gave them back, so the healthy four never started again and
        vanished from the context for the rest of the process's life.
        """
        wedged_ids = [f"wedged_{i}" for i in range(WEDGED)]
        healthy_ids = [f"healthy_{i}" for i in range(HEALTHY)]
        for pid in wedged_ids:  # installed first: they win the race for the workers
            _install(registry, pid, get_data=_wedge(release))
        for pid in healthy_ids:
            _install(registry, pid)

        referenced = wedged_ids + healthy_ids
        contexts = [registry.build_template_context(plugin_ids=referenced) for _ in range(TICKS)]

        # The breaker needs a few ticks to notice; after that every tick must
        # carry all four healthy plugins.
        for offset, context in enumerate(contexts[SETTLE_TICKS:]):
            present = [pid for pid in healthy_ids if pid in context]
            assert present == healthy_ids, (
                f"tick {offset + SETTLE_TICKS}: only {present} of {healthy_ids} reached the context"
            )

        # Non-vacuity: the data really is the healthy plugins' own.
        assert contexts[-1]["healthy_0"] == {"value": "HEALTHY_0"}

        # The wedged plugins are submitted once each and then never again.
        wedged_calls = {pid: registry._plugins[pid].get_data.call_count for pid in wedged_ids}
        assert wedged_calls == dict.fromkeys(wedged_ids, 1), (
            f"wedged plugins were resubmitted after the breaker opened: {wedged_calls}"
        )

    def test_breaker_status_names_the_quarantined_plugins(self, registry, release):
        """The quarantine is reportable, not just a log line."""
        _install(registry, "wedged", get_data=_wedge(release))
        _install(registry, "healthy")

        for _ in range(SETTLE_TICKS):
            registry.build_template_context(plugin_ids=["wedged", "healthy"])

        status = registry.get_fetch_breaker_status()
        assert status["wedged"]["quarantined"] is True
        assert status["wedged"]["consecutive_timeouts"] >= registry_module.PLUGIN_FETCH_BREAKER_THRESHOLD
        assert status["wedged"]["cooldown_remaining_seconds"] > 0
        assert "healthy" not in status, "a plugin that answers every tick must never be quarantined"


class TestWedgedPluginRenderStall:
    def test_a_wedged_referenced_plugin_stops_costing_every_render_the_timeout(self, registry, release):
        """One wedged referenced plugin used to cost EVERY render the full
        context-build timeout (15s in production) forever."""
        _install(registry, "wedged", get_data=_wedge(release))

        durations = []
        for _ in range(SETTLE_TICKS + 5):
            started = time.monotonic()
            registry.build_template_context(plugin_ids=["wedged"])
            durations.append(time.monotonic() - started)

        # Non-vacuity: the first render really did pay the full timeout, so a
        # green result cannot come from the wedge failing to wedge.
        assert durations[0] >= TIMEOUT, f"the first render did not stall at all: {durations[0]:.3f}s"
        after = durations[SETTLE_TICKS:]
        assert all(d < TIMEOUT / 2 for d in after), (
            f"renders still wait for the wedged plugin after the breaker opened: {after}"
        )
