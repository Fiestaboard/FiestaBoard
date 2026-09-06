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
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import src.plugins.registry as registry_module
from src.pages.models import Page
from src.pages.service import PageService
from src.pages.storage import PageStorage
from src.plugins.base import PluginBase, PluginResult
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

