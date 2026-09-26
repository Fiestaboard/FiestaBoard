"""Instrumentation tests for demand-driven plugin fetch (issue #1751).

Two audited wastes are pinned here by COUNTING, not by timing:

1. Render fan-out — a template page render fetched EVERY enabled plugin,
   whether or not the template referenced it. After the fix, a render
   fetches only the plugins its template references (plus trigger-capable
   plugins, whose ``check_triggers`` path may rely on fresh data), with a
   safe fetch-all fallback for pages whose variable owners cannot be
   determined statically (formula expressions).
2. Executor churn — every render built a fresh ``ThreadPoolExecutor`` and
   abandoned it with ``shutdown(wait=False)``, leaking one live thread per
   tick per hung plugin. After the fix, one persistent bounded pool serves
   every render: a hung fetch OCCUPIES a worker (bounded) instead of
   leaking a thread (unbounded).

Send behavior itself is pinned elsewhere (tests/test_engine_equivalence.py);
these tests must pass WITHOUT any golden changing.
"""

import threading
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import src.plugins.registry as registry_module
from src.devices import BoardContext
from src.pages.models import Page
from src.pages.service import PageService
from src.pages.storage import PageStorage
from src.plugins.base import DEFAULT_REFRESH_SECONDS, PluginBase, PluginResult
from src.plugins.registry import PluginRegistry
from src.templates.engine import TemplateEngine


def _make_registry() -> PluginRegistry:
    loader = MagicMock()
    loader.load_all_plugins.return_value = {}
    loader.load_errors = {}
    loader.get_manifest.return_value = None
    with patch("src.plugins.registry.PluginLoader", return_value=loader):
        return PluginRegistry(plugins_dir=Path("/fake/plugins"))


def _install_plugin(
    registry: PluginRegistry,
    plugin_id: str,
    *,
    supports_triggers: bool = False,
    get_data=None,
):
    """Register an enabled mock plugin directly on the registry internals."""
    plugin = MagicMock(spec=PluginBase)
    plugin.plugin_id = plugin_id
    plugin.supports_triggers = supports_triggers
    if get_data is not None:
        plugin.get_data.side_effect = get_data
    else:
        plugin.get_data.return_value = PluginResult(available=True, data={"value": plugin_id.upper()})
    registry._plugins[plugin_id] = plugin
    registry._enabled[plugin_id] = True
    return plugin


def _fetched_ids(registry: PluginRegistry) -> dict[str, int]:
    """Map of plugin_id -> how many times its data was fetched."""
    return {pid: p.get_data.call_count for pid, p in registry._plugins.items() if p.get_data.call_count}


def _engine_with(registry) -> TemplateEngine:
    """A TemplateEngine wired to the given registry, skipping real plugin init."""
    engine = TemplateEngine.__new__(TemplateEngine)
    engine._display_service = None
    cm = MagicMock()
    cm.get_color_rules.return_value = []
    engine._config_manager = cm
    engine._plugin_registry = registry
    return engine


def _template_page(page_id: str, lines: list[str]) -> Page:
    return Page(id=page_id, name=page_id, type="template", device_type="flagship", template=lines)


@pytest.fixture
def registry(monkeypatch):
    reg = _make_registry()
    monkeypatch.setattr("src.plugins.registry.get_plugin_registry", lambda: reg)
    return reg


@pytest.fixture
def page_service(monkeypatch, tmp_path, registry):
    storage = PageStorage(storage_file=str(tmp_path / "pages.json"))
    service = PageService(storage=storage)
    monkeypatch.setattr("src.pages.service.get_template_engine", lambda: _engine_with(registry))
    return service


