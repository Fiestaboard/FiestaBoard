"""Value-level contract goldens for the /triggers API (Phase 2 §2, slice 8).

Triggers are how a plugin interrupts the board — a doorbell, a delivery, a
low-battery warning. The web UI reads ``priority`` to sort them and
``remaining_seconds`` to run the dismiss countdown, so the *values* matter,
not just the key set.

Nothing in this domain's contract changed in the conversion pass: every
status code, error string, body key and value asserted below is exactly what
the unconverted trunk answered. The conversion added ``response_model=``,
``responses=`` and a typed body where there was none — none of which is
observable here, which is the point.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(_isolated_data_dir):
    from src.api_server import app

    return TestClient(app)


@pytest.fixture
def fired_trigger():
    """Activate one real trigger through the service and yield its id."""
    from src.plugins.base import TriggerResult
    from src.triggers.service import get_trigger_service

    service = get_trigger_service()
    service.activate_trigger(
        "doorbell",
        TriggerResult(
            triggered=True,
            trigger_id="doorbell:front",
            message="SOMEONE IS AT THE DOOR",
            priority=7,
            duration_seconds=300,
            data={"camera": "front"},
        ),
    )
    return "doorbell:front"


# ---------------------------------------------------------------------------
# GET /triggers
# ---------------------------------------------------------------------------


def test_listing_with_nothing_active_is_an_empty_list_not_an_error(client):
    response = client.get("/triggers")
    assert response.status_code == 200
    assert response.json() == {"triggers": [], "count": 0}


def test_listing_serialises_a_fired_trigger_field_by_field(client, fired_trigger):
    response = client.get("/triggers")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    (trigger,) = body["triggers"]
    assert trigger["trigger_id"] == "doorbell:front"
    assert trigger["plugin_id"] == "doorbell"
    assert trigger["message"] == "SOMEONE IS AT THE DOOR"
    assert trigger["formatted_lines"] is None
    assert trigger["data"] == {"camera": "front"}
    assert trigger["priority"] == 7
    assert trigger["duration_seconds"] == 300
    assert isinstance(trigger["activated_at"], str)
    assert 0 < trigger["remaining_seconds"] <= 300


def test_count_matches_the_list_it_is_served_with(client, fired_trigger):
    body = client.get("/triggers").json()
    assert body["count"] == len(body["triggers"])


# ---------------------------------------------------------------------------
# GET /triggers/active
# ---------------------------------------------------------------------------


def test_active_is_an_explicit_null_when_nothing_has_fired(client):
    response = client.get("/triggers/active")
    assert response.status_code == 200
    assert response.json() == {"trigger": None}


def test_active_returns_the_fired_trigger_under_the_trigger_key(client, fired_trigger):
    response = client.get("/triggers/active")
    assert response.status_code == 200
    assert response.json()["trigger"]["trigger_id"] == "doorbell:front"


# ---------------------------------------------------------------------------
# POST /triggers/{trigger_id}/dismiss
# ---------------------------------------------------------------------------


def test_dismissing_an_unknown_trigger_is_a_404_naming_it(client):
    response = client.post("/triggers/no-such-trigger/dismiss")
    assert response.status_code == 404
    assert response.json()["detail"] == "Trigger not found: no-such-trigger"


def test_dismissing_echoes_the_id_and_removes_it_from_the_list(client, fired_trigger):
    response = client.post(f"/triggers/{fired_trigger}/dismiss")
    assert response.status_code == 200
    assert response.json() == {"status": "dismissed", "trigger_id": fired_trigger}
    assert client.get("/triggers").json() == {"triggers": [], "count": 0}


# ---------------------------------------------------------------------------
# POST /triggers/clear
# ---------------------------------------------------------------------------


def test_clear_empties_the_list_and_reports_cleared(client, fired_trigger):
    response = client.post("/triggers/clear")
    assert response.status_code == 200
    assert response.json() == {"status": "cleared"}
    assert client.get("/triggers").json()["count"] == 0


# ---------------------------------------------------------------------------
# POST /triggers/check
# ---------------------------------------------------------------------------


def test_check_reports_how_many_plugins_it_polled_and_what_is_active(client):
    response = client.post("/triggers/check")
    assert response.status_code == 200
    assert response.json() == {"plugins_checked": 0, "active_triggers": [], "count": 0}


def test_check_leaves_an_already_active_trigger_in_place(client, fired_trigger):
    response = client.post("/triggers/check")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["active_triggers"][0]["trigger_id"] == "doorbell:front"
    assert body["count"] == len(body["active_triggers"])
