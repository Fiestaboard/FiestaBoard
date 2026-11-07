"""``status`` on ``GET /panel/{id}``: what the panel's board is doing (H13).

A TV viewer is read-only, but it should still be able to say *why* the board
looks the way it does: "Override · 2h 42m left", "Silenced", "Paused ·
showing the last update". Before this the viewer config carried no override,
silence, pause or schedule state at all, so the TV could show none of it.

``status`` is additive. Every key the viewer config already had is unchanged,
and ``GET /panel/{id}/frame`` is untouched (its golden lives in
``tests/test_panels_contract.py``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from tests.silence_helpers import ENDS_AT, silenced


@pytest.fixture
def client(_isolated_data_dir):
    from src.api_server import app

    return TestClient(app)


@pytest.fixture
def panel(client) -> dict:
    response = client.post("/panels", json={"name": "Living room TV"})
    assert response.status_code == 201, response.text
    return response.json()


def _status(client, panel) -> dict:
    response = client.get(f"/panel/{panel['id']}")
    assert response.status_code == 200, response.text
    return response.json()["status"]


def _settings():
    from src.settings.service import get_settings_service

    return get_settings_service()


@pytest.fixture
def panel_is_primary(panel, monkeypatch):
    """Make the panel's board the primary board, the only one an override drives today."""
    from src.settings.service import SettingsService

    monkeypatch.setattr(SettingsService, "get_primary_board_id", lambda self: panel["board_id"])


def _arm_override(expires_at: str | None) -> None:
    from src.settings.service import TemporaryOverride

    _settings().set_temporary_override(TemporaryOverride(page_id="evening-commute", expires_at=expires_at))


def test_an_idle_panel_reports_manual_mode_and_nothing_holding_it(client, panel):
    assert _status(client, panel) == {
        "mode": "manual",
        "schedule_enabled": False,
        "override_active": False,
        "override_expires_at": None,
        "silenced": False,
        "silenced_until": None,
        "silence_mode": None,
        "paused": False,
    }


def test_the_status_is_stable_between_polls_while_nothing_changes(client, panel):
    """A viewer diffs the config it polls; a per-request field would churn it."""
    assert _status(client, panel) == _status(client, panel)


def test_a_paused_board_reports_paused(client, panel):
    _settings().set_paused(True, board_id=panel["board_id"])
    assert _status(client, panel)["paused"] is True


def test_pausing_another_board_does_not_mark_this_panel_paused(client, panel):
    _settings().set_paused(True, board_id=_settings().get_primary_board_id())
    assert _status(client, panel)["paused"] is False


def test_a_board_following_its_schedule_reports_schedule_mode(client, panel):
    _settings().set_schedule_enabled(True, board_id=panel["board_id"])
    status = _status(client, panel)
    assert status["schedule_enabled"] is True
    assert status["mode"] == "schedule"


def test_a_silenced_board_reports_when_silence_ends_and_its_silence_mode(client, panel):
    with silenced(board=panel["board_id"]):
        status = _status(client, panel)
    assert status["silenced"] is True
    assert status["silenced_until"] == ENDS_AT
    # The resolved default; "indicator" and "page" render differently on a TV.
    assert status["silence_mode"] == "freeze"


def test_silencing_another_board_does_not_mark_this_panel_silenced(client, panel):
    with silenced(board="some-other-board"):
        status = _status(client, panel)
    assert (status["silenced"], status["silenced_until"], status["silence_mode"]) == (False, None, None)


def test_a_timed_override_reports_override_mode_and_when_it_ends(client, panel, panel_is_primary):
    expires_at = (datetime.now(UTC) + timedelta(hours=2, minutes=42)).isoformat()
    _arm_override(expires_at)
    status = _status(client, panel)
    assert status["override_active"] is True
    assert status["override_expires_at"] == expires_at
    assert status["mode"] == "override"


def test_an_indefinite_override_is_active_with_no_end(client, panel, panel_is_primary):
    _arm_override(None)
    status = _status(client, panel)
    assert (status["override_active"], status["override_expires_at"]) == (True, None)
    assert status["mode"] == "override"


def test_an_expired_override_is_not_reported(client, panel, panel_is_primary):
    _arm_override((datetime.now(UTC) - timedelta(minutes=1)).isoformat())
    status = _status(client, panel)
    assert (status["override_active"], status["override_expires_at"]) == (False, None)
    assert status["mode"] == "manual"


def test_an_override_on_the_primary_board_does_not_mark_a_secondary_panel(client, panel):
    """The override store drives the primary board only (src/main.py), so a
    panel on any other board must not claim it — that would be a lie."""
    _arm_override((datetime.now(UTC) + timedelta(hours=1)).isoformat())
    status = _status(client, panel)
    assert (status["override_active"], status["override_expires_at"], status["mode"]) == (False, None, "manual")


def test_an_orphaned_panel_has_no_status(client, panel, monkeypatch):
    monkeypatch.setattr("src.panels.routes._find_board", lambda board_id: None)
    response = client.get(f"/panel/{panel['id']}")
    assert response.status_code == 200
    assert response.json()["board_missing"] is True
    assert response.json()["status"] is None


def test_the_frame_does_not_carry_status(client, panel):
    """Status is on the config (polled every 10 s), not the 2 s frame poll."""
    assert "status" not in client.get(f"/panel/{panel['id']}/frame").json()
