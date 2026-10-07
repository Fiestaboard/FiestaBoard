"""Tests for the /settings/beta API endpoints (transition and output plugin flags).

HTTPS (Beta) was removed in settings v5; what replaced its tests is in
``tests/test_settings_v5_https_removed.py``.
"""

from fastapi.testclient import TestClient

from src.api_server import app

client = TestClient(app)


def test_get_beta_settings_returns_defaults():
    response = client.get("/settings/beta")
    assert response.status_code == 200
    assert response.json() == {"settings": {"transition_plugins_enabled": False, "output_plugins_enabled": False}}


def test_put_beta_toggles_transition_plugins_and_persists():
    response = client.put("/settings/beta", json={"transition_plugins_enabled": True})
    assert response.status_code == 200
    assert response.json()["settings"]["transition_plugins_enabled"] is True
    assert client.get("/settings/beta").json()["settings"]["transition_plugins_enabled"] is True


def test_put_beta_toggles_output_plugins():
    response = client.put("/settings/beta", json={"output_plugins_enabled": True})
    assert response.status_code == 200
    assert response.json()["settings"]["output_plugins_enabled"] is True


def test_put_beta_rejects_a_non_boolean_flag():
    response = client.put("/settings/beta", json={"transition_plugins_enabled": "yes"})
    assert response.status_code == 422


def test_settings_all_includes_beta_section():
    """beta should appear in the consolidated /settings/all payload."""
    response = client.get("/settings/all")
    assert response.status_code == 200
    data = response.json()
    assert data["beta"] == {"transition_plugins_enabled": False, "output_plugins_enabled": False}
