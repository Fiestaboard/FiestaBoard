"""Value-level contract goldens for the /schedules API (Phase 2 §2, slice 2).

These are deliberately *values*, not shapes. The shape corpus in
``tests/golden/responses/schedules.json`` records key sets and type names, so it
cannot see a schedule that came back with the wrong ``page_id``, a
``resolved_start_time`` that stopped tracking ``start_time``, a gap list in the
wrong order, or an error string that stopped naming the missing resource — the
class of regression Phase 1's masking bug proved shape goldens miss.

Every assertion below is a promise this domain makes to the web client, driven
through the real services on an isolated data dir (no ``patch`` on any
collaborator, so the seam retirement later in this PR cannot make these tests
vacuously pass).

All eleven routes are covered, including every 4xx body each one can produce.

Re-pinned by the conventions pass in this same PR. What deliberately changed,
and nothing else:

* ``POST /schedules`` answers **201** (was 200) — conventions doc, "Status
  codes". The body is unchanged apart from ``warnings`` below.
* ``DELETE /schedules/{id}`` answers ``{"id": <deleted id>}`` (was
  ``{"status": "success", "message": "Schedule <id> deleted"}``) — the doc
  offers "200 with the deleted resource id" or "204 with no body"; this domain
  picks the former, as collections did.
* ``PUT /schedules/default-page`` answers the bare
  ``{"default_page_id": ...}`` (was ``{"status": "success",
  "default_page_id": ...}``), which is byte-identical to what ``GET`` on the
  same path answers.
* ``PUT /schedules/enabled`` answers the bare ``{"enabled": ...}`` (was
  ``{"status", "enabled", "message"}``), matching its ``GET``.
* Create/update carry ``warnings`` **always**, empty when clean (the key used
  to be omitted when there was nothing to warn about).
* ``GET /schedules/active/page`` always carries ``current_time``,
  ``current_day`` and ``default_page_id``; they are ``null`` in manual mode
  (the manual branch used to omit them, so one route served two key sets).
* The three untyped ``dict`` bodies became Pydantic models, so a missing or
  wrongly-typed field is FastAPI's standard **422** instead of a hand-rolled
  400. The *rejection* is unchanged — notably ``{"enabled": "yes"}`` is still
  refused, via ``StrictBool``, rather than coerced to ``true``.

Every other value assertion — ids, times, resolved times, list ordering and
total, gap and overlap contents, error strings, and the failure status codes on
the 404 paths — is byte-identical to the pre-conversion recording. None was
weakened.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

MISSING_ID = "00000000-dead-beef-0000-000000000000"
GHOST_BOARD = "ghost-board"


@pytest.fixture
def client(_isolated_data_dir):
    """A TestClient whose services all resolve into this test's temp data dir."""
    from src.api_server import app

    return TestClient(app)


@pytest.fixture
def board_id(client) -> str:
    """The id of the single board a fresh install ships with."""
    response = client.get("/settings/board")
    assert response.status_code == 200, response.text
    return response.json()["boards"][0]["id"]


def _seed_page(client: TestClient, name: str, first_line: str) -> str:
    response = client.post(
        "/pages",
        json={
            "name": name,
            "type": "template",
            "device_type": "flagship",
            "template": [first_line, "", "", "", "", ""],
        },
    )
    # RE-PINNED (pages slice): POST /pages now returns 201 with the created
    # page as a bare body, replacing the 200 + {"page": {...}} envelope.
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def page_id(client) -> str:
    return _seed_page(client, "Contract Page A", "AAA")


def _create(client: TestClient, **body) -> dict:
    """POST /schedules and return the created schedule.

    The one place that knows the create envelope, so re-pinning the envelope is
    a one-line change instead of a sweep.
    """
    response = client.post("/schedules", json=body)
    assert response.status_code == 201, response.text  # RE-PINNED: 201 (was 200)
    return response.json()


# ── POST /schedules ─────────────────────────────────────────────────────────


