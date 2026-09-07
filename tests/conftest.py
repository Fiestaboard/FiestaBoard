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
    """
    import src.auth.service as auth_service_module
    import src.backup.service as backup_service_module
    import src.collections.service as collection_service_module
    import src.display_runtime as display_runtime
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
    display_runtime._service = None


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
_DISPLAY_RUNTIME_SEAMS = (
    "get_settings_service",
    "get_service",
    "peek_service",
    "_get_board_client",
    "_board_is_paused",
    "_primary_board_entry",
    "_primary_connection_info",
    "_get_first_board_dims",
    "_get_server_ip",
    "_get_service_uptime",
    "_format_uptime",
    "_note_out_of_band_write",
    "_publish_mqtt_state_update",
    "_send_with_status",
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
