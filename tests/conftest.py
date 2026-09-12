# tests/conftest.py

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

# Session-wide throwaway data dir, created in ``pytest_configure`` (below) and
# removed in ``pytest_unconfigure``. Module-level so both hooks see it.
_SESSION_DATA_ROOT: Path | None = None


def pytest_configure(config):
    """Point ``FIESTABOARD_DATA_DIR`` at a throwaway dir before collection (#1894).

    Function-scoped fixtures cannot protect anything that resolves the data
    directory at **import or collection time**: module-level work in a test
    file (four modules build a ``TestClient(app)`` at module scope) runs
    before any fixture is active. With ``FIESTABOARD_DATA_DIR`` unset in that
    window, ``src.paths.get_data_dir()`` falls back to ``<repo>/data`` and the
    suite writes the developer's real checkout — ``config.json``,
    ``external_plugins/.legacy-migration-done`` — intermittently under xdist,
    where collection and execution interleave differently per worker.

    Setting the variable here, before collection, closes the window for the
    whole session: every default data-dir resolution (they all route through
    the ``src/paths.py`` seam, #1762) lands in a temp dir, whatever the import
    order. Per-test fixtures can still layer narrower isolation on top.

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
