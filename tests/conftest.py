# tests/conftest.py

import os
import shutil
import tempfile
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest

# Session-wide throwaway data dir, created in ``pytest_configure`` (below) and
# removed in ``pytest_unconfigure``. Module-level so both hooks see it.
_SESSION_DATA_ROOT: Path | None = None


def pytest_configure(config):
    """Point ``FIESTABOARD_DATA_DIR`` at a throwaway dir before collection (#1894).

    The autouse ``_isolated_data_dir`` fixture below is *function*-scoped, so
    it cannot cover the two windows where nothing is active:

    1. **Collection time.** ``src/api_server.py`` resolves the data dir while
       it is being imported (``is_auth_enabled()`` at module scope builds the
       auth service, which resolves ``<data>/auth.json``). Four test modules
       build a ``TestClient(app)`` at module scope, so every xdist worker
       imports it before the first fixture runs.
    2. **After a test's teardown.** ``monkeypatch`` restores the variable to
       whatever it was *before* the test. Background threads a test started
       (e.g. ``board-state-poll`` in ``src/main.py``) outlive it, and the next
       thing they log re-enters ``ConfigManager()`` -> ``get_data_dir()``.

    With the variable unset in either window ``get_data_dir()`` falls back to
    ``<repo>/data`` and the suite writes the checkout — the intermittent
    ``config.json`` / ``logs/app.log`` leak that fails innocent PRs on CI's
    "Verify tests did not write data/" step.

    Setting it here, before collection, closes both: the fallback every
    ``monkeypatch`` teardown restores to is now a temp dir, not the repo. The
    per-test fixture stays layered on top for per-test isolation.

    The directory is keyed by ``PYTEST_XDIST_WORKER`` (pid when running
    without xdist) so parallel workers never share one.
    """
    global _SESSION_DATA_ROOT
    worker = os.environ.get("PYTEST_XDIST_WORKER") or f"pid{os.getpid()}"
    _SESSION_DATA_ROOT = Path(tempfile.mkdtemp(prefix=f"fiestaboard-tests-{worker}-"))
    os.environ["FIESTABOARD_DATA_DIR"] = str(_SESSION_DATA_ROOT / "data")


def pytest_unconfigure(config):
    """Remove the session data dir created in ``pytest_configure``."""
    global _SESSION_DATA_ROOT
    if _SESSION_DATA_ROOT is not None:
        shutil.rmtree(_SESSION_DATA_ROOT, ignore_errors=True)
        _SESSION_DATA_ROOT = None