def test_create_returns_the_created_schedule_with_its_values(client, page_id):
    response = client.post("/schedules", json={"page_id": page_id, "start_time": "09:00", "end_time": "17:00"})

    # RE-PINNED: 201 (was 200). The body is unchanged apart from `warnings`.
    assert response.status_code == 201, response.text
    schedule = response.json()
    assert schedule["page_id"] == page_id
    assert schedule["start_time"] == "09:00"
    assert schedule["end_time"] == "17:00"
    assert schedule["board_id"] == ""
    assert schedule["day_pattern"] == "all"
    assert schedule["custom_days"] is None
    assert schedule["enabled"] is True
    assert schedule["recurrence_type"] == "weekly"
    assert schedule["start_type"] == "fixed"
    assert schedule["end_type"] == "fixed"
    assert schedule["start_sun_offset"] == 0
    assert schedule["end_sun_offset"] == 0
    assert schedule["updated_at"] is None
    assert schedule["warnings"] == []  # RE-PINNED: always present, was omitted when clean


def test_create_mints_an_id_and_a_created_at(client, page_id):
    schedule = _create(client, page_id=page_id, start_time="09:00", end_time="17:00")

    assert schedule["id"]
    assert schedule["created_at"]


def test_create_resolves_fixed_times_to_themselves(client, page_id):
    """``resolved_*`` is what the client renders; for fixed schedules it must
    equal the stored time, not a recomputed one."""
    schedule = _create(client, page_id=page_id, start_time="09:00", end_time="17:00")

    assert schedule["resolved_start_time"] == "09:00"
    assert schedule["resolved_end_time"] == "17:00"


def test_create_keeps_an_open_ended_schedule_open_ended(client, page_id):
    schedule = _create(client, page_id=page_id, start_time="09:00", end_time=None)

    assert schedule["end_time"] is None
    assert schedule["resolved_end_time"] is None


def test_create_rejects_a_zero_duration_schedule_with_400(client, page_id):
    response = client.post("/schedules", json={"page_id": page_id, "start_time": "09:00", "end_time": "09:00"})

    assert response.status_code == 400
    assert response.json() == {
        "detail": (
            "Invalid schedule configuration: ['end_time must be different from start_time (zero-duration schedule)']"
        )
    }


def test_create_rejects_an_unknown_board_with_404_naming_the_board(client, page_id):
    response = client.post(
        "/schedules",
        json={"page_id": page_id, "start_time": "09:00", "end_time": "17:00", "board_id": GHOST_BOARD},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": f"Board not found: {GHOST_BOARD}"}


def test_create_rejects_a_malformed_start_time_with_422(client, page_id):
    response = client.post("/schedules", json={"page_id": page_id, "start_time": "9am", "end_time": "17:00"})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "start_time"]


def test_create_accepts_the_installs_real_board_id(client, page_id, board_id):
    schedule = _create(client, page_id=page_id, start_time="09:00", end_time="17:00", board_id=board_id)

    assert schedule["board_id"] == board_id


# ── GET /schedules ──────────────────────────────────────────────────────────


def test_list_is_empty_on_a_fresh_install(client):
    response = client.get("/schedules")

    assert response.status_code == 200
    assert response.json() == {"schedules": [], "total": 0, "default_page_id": None, "enabled": False}


def test_list_returns_the_created_schedules_and_a_matching_total(client, page_id):
    first = _create(client, page_id=page_id, start_time="06:00", end_time="09:00")
    second = _create(client, page_id=page_id, start_time="09:00", end_time="17:00")

    body = client.get("/schedules").json()

    assert body["total"] == 2
    assert {s["id"] for s in body["schedules"]} == {first["id"], second["id"]}
    assert [s["start_time"] for s in sorted(body["schedules"], key=lambda s: s["start_time"])] == ["06:00", "09:00"]


def test_list_reports_the_default_page_and_the_enabled_flag(client, page_id):
    client.put("/schedules/default-page", json={"page_id": page_id})
    client.put("/schedules/enabled", json={"enabled": True})

    body = client.get("/schedules").json()

    assert body["default_page_id"] == page_id
    assert body["enabled"] is True


