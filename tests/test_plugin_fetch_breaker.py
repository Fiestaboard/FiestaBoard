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
from src.devices import BoardContext
from src.plugins.base import PluginBase, PluginResult
from src.plugins.registry import PluginRegistry
from src.settings.service import PollingSettings

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


# ==========================================================================
# The three defects the Pi audit found in the machinery above
# ==========================================================================


class TestContextBuildBudget:
    def test_the_fetch_budget_stays_below_the_shortest_poll_interval(self):
        """The budget and the tick period must not be the same number.

        ``build_template_context`` blocks the single service thread, which also
        runs the 1 Hz silence-boundary detector and the collection-cadence gate
        (src/main.py). While the budget EQUALLED the default 15s interval, one
        slow plugin consumed an entire tick period and delayed silence
        entry/exit by up to a full 15 seconds.

        Pinned against the FLOOR the settings service will accept, not just the
        default, so a user who polls as fast as the product allows still gets a
        tick that finishes inside its own period.
        """
        floor = PollingSettings.from_dict({"interval_seconds": 1}).interval_seconds
        assert floor > registry_module.CONTEXT_BUILD_TIMEOUT_SECONDS
        assert PollingSettings().interval_seconds > registry_module.CONTEXT_BUILD_TIMEOUT_SECONDS


class TestBreakerIsPerBoardGeometry:
    """The breaker measures fetches; a fetch is one plugin ON one geometry.

    Keyed by plugin_id alone, the counters crossed geometries in both
    directions — and the direction that actually fires in the field is the one
    that never quarantines anything.
    """

    def test_a_plugin_wedged_on_one_geometry_keeps_serving_the_other(self, registry, release):
        def wedge_flagship_only(board=None):
            if board is not None and board.device_type == "flagship":
                release.wait(timeout=30)
                return PluginResult(available=False, error="released")
            return PluginResult(available=True, data={"value": "NOTE_OK"})

        _install(registry, "dual", get_data=wedge_flagship_only)
        flagship = BoardContext("flagship", rows=6, cols=22)
        note = BoardContext("note", rows=3, cols=15)

        note_contexts = []
        for _ in range(SETTLE_TICKS):
            registry.build_template_context(flagship, plugin_ids=["dual"])
            note_contexts.append(registry.build_template_context(note, plugin_ids=["dual"]))

        assert all(c.get("dual") == {"value": "NOTE_OK"} for c in note_contexts), (
            "the healthy geometry lost its data to the other geometry's quarantine"
        )

    def test_a_healthy_geometry_does_not_cancel_the_wedged_one_s_streak(self, registry, release):
        """The stall the breaker exists to end must still end.

        Pre-fix the Note build's success popped the shared plugin_id streak
        every tick, so the Flagship fetch never reached the threshold and every
        Flagship render kept paying the full context-build timeout forever.
        """

        def wedge_flagship_only(board=None):
            if board is not None and board.device_type == "flagship":
                release.wait(timeout=30)
                return PluginResult(available=False, error="released")
            return PluginResult(available=True, data={"value": "NOTE_OK"})

        _install(registry, "dual", get_data=wedge_flagship_only)
        flagship = BoardContext("flagship", rows=6, cols=22)
        note = BoardContext("note", rows=3, cols=15)

        for _ in range(SETTLE_TICKS):
            registry.build_template_context(flagship, plugin_ids=["dual"])
            registry.build_template_context(note, plugin_ids=["dual"])

        assert registry.get_fetch_breaker_status()["dual"]["quarantined"] is True

        started = time.monotonic()
        registry.build_template_context(flagship, plugin_ids=["dual"])
        assert time.monotonic() - started < TIMEOUT / 2

    def test_a_second_board_does_not_charge_two_timeouts_per_tick(self, registry, release):
        """Two geometries used to trip a threshold-3 breaker in two ticks."""
        _install(registry, "slow", get_data=_wedge(release))
        flagship = BoardContext("flagship", rows=6, cols=22)
        note = BoardContext("note", rows=3, cols=15)

        for _ in range(registry_module.PLUGIN_FETCH_BREAKER_THRESHOLD - 1):
            registry.build_template_context(flagship, plugin_ids=["slow"])
            registry.build_template_context(note, plugin_ids=["slow"])

        status = registry.get_fetch_breaker_status()["slow"]
        assert status["consecutive_timeouts"] == registry_module.PLUGIN_FETCH_BREAKER_THRESHOLD - 1
        assert status["quarantined"] is False, "two boards quarantined a plugin one tick early"


class _SlowButHonestPlugin(PluginBase):
    """A real PluginBase that always answers, just later than the budget."""

    def __init__(self, delay: float):
        self._delay = delay
        self.fetches = 0
        super().__init__({"id": "slow_honest", "name": "slow", "version": "1.0.0"})

    @property
    def plugin_id(self) -> str:
        return "slow_honest"

    def fetch_data(self) -> PluginResult:
        self.fetches += 1
        time.sleep(self._delay)
        return PluginResult(available=True, data={"value": "LATE"})


class TestSlowIsNotWedged:
    def test_a_plugin_that_answers_after_the_budget_is_never_quarantined(self, registry):
        """Shortening the budget must not turn slow data sources into dead ones.

        The abandoned fetch still lands and fills PluginBase's cache, so the
        next tick serves it inline — which is proof the plugin answered, and
        ends its timeout streak.
        """
        plugin = _SlowButHonestPlugin(delay=TIMEOUT * 3)
        registry._plugins["slow_honest"] = plugin
        registry._enabled["slow_honest"] = True

        contexts = [registry.build_template_context(plugin_ids=["slow_honest"]) for _ in range(SETTLE_TICKS)]

        assert contexts[-1] == {"slow_honest": {"value": "LATE"}}, "late data never reached the board"
        assert registry.get_fetch_breaker_status() == {}, "a slow-but-answering plugin was quarantined"
        assert plugin.fetches == 1, "the cached answer was refetched instead of served"