def _drop_all_singletons() -> None:
    """Forget every cached service instance, as a process restart would.

    Ordering hazard (see tests/test_mcp_state_effects.py): the template
    engine binds ``get_plugin_registry()`` onto itself, so the registry must
    be reset BEFORE the engine. We null the engine singleton outright (rather
    than ``reset_template_engine()``, whose ``reset_cache()`` would eagerly
    build — and fully initialize — a brand-new plugin registry on every
    test): the next ``get_template_engine()`` call builds a fresh engine
    bound to a fresh registry, and only in tests that actually use it.

    **Audited against every module global in ``src/``** (``grep -rn "    global
    " src/``). The ones deliberately NOT reset here, and why:

    * ``src.api_server._service_running`` / ``_service_thread`` /
      ``_shutting_down`` — owned by ``tests/test_service_lifecycle.py``, which
      drives them directly.
    * ``src.display_runtime._running_probe`` / ``_loop_spawn`` / ``_loop_halt``
      / ``_service_start_time`` — installed once by ``src.api_server`` at
      import; not per-test state.
    * ``src.board_send_executor._send_pool`` / ``_preview_pool`` and
      ``src.plugins.registry._fetch_executor`` / ``_fetch_workers_lost`` —
      idle thread pools that are already self-healing (shut down to ``None``,
      rebuilt lazily). Their threads hold no config or data-dir state.
    * ``src.network.wifi._service``, ``src.system.mdns._mdns_service``,
      ``src.utils.transit_cache._cache_instance``, ``src.time_service._bootstrap``
      and the ad-hoc response caches (``_ai_generate_last_call``,
      ``_muni_stops_cache``, ``_station_info_cache``) — no test was observed
      leaving any of them dirty. ``transit_cache`` does own a background
      thread; add it here if one ever starts leaking.
    """
    import src.auth.service as auth_service_module
    import src.backup.service as backup_service_module
    import src.collections.service as collection_service_module
    import src.display_runtime as display_runtime
    import src.mqtt.client as mqtt_client_module
    import src.pages.service as page_service_module
    import src.panels.service as panel_service_module
    import src.schedules.service as schedule_service_module
    import src.settings.service as settings_service_module
    import src.templates.engine as engine_module
    from src.config_manager import ConfigManager
    from src.displays.service import reset_display_service
    from src.plugins.registry import reset_plugin_registry
    from src.time_service import reset_time_service
    from src.triggers.service import reset_trigger_service

    # Registry before engine — see docstring.
    reset_plugin_registry()
    engine_module._template_engine = None

    ConfigManager._instance = None  # type: ignore[attr-defined]
    ConfigManager._lock = threading.Lock()  # type: ignore[attr-defined]

    settings_service_module._settings_service = None
    page_service_module._page_service = None
    collection_service_module._collection_service = None
    schedule_service_module._schedule_service = None
    panel_service_module._panel_service = None
    backup_service_module._backup_service = None
    reset_display_service()
    auth_service_module._reset_for_tests()
    reset_trigger_service()
    reset_time_service()

    # The DisplayService singleton. The comment that used to sit here named
    # `src.api_server._service`, an attribute that has not existed since the
    # debug slice moved the accessor to src/display_runtime.py — so nothing was
    # being deliberately preserved, the singleton was simply escaping the reset.
    # Any test that drives a send path without stubbing `get_service` builds a
    # real DisplayService (with vb_client=None), and it then answered
    # `get_service()` for every later test in the worker, carrying board clients
    # and a path into an already-deleted tmp data dir. Reset it like every other
    # singleton; test_service_lifecycle.py drives the background *thread*
    # (`_service_running`, `_service_thread`), which is api_server state and is
    # still left alone.
    #
    # Dropping the reference is not enough: `DisplayService.initialize()` starts
    # a `board-state-poll` thread, and that thread outlives the reference. See
    # `_stop_display_service` for what it does to the *next* test in the worker.
    _stop_display_service(display_runtime._service)
    display_runtime._service = None

    # The MQTT client singleton, which owns a `_sync_loop` thread of its own.
    # Same argument as the display service: `tests/test_mqtt_client.py` leaves
    # five of them running, and `get_mqtt_client()` answers with a client built
    # against a previous test's mock broker until something replaces it.
    _stop_mqtt_client(mqtt_client_module._mqtt_client_instance)
    mqtt_client_module._mqtt_client_instance = None