def test_list_scoped_to_the_primary_board_also_returns_legacy_unscoped_entries(client, page_id, board_id):
    """``board_id=""`` is the pre-multi-board sentinel for "the default board",
    so the primary board's listing has to include entries stored under it —
    otherwise every schedule created before multi-board support would vanish
    from the UI the moment a board id is passed."""
    scoped = _create(client, page_id=page_id, start_time="06:00", end_time="09:00", board_id=board_id)
    legacy = _create(client, page_id=page_id, start_time="09:00", end_time="17:00")

    body = client.get("/schedules", params={"board_id": board_id}).json()

    assert {s["id"] for s in body["schedules"]} == {scoped["id"], legacy["id"]}
    assert body["total"] == 2


def test_list_for_an_unknown_board_falls_back_to_empty_rather_than_404(client, page_id):
    """Documented asymmetry — see the board_id note in API_CONVENTIONS.md.
    Reads fall back; only writes 404."""
    _create(client, page_id=page_id, start_time="09:00", end_time="17:00")

    response = client.get("/schedules", params={"board_id": GHOST_BOARD})

    assert response.status_code == 200
    assert response.json()["schedules"] == []
    assert response.json()["total"] == 0


def test_wildcard_listing_returns_every_board(client, page_id, board_id):
    scoped = _create(client, page_id=page_id, start_time="06:00", end_time="09:00", board_id=board_id)
    unscoped = _create(client, page_id=page_id, start_time="09:00", end_time="17:00")

    body = client.get("/schedules", params={"board_id": "*"}).json()

    assert {s["id"] for s in body["schedules"]} == {scoped["id"], unscoped["id"]}
    assert body["total"] == 2


def test_wildcard_listing_reports_no_default_page(client, page_id):
    """``default_page_id`` is per-board, so the cross-board listing has none."""
    client.put("/schedules/default-page", json={"page_id": page_id})

    assert client.get("/schedules", params={"board_id": "*"}).json()["default_page_id"] is None


def test_wildcard_listing_does_not_claim_schedule_mode_is_off(client, page_id):
    """RE-PINNED (bug fix, this PR): ``enabled`` is ``null``, was hardcoded ``false``.

    ``enabled`` is a per-board flag, so the cross-board listing cannot answer
    it — exactly like ``default_page_id``, which the same branch already
    answers with ``null``. Hardcoding ``false`` made "not applicable here"
    indistinguishable from "schedule mode is off everywhere", which is a lie a
    client cannot detect: with schedule mode ON for the only board, the
    wildcard listing still said ``false``.
    """
    client.put("/schedules/enabled", json={"enabled": True})

    assert client.get("/schedules/enabled").json()["enabled"] is True
    assert client.get("/schedules", params={"board_id": "*"}).json()["enabled"] is None


# ── GET /schedules/{schedule_id} ────────────────────────────────────────────


def test_get_returns_the_schedule_by_id(client, page_id):
    created = _create(client, page_id=page_id, start_time="09:00", end_time="17:00")

    response = client.get(f"/schedules/{created['id']}")

    assert response.status_code == 200
    # RE-PINNED: the read carries no `warnings`. Page<->board compatibility is
    # computed on write, against the payload being written; recomputing it on
    # every read would be a different (and much more expensive) claim.
    assert response.json() == {k: v for k, v in created.items() if k != "warnings"}


def test_get_missing_schedule_404s_naming_the_id(client):
    response = client.get(f"/schedules/{MISSING_ID}")

    assert response.status_code == 404
    assert response.json() == {"detail": f"Schedule not found: {MISSING_ID}"}


# ── PUT /schedules/{schedule_id} ────────────────────────────────────────────


def test_update_applies_only_the_supplied_fields(client, page_id):
    created = _create(client, page_id=page_id, start_time="09:00", end_time="17:00")

    response = client.put(f"/schedules/{created['id']}", json={"start_time": "10:00"})

    assert response.status_code == 200
    updated = response.json()
    assert updated["id"] == created["id"]
    assert updated["start_time"] == "10:00"
    assert updated["end_time"] == "17:00"
    assert updated["page_id"] == page_id