class TestReferencedPluginFiltering:
    def test_render_fetches_only_the_referenced_plugin(self, registry, page_service):
        """A page referencing 1 of 3 enabled plugins fetches exactly that 1."""
        _install_plugin(registry, "alpha")
        _install_plugin(registry, "beta")
        _install_plugin(registry, "gamma")

        page = _template_page("p-1", ["TEMP {{alpha.value}}"])
        result = page_service.render_page(page, contexts={})

        # Non-vacuity: the referenced variable really resolved from plugin data.
        assert result.available
        assert "ALPHA" in result.formatted
        assert _fetched_ids(registry) == {"alpha": 1}

    def test_trigger_capable_plugin_is_fetched_even_when_unreferenced(self, registry, page_service):
        """The engine-tick fetch set is referenced plugins PLUS trigger plugins."""
        _install_plugin(registry, "alpha")
        _install_plugin(registry, "beta")
        _install_plugin(registry, "trig", supports_triggers=True)

        page = _template_page("p-1", ["{{alpha.value}}"])
        result = page_service.render_page(page, contexts={})

        assert result.available
        assert _fetched_ids(registry) == {"alpha": 1, "trig": 1}

    def test_formula_page_falls_back_to_fetching_all_plugins(self, registry, page_service):
        """A {{= ...}} formula's variable owners are not statically known: fetch all."""
        _install_plugin(registry, "alpha")
        _install_plugin(registry, "beta")
        _install_plugin(registry, "gamma")

        page = _template_page("p-1", ["{{= alpha.value & beta.value }}"])
        result = page_service.render_page(page, contexts={})

        assert result.available
        assert "ALPHABETA" in result.formatted
        assert _fetched_ids(registry) == {"alpha": 1, "beta": 1, "gamma": 1}

    def test_second_page_of_same_size_fetches_only_its_missing_plugin(self, registry, page_service):
        """The per-tick shared context widens by fetching only what it lacks."""
        _install_plugin(registry, "alpha")
        _install_plugin(registry, "beta")
        _install_plugin(registry, "gamma")

        contexts: dict[str, dict] = {}
        first = page_service.render_page(_template_page("p-1", ["{{alpha.value}}"]), contexts=contexts)
        second = page_service.render_page(_template_page("p-2", ["{{beta.value}}"]), contexts=contexts)

        assert first.available and "ALPHA" in first.formatted
        assert second.available and "BETA" in second.formatted
        assert _fetched_ids(registry) == {"alpha": 1, "beta": 1}

    def test_fetch_all_consumer_widens_a_filtered_shared_context(self, registry, page_service):
        """A fetch-all consumer (collection resolution) after a filtered render
        fetches only the plugins the shared context does not already hold."""
        _install_plugin(registry, "alpha")
        _install_plugin(registry, "beta")

        contexts: dict[str, dict] = {}
        page_service.render_page(_template_page("p-1", ["{{alpha.value}}"]), contexts=contexts)
        context = page_service.shared_context_for(contexts, "flagship")

        assert context is not None
        assert context.get("alpha") == {"value": "ALPHA"}
        assert context.get("beta") == {"value": "BETA"}
        assert _fetched_ids(registry) == {"alpha": 1, "beta": 1}


class TestPersistentBoundedExecutor:
    def test_thread_count_is_bounded_across_100_ticks_with_a_hanging_plugin(self, registry, monkeypatch):
        """100 renders with a wedged plugin occupy pool workers, not +1 thread/tick."""
        monkeypatch.setattr(registry_module, "CONTEXT_BUILD_TIMEOUT_SECONDS", 0.02)
        release = threading.Event()

        def hang(board=None):
            release.wait(timeout=30)
            return PluginResult(available=False, error="released")

        _install_plugin(registry, "wedged", get_data=hang)
        baseline = threading.active_count()
        try:
            for _ in range(100):
                context = registry.build_template_context()
                assert context == {}  # the wedged plugin never lands in the context
            grown = threading.active_count() - baseline
        finally:
            release.set()

        assert grown <= 8 + 2, f"thread count grew by {grown} across 100 ticks (bounded pool expected)"

    def test_saturated_fetch_pool_logs_a_warning(self, registry, monkeypatch, caplog):
        """When every worker is wedged and a fetch cannot even start, say so."""
        monkeypatch.setattr(registry_module, "CONTEXT_BUILD_TIMEOUT_SECONDS", 0.02)
        release = threading.Event()

        def hang(board=None):
            release.wait(timeout=30)
            return PluginResult(available=False, error="released")

        for i in range(12):  # more wedged plugins than the pool has workers
            _install_plugin(registry, f"wedged_{i}", get_data=hang)

        try:
            with caplog.at_level("WARNING", logger="src.plugins.registry"):
                registry.build_template_context()
                registry.build_template_context()
        finally:
            release.set()

        assert "saturated" in caplog.text


@pytest.fixture
def fresh_pool():
    """A private shared-pool lifetime for occupancy-counting tests."""
    registry_module.shutdown_plugin_fetch_executor()
    yield
    registry_module.shutdown_plugin_fetch_executor()


