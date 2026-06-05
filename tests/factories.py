# tests/factories.py

"""Factory functions for creating test objects with sensible defaults."""


def create_test_page(**overrides):
    """Create a test page with optional overrides."""
    return {
        "id": overrides.get("id", "test_page"),
        "title": overrides.get("title", "Test Page"),
        "content": overrides.get("content", "Hello, World!"),
        "variables": overrides.get("variables", {}),
    }


def create_test_schedule(**overrides):
    """Create a test schedule with optional overrides."""
    return {
        "id": overrides.get("id", "test_schedule"),
        "name": overrides.get("name", "Test Schedule"),
        "entries": overrides.get("entries", [{"day": "Monday", "page_id": "test_page", "time": "09:00"}]),
    }


def create_test_plugin(**overrides):
    """Create a test plugin config with optional overrides."""
    return {
        "name": overrides.get("name", "weather"),
        "enabled": overrides.get("enabled", True),
        "config": overrides.get("config", {}),
    }


def create_test_board_state(**overrides):
    """Create a test board state with optional overrides."""
    rows = overrides.get("rows", 6)
    cols = overrides.get("cols", 22)
    return {
        "id": overrides.get("id", "test_board"),
        "title": overrides.get("title", "Test Board"),
        "layout": overrides.get("layout", [[0] * cols for _ in range(rows)]),
    }
