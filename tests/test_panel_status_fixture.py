"""The TV apps' panel-status contract fixture, generated from real responses.

``tests/fixtures/panels/panel-status-v1.json`` is what the Android TV and
tvOS apps vendor to test how they read ``status`` on ``GET /panel/{id}``.
Every case here is a real response from this hub, under a frozen clock, so
the TVs can copy the file byte for byte instead of hand-writing bodies.

Only cases the hub produces live here. Client-side cases (an old server, a
missing or skewed ``Date`` header, an unreachable hub, reconnecting) and the
chip wording each TV expects stay with the TV apps.

Regenerate after an intended change with::

    RECORD_PANEL_STATUS_FIXTURE=1 pytest tests/test_panel_status_fixture.py
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FIXTURE = Path(__file__).parent / "fixtures" / "panels" / "panel-status-v1.json"
RECORD = os.environ.get("RECORD_PANEL_STATUS_FIXTURE") == "1"

#: 18:18 PST on Saturday 2026-11-07.
NOW = datetime(2026, 11, 8, 2, 18, 0, tzinfo=UTC)
ZONE = "America/Los_Angeles"
#: The keys a TV decodes from the viewer config. The full response also
#: carries the device model document, which panel status does not concern.
BODY_KEYS = ("id", "name", "board_id", "board_missing", "rows", "cols", "render_style", "status")
QUIET = {"enabled": True, "start_time": "02:00+00:00", "end_time": "15:00+00:00"}  # 18:00-07:00 PST


@pytest.fixture
def frozen(monkeypatch):
    """Freeze every clock panel status reads: the time service and datetime.now in the settings store."""
    from src.time_service import TimeService

    class Clock(TimeService):
        def get_current_utc(self):
            return NOW

        def get_current_time(self, timezone=None):
            return NOW.astimezone(self._default_tz)

    clock = Clock(ZONE)
    monkeypatch.setattr("src.time_service.get_time_service", lambda: clock)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz is not None else NOW.replace(tzinfo=None)

    monkeypatch.setattr("src.settings.service.datetime", FrozenDateTime)


class Hub:
    """One panel on its own board, with the state each case needs."""

    def __init__(self, client: TestClient):
        from src.settings.service import get_settings_service

        self.client = client
        self.settings = get_settings_service()
        self.panel = client.post("/panels", json={"name": "Lobby TV"}).json()
        self.board_id = self.panel["board_id"]
        page = client.post(
            "/v1/pages",
            json={"name": "Evening", "type": "template", "device_type": "panel",
                  "grid_rows": self.panel["rows"], "grid_cols": self.panel["cols"], "template": ["HELLO"]},
        )  # fmt: skip
        assert page.status_code == 201, page.text
        self.page_id = page.json()["id"]

    def reset(self):
        from src.config_manager import get_config_manager

        self.settings.clear_temporary_override(self.board_id)
        self.settings.set_paused(False, board_id=self.board_id)
        self.settings.set_schedule_enabled(False, board_id=self.board_id)
        get_config_manager().set_silence_schedule_for_board(self.board_id, {**QUIET, "enabled": False})

    def schedule(self):
        from src.schedules.models import ScheduleCreate
        from src.schedules.service import get_schedule_service

        self.settings.set_schedule_enabled(True, board_id=self.board_id)
        if not get_schedule_service().list_schedules(board_id=self.board_id):
            get_schedule_service().create_schedule(
                ScheduleCreate(board_id=self.board_id, page_id=self.page_id, start_time="13:00", end_time="21:00")
            )

    def override(self, expires_at: str | None):
        from src.settings.service import TemporaryOverride

        self.settings.set_temporary_override(
            TemporaryOverride(page_id=self.page_id, expires_at=expires_at), board_id=self.board_id
        )

    def silence(self, mode: str):
        from src.config_manager import get_config_manager

        get_config_manager().set_silence_schedule_for_board(self.board_id, {**QUIET, "mode": mode})

    def pause(self):
        self.settings.set_paused(True, board_id=self.board_id)

    def case(self, name: str, *, board_missing: bool = False, monkeypatch=None) -> dict:
        if board_missing:
            monkeypatch.setattr("src.panels.routes._find_board", lambda board_id: None)
        response = self.client.get(f"/panel/{self.panel['id']}")
        if board_missing:
            monkeypatch.undo()
        assert response.status_code == 200, response.text
        body = {key: response.json().get(key) for key in BODY_KEYS}
        # The real response carries the panel's board id even when that board is gone.
        body["id"], body["board_id"] = "lobby", "b1"
        return {
            "name": name,
            "headers": {
                "Date": format_datetime(NOW, usegmt=True),
                "Cache-Control": response.headers.get("cache-control"),
            },
            "body": body,
        }


def _generate(monkeypatch) -> dict:
    from src.api_server import app

    hub = Hub(TestClient(app))
    # Not on the minute: an override's end keeps its seconds (it equals override_expires_at).
    later, earlier = "2026-11-08T05:00:37+00:00", None
    steps = [
        ("manual", lambda: None),
        ("schedule", hub.schedule),
        ("override-with-expiry", lambda: hub.override(later)),
        ("override-until-cancelled", lambda: hub.override(earlier)),
        ("silenced-indicator", lambda: hub.silence("indicator")),
        ("silenced-freeze", lambda: hub.silence("freeze")),
        ("silenced-page", lambda: hub.silence("page")),
        ("paused", hub.pause),
        ("paused+override", lambda: (hub.pause(), hub.override(later))),
        ("override+silenced", lambda: (hub.override(later), hub.silence("indicator"))),
    ]
    cases = []
    for name, arrange in steps:
        hub.reset()
        arrange()
        cases.append(hub.case(name))
    hub.reset()
    cases.append(hub.case("board-missing", board_missing=True, monkeypatch=monkeypatch))
    return {
        "$comment": (
            "Generated by tests/test_panel_status_fixture.py from real GET /panel/{id} responses under a frozen "
            "clock. Each body is the real response projected to the keys a TV decodes, with the panel and board "
            "ids normalised to lobby and b1. The Date header is not captured (the test client sends none): it is "
            "synthesised from the frozen clock, clock.now. Copy byte for byte; do not edit. Client-side cases "
            "(old server, Date header missing or skewed, hub unreachable, reconnected) and expected chip copy "
            "live in each TV app."
        ),
        "protocol": "panel-status-v1",
        "clock": {"now": NOW.isoformat(), "date_header": format_datetime(NOW, usegmt=True), "tz": ZONE},
        "cases": cases,
    }


def _render(document: dict) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def test_the_panel_status_fixture_matches_the_hub(frozen, monkeypatch):
    rendered = _render(_generate(monkeypatch))
    if RECORD:
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(rendered)
    assert FIXTURE.exists(), "run with RECORD_PANEL_STATUS_FIXTURE=1 to create the fixture"
    assert FIXTURE.read_text() == rendered, (
        "panel status changed: regenerate the fixture and re-vendor it in the TV apps"
    )


def test_the_fixture_carries_the_schedule_chips_next_change():
    document = json.loads(FIXTURE.read_text())
    schedule = next(case for case in document["cases"] if case["name"] == "schedule")["body"]["status"]
    # 07b TV chip "Schedule · next change 9:00 PM": 21:00 PST is 05:00 UTC.
    assert (schedule["next_change_at"], schedule["next_change_reason"]) == ("2026-11-08T05:00:00+00:00", "schedule")


def _cases() -> dict:
    return {case["name"]: case["body"] for case in json.loads(FIXTURE.read_text())["cases"]}


def test_the_fixtures_board_missing_case_is_the_real_response():
    cases = _cases()
    missing = cases.pop("board-missing")
    # The hub keeps the panel's board id and marks it missing; a TV reads board_missing.
    assert (missing["board_id"], missing["board_missing"], missing["status"]) == ("b1", True, None)
    assert {(body["board_id"], body["board_missing"]) for body in cases.values()} == {("b1", False)}


def test_the_fixtures_override_end_keeps_its_seconds():
    status = _cases()["override-with-expiry"]["status"]
    assert status["next_change_at"] == status["override_expires_at"] == "2026-11-08T05:00:37+00:00"