def _stop_display_service(service) -> None:
    """Stop the background threads of the ``DisplayService`` being dropped.

    ``DisplayService.initialize()`` starts a daemon ``board-state-poll`` thread
    whose loop is::

        while self.running:
            interval = self._get_board_read_interval()   # get_settings_service()
            ...
            time.sleep(interval)

    Nulling ``display_runtime._service`` drops the *reference*; the thread keeps
    running. Every 30s it re-enters ``get_settings_service()``, which — because
    this fixture has since set ``_settings_service = None`` — CONSTRUCTS A NEW
    SettingsService and stores it in the process global, and then, through
    ``SettingsService.__init__`` -> ``_load_transition_settings`` ->
    ``Config._get_board()``, constructs a new ``ConfigManager`` singleton
    against the default config path. Both writes land in whatever test happens
    to be running at that moment, in that worker.

    That is the xdist flake this closes. Two observed shapes:

    * ``tests/test_transitions_contract.py`` — the ``beta_on`` fixture enables
      ``transition_plugins_enabled`` on the settings singleton, the poll thread
      replaces the singleton mid-test, and the route's beta gate reads the
      replacement's default ``False``::

          assert 'Transition plugins are an experimental beta. ...'
                 == "Transition plugin 'ghost' not loaded or not enabled"

    * ``tests/test_silence_per_board_composition.py`` — ``ConfigManager`` is a
      ``__new__``-singleton that ignores ``config_path`` once an instance
      exists, so ``ConfigManager(config_path=tmp/config.json)`` silently binds
      to the poll thread's default-path instance and the migration finds
      nothing to seed (``assert 0 == 1``).

    ``running = False`` is the existing stop seam — it is exactly what
    ``src/main.py``'s SIGTERM handler does — so no production code changes.
    The thread re-checks it at the top of every iteration and exits without
    touching another global. Send workers and the adaptive post-send refresh
    thread get their own cancels; neither is joined, because a per-test join
    would cost more than the leak.
    """
    if service is None:
        return
    service.running = False
    try:
        runtimes = list(getattr(service, "runtimes", {}).values())
    except RuntimeError:  # pragma: no cover - dict replaced concurrently
        return
    for runtime in runtimes:
        cancel = getattr(runtime, "refresh_cancel", None)
        if cancel is not None:
            cancel.set()
        worker = getattr(runtime, "send_worker", None)
        if worker is not None:
            worker.stop(timeout=0.0)


