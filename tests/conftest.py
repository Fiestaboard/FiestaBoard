"""Pytest configuration and fixtures.

This module provides fixtures that reset singleton instances between tests
to ensure test isolation and prevent test pollution.
"""

import pytest


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singleton service instances before each test.

    This ensures tests don't pollute each other with leftover state
    from singleton instances.
    """
    # Import the modules that have singletons
    from src.displays import service as displays_service
    from src.settings import service as settings_service
    from src.pages import service as pages_service
    from src.templates import engine as template_engine
    from src.system import mdns as mdns_module

    # Reset all singletons before the test
    displays_service._display_service = None
    settings_service._settings_service = None
    pages_service._page_service = None
    template_engine._template_engine = None
    mdns_module._mdns_service = None

    yield

    # Reset again after the test (cleanup)
    displays_service._display_service = None
    settings_service._settings_service = None
    pages_service._page_service = None
    template_engine._template_engine = None
    mdns_module._mdns_service = None


@pytest.fixture
def mock_config():
    """Fixture to mock configuration values.
    
    Usage:
        def test_something(mock_config):
            with patch('src.config.Config.WEATHER_API_KEY', 'test_key'):
                # test code
    """
    from unittest.mock import patch
    return patch