def test_update_stamps_updated_at_and_re_resolves_the_times(client, page_id):
    created = _create(client, page_id=page_id, start_time="09:00", end_time="17:00")

    updated = client.put(f"/schedules/{created['id']}", json={"start_time": "10:00"}).json()

    assert updated["updated_at"] is not None
    assert updated["created_at"] == created["created_at"]
    assert updated["resolved_start_time"] == "10:00"


def test_update_missing_schedule_404s_naming_the_id(client):
    response = client.put(f"/schedules/{MISSING_ID}", json={"start_time": "10:00"})

    assert response.status_code == 404
    assert response.json() == {"detail": f"Schedule not found: {MISSING_ID}"}


def test_update_rejects_an_unknown_board_with_404_naming_the_board(client, page_id):
    created = _create(client, page_id=page_id, start_time="09:00", end_time="17:00")

    response = client.put(f"/schedules/{created['id']}", json={"board_id": GHOST_BOARD})

    assert response.status_code == 404
    assert response.json() == {"detail": f"Board not found: {GHOST_BOARD}"}


def test_update_to_a_zero_duration_window_400s(client, page_id):
    created = _create(client, page_id=page_id, start_time="09:00", end_time="17:00")

    response = client.put(f"/schedules/{created['id']}", json={"end_time": "09:00"})

    assert response.status_code == 400
    assert "zero-duration schedule" in response.json()["detail"]


# ── DELETE /schedules/{schedule_id} ─────────────────────────────────────────


def test_delete_removes_the_schedule(client, page_id):
    created = _create(client, page_id=page_id, start_time="09:00", end_time="17:00")

    response = client.delete(f"/schedules/{created['id']}")

    assert response.status_code == 200
    # RE-PINNED: the deleted id (was {"status": "success", "message": ...}).
    assert response.json() == {"id": created["id"]}
    assert client.get(f"/schedules/{created['id']}").status_code == 404


def test_delete_missing_schedule_404s_naming_the_id(client):
    response = client.delete(f"/schedules/{MISSING_ID}")

    assert response.status_code == 404
    assert response.json() == {"detail": f"Schedule not found: {MISSING_ID}"}


# ── POST /schedules/validate ────────────────────────────────────────────────


def test_validate_reports_a_valid_empty_schedule_with_one_all_day_gap(client):
    response = client.post("/schedules/validate")

    assert response.status_code == 200
    assert response.json() == {
        "valid": True,
        "overlaps": [],
        "gaps": [
            {
                "start_time": "00:00",
                "end_time": "23:59",
                "days": ["friday", "monday", "saturday", "sunday", "thursday", "tuesday", "wednesday"],
            }
        ],
    }


def test_validate_names_both_sides_of_an_overlap(client, page_id):
    first = _create(client, page_id=page_id, start_time="09:00", end_time="12:00")
    second = _create(client, page_id=page_id, start_time="11:00", end_time="14:00")

    body = client.post("/schedules/validate").json()

    assert body["valid"] is False
    assert len(body["overlaps"]) == 1
    overlap = body["overlaps"][0]
    assert {overlap["schedule1_id"], overlap["schedule2_id"]} == {first["id"], second["id"]}
    assert overlap["conflict_description"]


def test_validate_reports_the_gaps_around_a_single_schedule(client, page_id):
    _create(client, page_id=page_id, start_time="09:00", end_time="17:00")

    body = client.post("/schedules/validate").json()

    assert body["valid"] is True
    assert [(gap["start_time"], gap["end_time"]) for gap in body["gaps"]] == [
        ("00:00", "09:00"),
        ("17:00", "23:59"),
    ]


def test_validate_scopes_to_the_board_in_the_body(client, page_id, board_id):
    _create(client, page_id=page_id, start_time="09:00", end_time="17:00", board_id=board_id)

    unscoped = client.post("/schedules/validate", json={"board_id": ""}).json()
    scoped = client.post("/schedules/validate", json={"board_id": board_id}).json()

    assert [(g["start_time"], g["end_time"]) for g in unscoped["gaps"]] == [("00:00", "23:59")]
    assert [(g["start_time"], g["end_time"]) for g in scoped["gaps"]] == [("00:00", "09:00"), ("17:00", "23:59")]


