# tests/conftest.py

import threading
from unittest.mock import Mock

import pytest


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
    # Deliberately NOT reset: src.api_server._service (the background display
    # loop). test_service_lifecycle.py owns its lifecycle.


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
    """
    monkeypatch.setenv("FIESTABOARD_DATA_DIR", str(tmp_path / "data"))
    _drop_all_singletons()
    yield tmp_path / "data"
    _drop_all_singletons()


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
    if "test_auth_" in test_file or "test_secrets_encryption" in test_file:
        return
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "false")


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