def _stop_mqtt_client(client) -> None:
    """Stop the ``_sync_loop`` thread of the MQTT client being dropped."""
    if client is None:
        return
    client._running = False


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Every test runs against a throwaway data dir (#1762).

    ``src.paths.get_data_dir()`` — the one seam every store's default path
    resolves through — honors ``FIESTABOARD_DATA_DIR``, so pointing it at
    ``tmp_path`` keeps the suite off the developer's real ``data/``. The
    singletons are dropped on both sides of the test: before, so this test
    cannot see a store some earlier test built against its own tmp dir;
    after, so no singleton survives holding a path into this test's (now
    deleted) tmp dir.

    This narrows isolation to one test. It does *not* establish it: the
    session-wide override in ``pytest_configure`` above is what guarantees
    the variable is never unset, including at collection time and after this
    fixture's ``monkeypatch`` has been undone (#1894).
    """
    monkeypatch.setenv("FIESTABOARD_DATA_DIR", str(tmp_path / "data"))
    _drop_all_singletons()
    yield tmp_path / "data"
    _drop_all_singletons()


#: Collaborators that moved from ``src.api_server`` to ``src.display_runtime``
#: in the Phase 2 debug slice. ``api_server`` re-exports every one of them, so
#: both module attributes exist and both are legitimate patch targets.
#:
#: Six names left this tuple with their re-exports: ``_primary_board_entry``,
#: ``_primary_connection_info``, ``_get_first_board_dims``,
#: ``_note_out_of_band_write``, ``_publish_mqtt_state_update`` and
#: ``_send_with_status``. No test patches any of them at
#: ``src.api_server.<name>``, so forwarding them there steered nothing —
#: it only kept six re-exports alive that had no other consumer. Patch
#: ``src.display_runtime.<name>`` for these; the rest still work both ways.
_DISPLAY_RUNTIME_SEAMS = (
    "get_settings_service",
    "get_service",
    "peek_service",
    "_get_board_client",
    "_board_is_paused",
    "_get_server_ip",
    "_get_service_uptime",
    "_format_uptime",
)


@pytest.fixture(autouse=True)
def _display_runtime_follows_api_server_stubs(monkeypatch):
    """Stub both targets while the seam retirement is half done.

    Phase 2 moves collaborators out of ``src/api_server.py`` one domain at a
    time (spec §2.3). Until the last domain converts, two module attributes
    name the same collaborator: the canonical one in
    :mod:`src.display_runtime` and the re-export in ``src.api_server`` that
    ~130 existing ``patch("src.api_server.<name>")`` targets resolve. Patching
    one rebinds only that module's name, so a test that stubs the api_server
    side and drives a handler *through* display_runtime would silently get the
    real collaborator — and, with no board configured, a 503 that looks like a
    product bug.

    This makes display_runtime read the api_server attribute at call time, so
    a stub set on either side is honored on both. Patching
    ``src.display_runtime.<name>`` still wins: it replaces the forwarder.

    Behavior-preserving: in production ``api_server.<name>`` *is*
    display_runtime's function object, so the forwarder resolves to exactly
    what it replaced. Delete this fixture when api_server stops re-exporting
    (the recipe's "shared accessor cannot be deleted until its last consumer
    converts").
    """
    import src.api_server as api_server
    import src.display_runtime as display_runtime

    def _forward(name):
        def forwarder(*args, **kwargs):
            return getattr(api_server, name)(*args, **kwargs)

        forwarder.__name__ = name
        forwarder.__doc__ = f"Test shim: resolves src.api_server.{name} at call time."
        return forwarder

    for name in _DISPLAY_RUNTIME_SEAMS:
        monkeypatch.setattr(display_runtime, name, _forward(name))


@pytest.fixture(autouse=True)
def _disable_auth_for_tests(request, monkeypatch):
    """Disable auth enforcement by default in the test suite.

    The auth middleware is *secure-by-default* — when no admin user
    exists and no env override is set it returns 409 setup-required on
    every protected endpoint. That's correct production behavior but
    would break every API-level test that pre-dates the auth feature.

    Auth-specific tests opt out by depending on their own `enabled` /
    `disabled` / `undecided` fixtures, which override the env after
    this one runs.
    """
    # Skip for the auth-specific suites that manage the env themselves.
    test_file = str(request.node.fspath)
    if "test_auth_" in test_file:
        return
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "false")


@pytest.fixture(autouse=True)
def _reset_silence_window_cache():
    """Isolate the parsed silence-window cache (issue #1752) per test.

    ``Config.silence_config_for`` caches its result keyed on the config
    manager's write generation. In production every config change goes
    through ``_save_internal`` (which bumps the generation), but tests
    routinely swap the underlying feature dict via ``patch.object(Config,
    "_get_feature", ...)`` — a seam the generation cannot see — so a cached
    window from one test would leak into the next.
    """
    from src.config import Config

    Config._silence_cache.clear()
    Config._silence_migrations_ran = None
    yield
    Config._silence_cache.clear()
    Config._silence_migrations_ran = None


# Shared fixtures for test helpers
@pytest.fixture
def mock_board_client():
    """Mock client for Vestaboard API interactions."""
    client = Mock()
    client.post_message.return_value = {"success": True}
    client.get_board.return_value = {"id": "test_board", "title": "Test Board", "layout": [[0] * 22 for _ in range(6)]}
    return client


@pytest.fixture
def mock_api_client():
    """Mock API client for integration tests."""
    client = Mock()
    client.get.return_value = {"status": 200, "data": {}}
    client.post.return_value = {"status": 201, "data": {}}
    return client


@pytest.fixture
def sample_page():
    """Sample page data for testing."""
    return {
        "id": "test_page",
        "title": "Test Page",
        "content": "Hello, World!",
        "variables": {"weather": {"temperature": 72, "condition": "Sunny"}, "time": "12:00 PM"},
    }


@pytest.fixture
def sample_schedule():
    """Sample schedule data for testing."""
    return {
        "id": "test_schedule",
        "name": "Test Schedule",
        "entries": [{"day": "Monday", "page_id": "test_page", "time": "09:00"}],
    }


@pytest.fixture
def sample_plugin():
    """Sample plugin config for testing."""
    return {"name": "weather", "enabled": True, "config": {"api_key": "test_key", "location": "San Francisco"}}
