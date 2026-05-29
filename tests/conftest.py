# tests/conftest.py

import os

import pytest
from unittest.mock import Mock


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
    client.get_board.return_value = {
        "id": "test_board",
        "title": "Test Board",
        "layout": [[0] * 22 for _ in range(6)]
    }
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
        "variables": {
            "weather": {"temperature": 72, "condition": "Sunny"},
            "time": "12:00 PM"
        }
    }

@pytest.fixture
def sample_schedule():
    """Sample schedule data for testing."""
    return {
        "id": "test_schedule",
        "name": "Test Schedule",
        "entries": [
            {"day": "Monday", "page_id": "test_page", "time": "09:00"}
        ]
    }

@pytest.fixture
def sample_plugin():
    """Sample plugin config for testing."""
    return {
        "name": "weather",
        "enabled": True,
        "config": {
            "api_key": "test_key",
            "location": "San Francisco"
        }
    }