# ── GET / PUT /schedules/default-page ───────────────────────────────────────


def test_default_page_is_null_on_a_fresh_install(client):
    response = client.get("/schedules/default-page")

    assert response.status_code == 200
    assert response.json() == {"default_page_id": None}


def test_set_default_page_stores_it_and_reads_back(client, page_id):
    response = client.put("/schedules/default-page", json={"page_id": page_id})

    assert response.status_code == 200
    # RE-PINNED: bare body (was {"status": "success", "default_page_id": ...}),
    # byte-identical to what GET on the same path answers.
    assert response.json() == {"default_page_id": page_id}
    assert client.get("/schedules/default-page").json() == {"default_page_id": page_id}


def test_set_default_page_to_null_clears_it(client, page_id):
    client.put("/schedules/default-page", json={"page_id": page_id})

    response = client.put("/schedules/default-page", json={"page_id": None})

    assert response.status_code == 200
    assert response.json() == {"default_page_id": None}  # RE-PINNED: bare body
    assert client.get("/schedules/default-page").json() == {"default_page_id": None}


def test_set_default_page_without_page_id_422s(client):
    """RE-PINNED: 422 (was a hand-rolled 400 "page_id parameter required").

    The body is a Pydantic model now, so a missing required field is FastAPI's
    standard validation error. The request is still refused, and nothing is
    written.
    """
    response = client.put("/schedules/default-page", json={})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "page_id"]
    assert client.get("/schedules/default-page").json() == {"default_page_id": None}


def test_set_default_page_to_an_unknown_page_404s_naming_the_page(client):
    response = client.put("/schedules/default-page", json={"page_id": MISSING_ID})

    assert response.status_code == 404
    assert response.json() == {"detail": f"Page not found: {MISSING_ID}"}


def test_set_default_page_to_an_unknown_collection_404s_naming_the_collection(client):
    collection_ref = f"collection:{MISSING_ID}"

    response = client.put("/schedules/default-page", json={"page_id": collection_ref})

    assert response.status_code == 404
    assert response.json() == {"detail": f"Collection not found: {collection_ref}"}


def test_set_default_page_for_an_unknown_board_404s_and_stores_nothing(client, page_id):
    response = client.put("/schedules/default-page", json={"page_id": page_id, "board_id": GHOST_BOARD})

    assert response.status_code == 404
    assert response.json() == {"detail": f"Board not found: {GHOST_BOARD}"}
    assert client.get("/schedules/default-page", params={"board_id": GHOST_BOARD}).json() == {"default_page_id": None}


def test_default_page_read_for_an_unknown_board_falls_back_rather_than_404(client):
    response = client.get("/schedules/default-page", params={"board_id": GHOST_BOARD})

    assert response.status_code == 200
    assert response.json() == {"default_page_id": None}


# ── GET / PUT /schedules/enabled ────────────────────────────────────────────


def test_schedule_mode_is_off_on_a_fresh_install(client):
    response = client.get("/schedules/enabled")

    assert response.status_code == 200
    assert response.json() == {"enabled": False}


def test_set_schedule_enabled_turns_it_on_and_reads_back(client):
    response = client.put("/schedules/enabled", json={"enabled": True})

    assert response.status_code == 200
    # RE-PINNED: bare body (was {"status", "enabled", "message"}), matching GET.
    assert response.json() == {"enabled": True}
    assert client.get("/schedules/enabled").json() == {"enabled": True}


def test_set_schedule_enabled_turns_it_off_again(client):
    client.put("/schedules/enabled", json={"enabled": True})

    response = client.put("/schedules/enabled", json={"enabled": False})

    assert response.status_code == 200
    assert response.json() == {"enabled": False}  # RE-PINNED: bare body
    assert client.get("/schedules/enabled").json() == {"enabled": False}


def test_set_schedule_enabled_without_the_flag_422s(client):
    """RE-PINNED: 422 (was a hand-rolled 400 "enabled parameter required")."""
    response = client.put("/schedules/enabled", json={})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "enabled"]
    assert client.get("/schedules/enabled").json() == {"enabled": False}


