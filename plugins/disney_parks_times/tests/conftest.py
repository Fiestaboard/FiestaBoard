"""Plugin test fixtures for disney_parks_times."""

import pytest


@pytest.fixture(autouse=True)
def reset_plugin_singletons():
    """Reset plugin singletons before each test."""
    yield


@pytest.fixture
def sample_manifest():
    """Return sample manifest for testing."""
    return {
        "id": "disney_parks_times",
        "name": "Disney Park Queue Times",
        "version": "1.0.0",
        "settings_schema": {
            "type": "object",
            "properties": {
                "parks": {"type": "array", "items": {"type": "object"}},
                "refresh_seconds": {"type": "integer", "default": 300},
            },
            "required": ["parks"],
        },
        "variables": {"simple": ["formatted"], "arrays": {"parks": {"label_field": "park_name", "item_fields": ["park_id", "park_name", "rides"]}}},
        "max_lengths": {"formatted": 22},
    }


@pytest.fixture
def sample_config():
    """Return sample configuration for testing."""
    return {
        "parks": [
            {"park_id": 16, "ride_ids": [284, 279]},
        ],
        "refresh_seconds": 300,
        "enabled": True,
    }


@pytest.fixture
def parks_json_response():
    """Queue-Times parks.json (Disney group only)."""
    return [
        {"id": 11, "name": "Other", "parks": []},
        {
            "id": 2,
            "name": "Walt Disney Attractions",
            "parks": [
                {"id": 16, "name": "Disneyland", "country": "United States", "timezone": "America/Los_Angeles"},
                {"id": 17, "name": "Disney California Adventure", "country": "United States", "timezone": "America/Los_Angeles"},
            ],
        },
    ]


@pytest.fixture
def queue_times_json_response():
    """Queue-Times queue_times.json for one park."""
    return {
        "lands": [
            {
                "id": 117,
                "name": "Tomorrowland",
                "rides": [
                    {"id": 284, "name": "Space Mountain", "is_open": True, "wait_time": 60, "last_updated": "2026-02-14T18:05:39.000Z"},
                    {"id": 279, "name": "Matterhorn Bobsleds", "is_open": True, "wait_time": 55, "last_updated": "2026-02-14T18:05:39.000Z"},
                ],
            },
        ],
        "rides": [],
    }