class TestInFlightFetchDedupe:
    def test_wedged_plugin_occupies_one_worker_and_never_starves_healthy_plugins(
        self, registry, monkeypatch, fresh_pool
    ):
        """12 ticks with one wedged plugin: its pending fetch is JOINED, not
        resubmitted — so it occupies exactly ONE pool worker, and the healthy
        plugin's data is present in the context on every tick.

        (Pre-dedupe, every tick submitted a duplicate wedged fetch; by ~tick 8
        all 8 shared workers were occupied and the healthy plugin's fetch
        could no longer start, killing ALL plugin data board-wide.)
        """
        monkeypatch.setattr(registry_module, "CONTEXT_BUILD_TIMEOUT_SECONDS", 0.1)
        release = threading.Event()
        workers_entered: list[str] = []

        def hang(board=None):
            workers_entered.append(threading.current_thread().name)
            release.wait(timeout=30)
            return PluginResult(available=False, error="released")

        _install_plugin(registry, "wedged", get_data=hang)
        healthy = _install_plugin(registry, "healthy")

        try:
            for tick in range(12):
                context = registry.build_template_context()
                assert context.get("healthy") == {"value": "HEALTHY"}, (
                    f"healthy plugin dropped from the context at tick {tick} "
                    f"(wedged fetch occupies {len(workers_entered)} workers)"
                )
        finally:
            release.set()

        # The healthy plugin really was re-fetched every tick (dedupe joins
        # only PENDING fetches; completed ones are re-submitted as before).
        assert healthy.get_data.call_count == 12
        assert len(workers_entered) == 1, (
            f"wedged fetch occupied {len(workers_entered)} pool workers across 12 ticks; "
            "in-flight dedupe should hold it to exactly one"
        )


class TestTriggerFetchedOncePerTick:
    def test_trigger_plugin_fetched_once_across_three_consumers_in_one_tick(self, registry, page_service):
        """Cache widening fetches exactly the missing ids: the trigger plugin
        rides along on the FIRST build of a size only, not on every widening."""
        _install_plugin(registry, "alpha")
        _install_plugin(registry, "beta")
        _install_plugin(registry, "gamma")
        _install_plugin(registry, "trig", supports_triggers=True)

        contexts: dict[str, dict] = {}
        first = page_service.render_page(_template_page("p-1", ["{{alpha.value}}"]), contexts=contexts)
        second = page_service.render_page(_template_page("p-2", ["{{beta.value}}"]), contexts=contexts)
        third = page_service.render_page(_template_page("p-3", ["{{gamma.value}}"]), contexts=contexts)

        # Non-vacuity: all three renders resolved their variable, and the
        # trigger plugin's data is in the shared context.
        assert first.available and "ALPHA" in first.formatted
        assert second.available and "BETA" in second.formatted
        assert third.available and "GAMMA" in third.formatted
        assert contexts[next(k for k in contexts if not k.startswith("\x00"))].get("trig") == {"value": "TRIG"}

        assert _fetched_ids(registry) == {"alpha": 1, "beta": 1, "gamma": 1, "trig": 1}


# ==========================================================================
# The calling-thread fast path for already-cached plugins
# ==========================================================================


class _CountingPlugin(PluginBase):
    """A real PluginBase, so its real cache decides what a fetch costs."""

    def __init__(self, plugin_id: str, manifest_extra: dict | None = None):
        self._pid = plugin_id
        self.fetches = 0
        super().__init__({"id": plugin_id, "name": plugin_id, "version": "1.0.0", **(manifest_extra or {})})

    @property
    def plugin_id(self) -> str:
        return self._pid

    def fetch_data(self) -> PluginResult:
        self.fetches += 1
        return PluginResult(available=True, data={"value": f"V{self.fetches}"})


@pytest.fixture
def counted_pool(monkeypatch):
    """Count every submission to the shared plugin-fetch pool."""
    executor = registry_module._get_fetch_executor()
    submits = []
    real_submit = executor.submit

    def counting_submit(fn, *args, **kwargs):
        submits.append(args[0] if args else None)
        return real_submit(fn, *args, **kwargs)

    monkeypatch.setattr(executor, "submit", counting_submit)
    return submits


def _install_real_plugin(registry, plugin, enabled: bool = True):
    registry._plugins[plugin.plugin_id] = plugin
    registry._enabled[plugin.plugin_id] = enabled
    return plugin