def test_set_schedule_enabled_rejects_a_non_boolean(client):
    """A truthy string must not be coerced into "on" — that would silently turn
    schedule mode on for a client that sent the wrong type.

    RE-PINNED: 422 (was a hand-rolled 400 "enabled must be boolean"). The
    rejection itself is what matters and is unchanged — Pydantic's lax mode
    *would* have coerced "yes" to True, so the model declares ``StrictBool``.
    """
    response = client.put("/schedules/enabled", json={"enabled": "yes"})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "enabled"]
    assert client.get("/schedules/enabled").json() == {"enabled": False}


def test_set_schedule_enabled_for_an_unknown_board_404s_and_writes_nothing(client):
    response = client.put("/schedules/enabled", json={"enabled": True, "board_id": GHOST_BOARD})

    assert response.status_code == 404
    assert response.json() == {"detail": f"Board not found: {GHOST_BOARD}"}
    assert client.get("/schedules/enabled", params={"board_id": GHOST_BOARD}).json() == {"enabled": False}


def test_enabled_read_for_an_unknown_board_falls_back_rather_than_404(client):
    response = client.get("/schedules/enabled", params={"board_id": GHOST_BOARD})

    assert response.status_code == 200
    assert response.json() == {"enabled": False}


# ── GET /schedules/active/page ──────────────────────────────────────────────


def test_active_page_reports_the_manual_page_when_schedule_mode_is_off(client, page_id):
    client.put("/settings/active-page", json={"page_id": page_id})

    response = client.get("/schedules/active/page")

    assert response.status_code == 200
    body = response.json()
    assert body["page_id"] == page_id
    assert body["resolved_page_id"] == page_id
    assert body["resolved_next_check_seconds"] is None
    assert body["source"] == "manual"
    assert body["schedule_enabled"] is False


def test_active_page_nulls_the_clock_fields_in_manual_mode(client, page_id):
    """RE-PINNED: the three fields are present and null; they used to be absent.

    One route served two key sets, so a client could not tell "manual mode" from
    "this server does not report the current day". They are declared on
    ``ActiveScheduleResponse`` now, and null is the manual-mode answer.
    """
    client.put("/settings/active-page", json={"page_id": page_id})

    body = client.get("/schedules/active/page").json()

    assert body["current_time"] is None
    assert body["current_day"] is None
    assert body["default_page_id"] is None


def test_active_page_reports_the_scheduled_page_when_schedule_mode_is_on(client, page_id):
    created = _create(client, page_id=page_id, start_time="00:00", end_time=None)
    client.put("/schedules/enabled", json={"enabled": True})

    body = client.get("/schedules/active/page").json()

    assert body["page_id"] == page_id
    assert body["resolved_page_id"] == page_id
    assert body["source"] == "schedule"
    assert body["schedule_enabled"] is True
    assert len(body["current_time"]) == 5
    assert body["current_day"] in {
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    }
    assert created["page_id"] == body["page_id"]


def test_active_page_reports_source_none_when_nothing_is_scheduled(client):
    client.put("/schedules/enabled", json={"enabled": True})

    body = client.get("/schedules/active/page").json()

    assert body["page_id"] is None
    assert body["source"] == "none"
    assert body["schedule_enabled"] is True


def test_active_page_carries_the_inactive_temporary_override_block(client, page_id):
    client.put("/settings/active-page", json={"page_id": page_id})

    override = client.get("/schedules/active/page").json()["temporary_override"]

    assert override == {
        "active": False,
        "page_id": None,
        "expires_at": None,
        "remaining_seconds": None,
        "revert_mode": None,
        "revert_page_id": None,
        "template": None,
        "line_metadata": None,
        "device_type": None,
        "notes_wide": None,
        "notes_tall": None,
    }


def test_active_page_carries_an_active_temporary_override(client, page_id):
    client.post("/settings/temporary-override", json={"page_id": page_id, "duration_minutes": 30})

    override = client.get("/schedules/active/page").json()["temporary_override"]

    assert override["active"] is True
    assert override["page_id"] == page_id
    assert override["revert_mode"] == "schedule"
    assert override["remaining_seconds"] is not None
