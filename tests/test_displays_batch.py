"""Tests for batch display endpoints."""

from fastapi.testclient import TestClient

from src.api_server import app

client = TestClient(app)


def test_displays_raw_batch_success():
    """Test successful batch display fetch."""
    response = client.post("/displays/raw/batch", json={"display_types": ["date_time"], "enabled_only": False})

    assert response.status_code == 200
    data = response.json()

    assert "displays" in data
    assert "total" in data
    assert "successful" in data
    assert data["total"] == 1

    # Check date_time display is in results
    assert "date_time" in data["displays"]
    display = data["displays"]["date_time"]
    assert "data" in display
    assert "available" in display
    assert "error" in display


def test_displays_raw_batch_multiple_plugins():
    """Test batch fetch with multiple plugins."""
    response = client.post(
        "/displays/raw/batch", json={"display_types": ["date_time", "weather", "stocks"], "enabled_only": False}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 3
    assert "date_time" in data["displays"]

    # Other plugins may or may not be available depending on configuration
    # but should be in the response
    for plugin_id in ["date_time", "weather", "stocks"]:
        assert plugin_id in data["displays"]


def test_displays_raw_batch_enabled_only():
    """Test batch fetch with enabled_only filter."""
    response = client.post(
        "/displays/raw/batch", json={"display_types": ["date_time", "weather", "stocks", "muni"], "enabled_only": True}
    )

    assert response.status_code == 200
    data = response.json()

    # enabled_only filters out non-available plugins
    # All returned displays should be available
    for _display_id, display in data["displays"].items():
        assert display["available"] is True

    # Total requested may be more than returned
    assert data["total"] == 4
    assert data["successful"] == len(data["displays"])


def test_displays_raw_batch_no_display_types():
    """Test batch endpoint with missing display_types."""
    response = client.post("/displays/raw/batch", json={})

    assert response.status_code == 400
    assert "display_types parameter required" in response.json()["detail"]


def test_displays_raw_batch_invalid_display_types():
    """Test batch endpoint with invalid display_types format."""
    response = client.post("/displays/raw/batch", json={"display_types": "not_a_list"})

    assert response.status_code == 400
    assert "display_types must be a list" in response.json()["detail"]


def test_displays_raw_batch_partial_failure():
    """Test batch fetch with some invalid plugins."""
    response = client.post(
        "/displays/raw/batch",
        json={"display_types": ["date_time", "invalid_plugin_xyz", "another_fake"], "enabled_only": False},
    )

    assert response.status_code == 200
    data = response.json()

    # All requested plugins should be in results
    assert "date_time" in data["displays"]
    assert "invalid_plugin_xyz" in data["displays"]
    assert "another_fake" in data["displays"]

    # Invalid plugins should not be available
    assert data["displays"]["invalid_plugin_xyz"]["available"] is False
    assert data["displays"]["another_fake"]["available"] is False

    # Total requested should match
    assert data["total"] == 3


def test_displays_raw_batch_empty_list():
    """Test batch endpoint with empty display_types list."""
    response = client.post("/displays/raw/batch", json={"display_types": []})

    # Should return 400 since no display_types provided
    assert response.status_code == 400


def test_displays_raw_batch_data_structure():
    """Test that batch response has correct data structure."""
    response = client.post("/displays/raw/batch", json={"display_types": ["date_time"], "enabled_only": False})

    assert response.status_code == 200
    data = response.json()

    # Verify overall structure
    assert isinstance(data["displays"], dict)
    assert isinstance(data["total"], int)
    assert isinstance(data["successful"], int)

    # Verify individual display structure
    for _display_id, display in data["displays"].items():
        assert "data" in display
        assert "available" in display
        assert "error" in display
        assert isinstance(display["data"], dict)
        assert isinstance(display["available"], bool)
        assert display["error"] is None or isinstance(display["error"], str)


def test_displays_raw_batch_default_enabled_only():
    """Test that enabled_only defaults to True."""
    response = client.post("/displays/raw/batch", json={"display_types": ["date_time"]})

    assert response.status_code == 200
    data = response.json()

    # Should only return enabled plugins by default
    # All returned plugins should be available
    for _display_id, display in data["displays"].items():
        assert display["available"] is True