class TestCachedFetchFastPath:
    """A plugin whose own cache is fresh must not be dispatched to a thread.

    Measured against doing the identical work inline, the dispatch — Future
    allocation, queue put, worker wakeup, condvar wait, done-callback and
    three lock round-trips — costs 21x what the in-memory dict read it wraps
    costs. The second-order win matters more: a fully cached tick that never
    submits also never enters ``futures_wait``, so it can never pay the
    context-build timeout for a plugin it was not going to talk to.
    """

    def test_a_cached_plugin_is_served_without_touching_the_pool(self, counted_pool):
        registry = _make_registry()
        plugin = _install_real_plugin(registry, _CountingPlugin("cached"))

        first = registry.build_template_context(plugin_ids=["cached"])
        submits_after_first = len(counted_pool)
        second = registry.build_template_context(plugin_ids=["cached"])

        assert first == {"cached": {"value": "V1"}}
        assert second == {"cached": {"value": "V1"}}, "the cached payload must still reach the context"
        assert submits_after_first == 1, "the cold build must dispatch"
        assert len(counted_pool) == 1, "the warm build must not dispatch"
        assert plugin.fetches == 1

    def test_a_cached_build_never_enters_the_context_build_wait(self, monkeypatch):
        """This is what decouples a fully-cached tick from the fetch timeout."""
        registry = _make_registry()
        _install_real_plugin(registry, _CountingPlugin("cached"))
        registry.build_template_context(plugin_ids=["cached"])

        waits = []
        real_wait = registry_module.futures_wait
        monkeypatch.setattr(
            registry_module,
            "futures_wait",
            lambda *a, **k: (waits.append(1), real_wait(*a, **k))[1],
        )
        assert registry.build_template_context(plugin_ids=["cached"]) == {"cached": {"value": "V1"}}
        assert waits == []

    def test_a_live_data_plugin_never_takes_the_fast_path(self, counted_pool):
        """live_data means "stale is wrong by definition" — it has no cache."""
        registry = _make_registry()
        plugin = _install_real_plugin(registry, _CountingPlugin("clock", {"live_data": True}))

        registry.build_template_context(plugin_ids=["clock"])
        registry.build_template_context(plugin_ids=["clock"])

        assert len(counted_pool) == 2
        assert plugin.fetches == 2

    def test_an_expired_cache_is_refetched_through_the_pool(self, counted_pool, monkeypatch):
        registry = _make_registry()
        plugin = _install_real_plugin(registry, _CountingPlugin("stale"))
        registry.build_template_context(plugin_ids=["stale"])

        # Age the cache past the default refresh interval.
        with plugin._cache_lock:
            for key in plugin._last_fetch_times:
                plugin._last_fetch_times[key] -= timedelta(seconds=DEFAULT_REFRESH_SECONDS + 1)

        assert registry.build_template_context(plugin_ids=["stale"]) == {"stale": {"value": "V2"}}
        assert len(counted_pool) == 2
        assert plugin.fetches == 2

    def test_a_disabled_plugin_is_never_served_from_cache(self):
        registry = _make_registry()
        _install_real_plugin(registry, _CountingPlugin("off"))
        registry.build_template_context(plugin_ids=["off"])
        registry._enabled["off"] = False

        assert registry.get_cached_plugin_data("off") is None

    def test_a_plugin_returning_a_non_result_falls_through_to_a_real_fetch(self, counted_pool):
        """Only a genuine PluginResult may stand in for a fetch.

        Without this guard any ``MagicMock(spec=PluginBase)`` — the shape half
        this suite's doubles take — would satisfy the fast path and put a mock
        object into the template context.
        """
        registry = _make_registry()
        plugin = _install_real_plugin(registry, _CountingPlugin("liar"))
        plugin.cached_result = lambda board=None: {"not": "a result"}

        assert registry.build_template_context(plugin_ids=["liar"]) == {"liar": {"value": "V1"}}
        assert len(counted_pool) == 1

    def test_cached_result_is_keyed_by_board_geometry(self):
        """A Flagship's cached payload must never answer a Note's probe."""
        registry = _make_registry()
        _install_real_plugin(registry, _CountingPlugin("board_aware"))
        flagship = BoardContext("flagship", rows=6, cols=22)
        note = BoardContext("note", rows=3, cols=15)

        registry.build_template_context(flagship, plugin_ids=["board_aware"])

        assert registry.get_cached_plugin_data("board_aware", flagship) is not None
        assert registry.get_cached_plugin_data("board_aware", note) is None
