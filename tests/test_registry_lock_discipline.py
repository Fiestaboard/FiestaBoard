"""The registry lock must not be held across the plugin fetch fan-out.

``PluginRegistry.build_template_context`` fans plugin fetches out onto a
worker pool.  Each worker runs :meth:`PluginRegistry.fetch_plugin_data`,
which takes the registry lock for its own lookups.  If the calling thread
(the engine tick) still holds that lock while it waits on the futures, every
worker blocks on it and the tick blocks on the workers: the pool deadlocks
and no board ever updates again.

Nothing else covers this.  The engine equivalence corpus explicitly excludes
the fetch machinery, and both the snapshot (#1828) and the demand-filter
rewrite (#1751) touched this exact function on separate branches — a naive
integration of the two would have reintroduced the hazard silently.

The probe runs *inside a pool worker*: it tries to take the registry lock
with a short timeout.  Under correct code the lock is free and the probe
succeeds; if the caller held it across the submit/wait the worker cannot
take it, and the assertions below fail.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import src.plugins.registry as registry_module
from src.plugins.base import PluginBase, PluginResult
from src.plugins.registry import PluginRegistry

# Long enough that a loaded CI box does not flake, short enough that a real
# deadlock fails the test in seconds instead of hanging the suite.
LOCK_PROBE_TIMEOUT = 5.0

# What the fan-out's own wait budget is shortened to for these tests. Only
# reached when the fan-out is actually wedged; the healthy cases return in
# milliseconds.
DEADLOCKED_WAIT_BUDGET = 2.0


class _LockProbePlugin(PluginBase):
    """A plugin whose fetch reports whether the registry lock was free.

    ``fetch_data`` runs on a pool worker, at exactly the moment the calling
    thread is parked in ``futures_wait``. Taking the registry lock there is
    the same thing ``fetch_plugin_data`` does for its own lookups, so this
    reproduces the deadlock's precondition without depending on the pool
    starving first.
    """

    def __init__(self, plugin_id: str, registry: PluginRegistry) -> None:
        # Set before super().__init__: PluginBase's constructor logs
        # ``self.plugin_id``, which reads ``_id``.
        self._id = plugin_id
        self._registry = registry
        self.probe_results: list[bool] = []
        super().__init__({"id": plugin_id, "name": plugin_id, "version": "1.0.0", "live_data": True})

    @property
    def plugin_id(self) -> str:
        return self._id

    def fetch_data(self) -> PluginResult:
        acquired = self._registry._lock.acquire(timeout=LOCK_PROBE_TIMEOUT)
        self.probe_results.append(acquired)
        if acquired:
            self._registry._lock.release()
        return PluginResult(available=True, data={"lock_was_free": acquired})


@pytest.fixture
def registry() -> PluginRegistry:
    loader = MagicMock()
    loader.load_all_plugins.return_value = {}
    loader.load_errors = {}
    loader.get_manifest.return_value = None
    with patch("src.plugins.registry.PluginLoader", return_value=loader):
        return PluginRegistry(plugins_dir=Path("/fake/plugins"))


@pytest.fixture
def isolated_fetch_pool(monkeypatch):
    """Give the fan-out its own pool, so a wedged worker in a failing run
    cannot poison the process-wide executor for the rest of the session."""
    pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="lock-discipline-test")
    monkeypatch.setattr(registry_module, "_get_fetch_executor", lambda: pool)
    # Bound the wait so a genuine deadlock fails fast instead of parking the
    # suite for the production 15s budget on every probed plugin.
    monkeypatch.setattr(registry_module, "CONTEXT_BUILD_TIMEOUT_SECONDS", DEADLOCKED_WAIT_BUDGET)
    yield pool
    pool.shutdown(wait=False, cancel_futures=True)


def _install(registry: PluginRegistry, plugin: _LockProbePlugin) -> None:
    registry._plugins[plugin.plugin_id] = plugin
    registry._enabled[plugin.plugin_id] = True


def test_registry_lock_is_free_while_the_fetch_fanout_is_in_flight(registry, isolated_fetch_pool):
    """A worker running a plugin fetch must be able to take the registry lock."""
    plugin = _LockProbePlugin("lock_probe", registry)
    _install(registry, plugin)

    context = registry.build_template_context()

    assert plugin.probe_results == [True], (
        "the registry lock was still held while the fetch fan-out ran — "
        "build_template_context must snapshot and release it before submitting"
    )
    assert context == {"lock_probe": {"lock_was_free": True}}


def test_registry_lock_is_free_for_a_demand_filtered_fanout(registry, isolated_fetch_pool):
    """Same property on the demand-driven path (#1751).

    The filtered branch consults ``trigger_plugins`` — another lock-taking
    property — between the snapshot and the submit, so it gets its own
    coverage rather than riding on the fetch-everything case.
    """
    wanted = _LockProbePlugin("wanted", registry)
    unwanted = _LockProbePlugin("unwanted", registry)
    _install(registry, wanted)
    _install(registry, unwanted)
    # Neither is trigger-capable, so the filter is the only thing selecting.
    wanted._manifest["triggers"] = []
    unwanted._manifest["triggers"] = []

    context = registry.build_template_context(plugin_ids=["wanted"])

    assert wanted.probe_results == [True], "the registry lock was still held across the demand-filtered fan-out"
    assert unwanted.probe_results == [], "the demand filter should not have fetched 'unwanted'"
    assert context == {"wanted": {"lock_was_free": True}}


def test_probe_detects_a_lock_held_across_the_fanout(registry, isolated_fetch_pool):
    """The probe itself is not vacuous.

    Reproduces the exact hazard: the *calling* thread holds the registry
    lock across the fan-out.  ``_lock`` is re-entrant, so the caller sails
    through ``enabled_plugins`` and submits — and then every worker blocks in
    ``fetch_plugin_data``'s lookup, the wait budget expires, and no plugin
    data comes back at all.  If this test ever stops failing to fetch, the
    two above have stopped proving anything.
    """
    plugin = _LockProbePlugin("held", registry)
    _install(registry, plugin)

    with registry._lock:
        context = registry.build_template_context()
        # The worker never got past fetch_plugin_data's lookup, so fetch_data
        # (and its probe) never ran and the context came back empty.
        assert plugin.probe_results == []
        assert context == {}
