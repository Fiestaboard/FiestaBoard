"""Value-level contract goldens for the consumer-facing ``/v1`` API.

These routes are new, so there is no "before" to preserve — which makes this
file the contract rather than a record of one. Every assertion is a promise
to a consumer this repo cannot see and cannot update in lockstep, so it is
pinned by **value**: exact status codes, exact ``detail`` strings, exact body
keys. A shape golden would not see a ``sent`` that stopped meaning "flaps
moved", and that is the whole point of the surface.

Three decisions are pinned here on purpose, because they are the ones a
future change is most likely to unpick:

1. **A v1 write honours the install's output target.** With the target set to
   UI-only nothing reaches the board and the response says so — ``sent:
   false`` plus a ``reason``. Today ``POST /pages/{id}/send`` honours the
   target and ``POST /send-message`` ignores it; v1 has one rule.
2. **The write goes through** :func:`src.ops.executors.send_message`, so the
   silence, pause, throttle and out-of-band-bookkeeping sequence is one
   implementation. ``test_paused_board_refuses_the_write`` and
   ``test_a_write_the_send_floor_dropped_is_a_429`` are the gates observed
   through v1; if the executor's sequence changes, they change.
3. **``primary`` is a board id.** Every ``/v1/boards/...`` path accepts it,
   and it resolves to the same board a real id does.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

#: The executor resolves the DisplayService through ``src.api_server``; the
#: routes resolve it through ``src.display_runtime``. conftest's autouse
#: forwarder makes one stub cover both, but both are named here so the file
#: reads as what it patches.
SERVICE = "src.api_server.get_service"
RUNTIME_SERVICE = "src.display_runtime.get_service"

FLAGSHIP_ROWS, FLAGSHIP_COLS = 6, 22
NOTE_ROWS, NOTE_COLS = 3, 15

BLANK_FLAGSHIP = [[0] * FLAGSHIP_COLS for _ in range(FLAGSHIP_ROWS)]


@pytest.fixture
def client(_isolated_data_dir):
    from src.api_server import app

    return TestClient(app)


@pytest.fixture
def boards(client):
    """A flagship primary board and a note secondary, both real settings rows."""
    from src.settings.service import get_settings_service

    settings = get_settings_service()
    stored = settings.set_boards(
        [
            {"device_type": "flagship", "name": "Kitchen"},
            {"device_type": "note", "name": "Hallway"},
        ]
    )
    return stored.boards[0]["id"], stored.boards[1]["id"]


def _board_client(*, render=(True, True), throttled=False):
    client = Mock()
    client.render.return_value = render
    client.last_send_throttled = throttled
    client.min_send_interval_ms = 15000
    client._last_characters = None
    return client


@pytest.fixture
def board_client():
    """A reachable board client behind a stubbed DisplayService."""
    client = _board_client()
    service = Mock()
    service.get_board_client.return_value = client
    service.vb_client = client
    runtime = Mock()
    runtime.polled_characters = None
    runtime.polled_at = None
    runtime.client = client
    runtime.last_active_page_content = None
    service.get_runtime.return_value = runtime
    with patch(SERVICE, return_value=service), patch(RUNTIME_SERVICE, return_value=service):
        yield client


def _seed_page(client: TestClient, name: str = "Contract Page") -> str:
    response = client.post(
        "/v1/pages",
        json={
            "name": name,
            "type": "template",
            "device_type": "flagship",
            "template": ["HI", "", "", "", "", ""],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


# ── the surface itself ──────────────────────────────────────────────────────


def test_v1_publishes_exactly_thirty_one_operations():
    """The contract is 31 operations. A 32nd is a decision, not a side effect."""
    from tests.test_route_inventory import build_route_inventory

    operations = [
        f"{method} {record['path']}"
        for record in build_route_inventory()
        if record["path"].startswith("/v1")
        for method in record["methods"]
    ]

    assert sorted(operations) == sorted(
        [
            "GET /v1/boards",
            "GET /v1/boards/{board}",
            "PATCH /v1/boards/{board}",
            "POST /v1/boards/{board}/message",
            "DELETE /v1/boards/{board}/message",
            "PUT /v1/boards/{board}/active-page",
            "GET /v1/pages",
            "POST /v1/pages",
            "GET /v1/pages/{page_id}",
            "PUT /v1/pages/{page_id}",
            "DELETE /v1/pages/{page_id}",
            "GET /v1/schedules",
            "POST /v1/schedules",
            "GET /v1/schedules/{schedule_id}",
            "PUT /v1/schedules/{schedule_id}",
            "DELETE /v1/schedules/{schedule_id}",
            "GET /v1/collections",
            "POST /v1/collections",
            "GET /v1/collections/{collection_id}",
            "PUT /v1/collections/{collection_id}",
            "DELETE /v1/collections/{collection_id}",
            "GET /v1/plugins",
            "GET /v1/plugins/{plugin_id}",
            "PATCH /v1/plugins/{plugin_id}",
            "GET /v1/plugins/{plugin_id}/data",
            "POST /v1/plugins/{plugin_id}/receive",
            "GET /v1/variables",
            "POST /v1/render",
            "GET /v1/functions",
            "GET /v1/health",
            "GET /v1/status",
        ]
    )


def test_every_v1_operation_has_a_written_summary_and_description():
    """187 of 187 existing summaries are FastAPI's function names. Not here."""
    from src.api_server import app

    schema = app.openapi()
    missing = []
    for path, operations in schema["paths"].items():
        if not path.startswith("/v1"):
            continue
        for method, operation in operations.items():
            summary = operation.get("summary", "")
            description = operation.get("description", "")
            # An auto-generated summary is the title-cased function name, so
            # it never contains a lowercase connecting word.
            if len(summary.split()) < 3 or len(description) < 80:
                missing.append(f"{method.upper()} {path}")

    assert missing == []


def test_the_schema_declares_the_authentication_the_middleware_enforces():
    """Measured on `next`: no securitySchemes at all, so auth was undiscoverable."""
    from src.api_server import app

    schema = app.openapi()

    assert schema["components"]["securitySchemes"]["apiToken"]["type"] == "http"
    assert schema["components"]["securitySchemes"]["apiToken"]["scheme"] == "bearer"
    assert schema["components"]["securitySchemes"]["session"]["type"] == "apiKey"
    assert schema["components"]["securitySchemes"]["session"]["in"] == "cookie"
    assert schema["security"] == [{"apiToken": []}, {"session": []}]


# ── boards: read ────────────────────────────────────────────────────────────


def test_list_boards_projects_the_fields_a_consumer_needs(client, boards):
    primary_id, secondary_id = boards

    response = client.get("/v1/boards")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["boards"][0] == {
        "id": primary_id,
        "name": "Kitchen",
        "device_type": "flagship",
        "rows": FLAGSHIP_ROWS,
        "cols": FLAGSHIP_COLS,
        "is_primary": True,
        "paused": False,
        "schedule_enabled": False,
    }
    assert body["boards"][1]["id"] == secondary_id
    assert body["boards"][1]["is_primary"] is False
    assert (body["boards"][1]["rows"], body["boards"][1]["cols"]) == (NOTE_ROWS, NOTE_COLS)


def test_list_boards_never_serves_board_credentials(client, boards):
    """A consumer projection, not the stored entry. Not even masked secrets."""
    response = client.get("/v1/boards")

    for board in response.json()["boards"]:
        assert set(board) == {
            "id",
            "name",
            "device_type",
            "rows",
            "cols",
            "is_primary",
            "paused",
            "schedule_enabled",
        }


def test_primary_resolves_to_the_same_board_as_its_id(client, boards):
    primary_id, _ = boards

    by_alias = client.get("/v1/boards/primary")
    by_id = client.get(f"/v1/boards/{primary_id}")

    assert by_alias.status_code == 200
    assert by_alias.json() == by_id.json()
    assert by_alias.json()["id"] == primary_id


def test_reading_an_unknown_board_is_a_404(client, boards):
    response = client.get("/v1/boards/no-such-board")

    assert response.status_code == 404
    assert response.json() == {"detail": "Board not found: no-such-board"}


def test_primary_on_an_install_with_no_boards_is_a_404(client):
    from src.settings.service import get_settings_service

    get_settings_service()._board.boards = []

    response = client.get("/v1/boards/primary")

    assert response.status_code == 404
    assert response.json() == {"detail": "No board is configured on this install."}


def test_get_board_merges_the_three_reads_into_one_answer(client, boards, board_client):
    """current-message + settings/active-page + schedules/active/page, once."""
    primary_id, _ = boards
    page_id = _seed_page(client)
    client.put("/v1/boards/primary/active-page", json={"page_id": page_id})

    response = client.get("/v1/boards/primary")

    assert response.status_code == 200
    body = response.json()
    assert body["active_page_id"] == page_id
    assert body["resolved_page_id"] == page_id
    assert body["source"] == "manual"
    assert body["scheduled_page_id"] is None
    assert body["id"] == primary_id
    assert set(body) == {
        "id",
        "name",
        "device_type",
        "rows",
        "cols",
        "is_primary",
        "paused",
        "schedule_enabled",
        "characters",
        "text",
        "read_at",
        "active_page_id",
        "scheduled_page_id",
        "resolved_page_id",
        "source",
        "default_page_id",
        "override_expires_at",
    }


def test_get_board_reports_the_flaps_currently_on_it(client, boards):
    grid = [[63] * FLAGSHIP_COLS for _ in range(FLAGSHIP_ROWS)]
    service = Mock()
    runtime = Mock()
    runtime.polled_characters = grid
    runtime.polled_at = 1_700_000_000.0
    runtime.client = _board_client()
    service.get_runtime.return_value = runtime
    with patch(SERVICE, return_value=service), patch(RUNTIME_SERVICE, return_value=service):
        response = client.get("/v1/boards/primary")

    assert response.status_code == 200
    assert response.json()["characters"] == grid
    assert response.json()["read_at"] == "2023-11-14T22:13:20+00:00"


# ── boards: patch ───────────────────────────────────────────────────────────


def test_patch_applies_only_the_fields_sent(client, boards):
    response = client.patch("/v1/boards/primary", json={"paused": True})

    assert response.status_code == 200
    assert response.json()["paused"] is True
    assert response.json()["name"] == "Kitchen"
    assert response.json()["schedule_enabled"] is False


def test_patch_renames_a_board(client, boards):
    response = client.patch("/v1/boards/primary", json={"name": "Living Room"})

    assert response.status_code == 200
    assert response.json()["name"] == "Living Room"
    assert client.get("/v1/boards").json()["boards"][0]["name"] == "Living Room"


def test_patch_sets_the_schedule_gap_page(client, boards):
    page_id = _seed_page(client)

    response = client.patch("/v1/boards/primary", json={"default_page_id": page_id})

    assert response.status_code == 200
    assert response.json()["default_page_id"] == page_id


def test_patch_with_an_unknown_default_page_is_a_404(client, boards):
    response = client.patch("/v1/boards/primary", json={"default_page_id": "nope"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Page not found: nope"}


def test_patch_rejects_a_coerced_boolean(client, boards):
    """StrictBool: "yes" must not silently stop the board (the #1887 hole)."""
    response = client.patch("/v1/boards/primary", json={"paused": "yes"})

    assert response.status_code == 422


# ── boards: the front door ──────────────────────────────────────────────────


def test_text_is_wrapped_to_the_board_and_sent(client, boards, board_client):
    primary_id, _ = boards

    response = client.post("/v1/boards/primary/message", json={"text": "Hello World"})

    assert response.status_code == 200
    body = response.json()
    assert body["sent"] is True
    assert body["board_id"] == primary_id
    assert body["text"] == "Hello World"
    assert body["expires_at"] is None
    assert body["reason"] is None
    assert len(body["characters"]) == FLAGSHIP_ROWS
    assert all(len(row) == FLAGSHIP_COLS for row in body["characters"])
    assert board_client.render.called


def test_the_message_reaches_a_secondary_board(client, boards, board_client):
    """The defect this API exists to fix: POST /send-message cannot address board 2."""
    _, secondary_id = boards

    response = client.post(f"/v1/boards/{secondary_id}/message", json={"text": "Board two"})

    assert response.status_code == 200
    assert response.json()["sent"] is True
    assert response.json()["board_id"] == secondary_id
    grid = response.json()["characters"]
    assert (len(grid), len(grid[0])) == (NOTE_ROWS, NOTE_COLS)


def test_fill_paints_the_whole_board_with_one_code(client, boards, board_client):
    response = client.post("/v1/boards/primary/message", json={"fill": 63})

    assert response.status_code == 200
    assert response.json()["characters"] == [[63] * FLAGSHIP_COLS for _ in range(FLAGSHIP_ROWS)]


def test_fill_zero_blanks_the_board(client, boards, board_client):
    response = client.post("/v1/boards/primary/message", json={"fill": 0})

    assert response.status_code == 200
    assert response.json()["characters"] == BLANK_FLAGSHIP


def test_a_raw_grid_is_sent_verbatim(client, boards, board_client):
    grid = [[i % 26 + 1] * FLAGSHIP_COLS for i in range(FLAGSHIP_ROWS)]

    response = client.post("/v1/boards/primary/message", json={"characters": grid})

    assert response.status_code == 200
    assert response.json()["characters"] == grid
    assert board_client.render.call_args.args[0] == grid


def test_a_grid_of_the_wrong_size_is_a_400(client, boards, board_client):
    response = client.post("/v1/boards/primary/message", json={"characters": [[0, 0, 0]]})

    assert response.status_code == 400
    assert response.json() == {"detail": "characters must be a 6x22 grid for this board, got 1x3"}


def test_an_out_of_range_flap_code_is_a_422(client, boards, board_client):
    response = client.post("/v1/boards/primary/message", json={"fill": 99})

    assert response.status_code == 422


def test_a_boolean_flap_code_is_rejected(client, boards, board_client):
    """StrictInt: isinstance(True, int) is true, and true must not mean code 1."""
    response = client.post("/v1/boards/primary/message", json={"fill": True})

    assert response.status_code == 422


def test_a_saved_page_is_rendered_and_sent(client, boards, board_client):
    page_id = _seed_page(client)

    response = client.post("/v1/boards/primary/message", json={"page_id": page_id})

    assert response.status_code == 200
    assert response.json()["sent"] is True
    assert response.json()["text"].splitlines()[0].strip() == "HI"


def test_sending_an_unknown_page_is_a_404(client, boards, board_client):
    response = client.post("/v1/boards/primary/message", json={"page_id": "nope"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Page not found: nope"}


def test_supplying_two_content_fields_is_a_422(client, boards, board_client):
    response = client.post("/v1/boards/primary/message", json={"text": "a", "fill": 1})

    assert response.status_code == 422
    assert "Supply exactly one of text, lines, characters, page_id or fill" in response.text


def test_supplying_no_content_field_is_a_422(client, boards, board_client):
    response = client.post("/v1/boards/primary/message", json={})

    assert response.status_code == 422
    assert "got none" in response.text


# ── boards: what "sent" actually means ──────────────────────────────────────


def test_a_ui_only_output_target_writes_nothing_and_says_so(client, boards, board_client):
    """Decision 1: v1 writes honour the global output target, and report it."""
    from src.settings.service import get_settings_service

    get_settings_service().set_output_target("ui")

    response = client.post("/v1/boards/primary/message", json={"text": "Hello"})

    assert response.status_code == 200
    assert response.json()["sent"] is False
    assert response.json()["reason"] == ("The install's output target is UI only, so nothing was written to the board.")
    assert response.json()["characters"] != []
    board_client.render.assert_not_called()


def test_unchanged_content_is_reported_not_claimed_as_sent(client, boards):
    client_stub = _board_client(render=(True, False))
    service = Mock()
    service.get_board_client.return_value = client_stub
    service.vb_client = client_stub
    with patch(SERVICE, return_value=service), patch(RUNTIME_SERVICE, return_value=service):
        response = client.post("/v1/boards/primary/message", json={"text": "Hello"})

    assert response.status_code == 200
    assert response.json()["sent"] is False
    assert response.json()["reason"] == (
        "The board already shows this exact content. Send force=true to write it anyway."
    )


def test_force_is_passed_through_to_the_board_client(client, boards, board_client):
    client.post("/v1/boards/primary/message", json={"text": "Hello", "force": True})

    assert board_client.render.call_args.kwargs["force"] is True


def test_a_per_send_transition_overrides_the_stored_settings(client, boards, board_client):
    client.post(
        "/v1/boards/primary/message",
        json={"text": "Hello", "transition": {"strategy": "instant", "interval_ms": 40, "step_size": 3}},
    )

    kwargs = board_client.render.call_args.kwargs
    assert kwargs["strategy"] == "instant"
    assert kwargs["step_interval_ms"] == 40
    assert kwargs["step_size"] == 3


# ── boards: the gates, observed through v1 ──────────────────────────────────


def test_paused_board_refuses_the_write(client, boards, board_client):
    from src.settings.service import get_settings_service

    primary_id, _ = boards
    get_settings_service().set_paused(True, board_id=primary_id)

    response = client.post("/v1/boards/primary/message", json={"text": "Hello"})

    assert response.status_code == 409
    assert response.json() == {"detail": "Board is paused — sends are blocked until it is resumed."}
    board_client.render.assert_not_called()


def test_the_silence_window_refuses_the_write(client, boards, board_client):
    with patch("src.config.Config.is_silence_mode_active", return_value=True):
        response = client.post("/v1/boards/primary/message", json={"text": "Hello"})

    assert response.status_code == 409
    assert response.json() == {"detail": "Manual sends blocked during silence mode to prevent wake-ups"}
    board_client.render.assert_not_called()


def test_a_write_the_send_floor_dropped_is_a_429(client, boards):
    client_stub = _board_client(render=(True, False), throttled=True)
    service = Mock()
    service.get_board_client.return_value = client_stub
    service.vb_client = client_stub
    with patch(SERVICE, return_value=service), patch(RUNTIME_SERVICE, return_value=service):
        response = client.post("/v1/boards/primary/message", json={"text": "Hello"})

    assert response.status_code == 429
    assert response.json() == {
        "detail": "Send skipped: the board accepts at most one message every 15s. Retry shortly."
    }
    assert response.headers["Retry-After"] == "15"


def test_a_refused_send_is_a_500_with_an_unstuttered_detail(client, boards):
    client_stub = _board_client(render=(False, False))
    service = Mock()
    service.get_board_client.return_value = client_stub
    service.vb_client = client_stub
    with patch(SERVICE, return_value=service), patch(RUNTIME_SERVICE, return_value=service):
        response = client.post("/v1/boards/primary/message", json={"text": "Hello"})

    assert response.status_code == 500
    assert response.json() == {"detail": "Failed to send message to the board."}


def test_writing_with_no_board_client_is_a_503(client, boards):
    service = Mock()
    service.get_board_client.return_value = None
    primary_id = boards[0]
    with patch(SERVICE, return_value=service), patch(RUNTIME_SERVICE, return_value=service):
        response = client.post("/v1/boards/primary/message", json={"text": "Hello"})

    assert response.status_code == 503
    assert response.json() == {"detail": f"Board client not initialized: {primary_id}"}


# ── boards: timed messages ──────────────────────────────────────────────────


def test_duration_arms_a_timed_message_and_reports_when_it_expires(client, boards, board_client):
    response = client.post("/v1/boards/primary/message", json={"text": "Back soon", "duration_minutes": 20})

    assert response.status_code == 200
    assert response.json()["sent"] is True
    assert response.json()["expires_at"] is not None
    stored = client.get("/settings/temporary-override").json()
    assert stored["template"] is not None
    assert stored["revert_mode"] == "schedule"


def test_duration_on_a_secondary_board_is_refused_rather_than_faked(client, boards, board_client):
    """The override store is global and the loop applies it primary-only."""
    _, secondary_id = boards

    response = client.post(f"/v1/boards/{secondary_id}/message", json={"text": "x", "duration_minutes": 5})

    assert response.status_code == 400
    assert response.json() == {
        "detail": (
            "duration_minutes is only supported on the primary board — "
            "timed messages are applied by the display loop for the primary board only."
        )
    }


def test_duration_with_a_raw_grid_is_refused(client, boards, board_client):
    response = client.post("/v1/boards/primary/message", json={"fill": 0, "duration_minutes": 5})

    assert response.status_code == 400
    assert response.json() == {
        "detail": "duration_minutes cannot be combined with characters or fill; use text, lines or page_id"
    }


def test_revert_mode_without_a_duration_is_refused(client, boards, board_client):
    response = client.post("/v1/boards/primary/message", json={"text": "x", "revert_mode": "blank"})

    assert response.status_code == 400
    assert response.json() == {"detail": "revert_mode requires duration_minutes"}


def test_revert_page_id_without_page_mode_is_refused(client, boards, board_client):
    response = client.post(
        "/v1/boards/primary/message",
        json={"text": "x", "duration_minutes": 5, "revert_mode": "blank", "revert_page_id": "p"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": 'revert_page_id requires revert_mode "page"'}


# ── boards: clearing ────────────────────────────────────────────────────────


def test_delete_cancels_a_timed_message_and_re_renders(client, boards, board_client):
    client.post("/v1/boards/primary/message", json={"text": "Back soon", "duration_minutes": 20})

    response = client.delete("/v1/boards/primary/message")

    assert response.status_code == 200
    assert response.json()["expires_at"] is None
    assert client.get("/settings/temporary-override").json()["template"] is None


# ── boards: active page ─────────────────────────────────────────────────────


def test_pinning_a_page_sets_it_and_reports_delivery(client, boards, board_client):
    primary_id, _ = boards
    page_id = _seed_page(client)

    response = client.put("/v1/boards/primary/active-page", json={"page_id": page_id})

    assert response.status_code == 200
    assert response.json() == {"board_id": primary_id, "page_id": page_id, "sent": True, "warnings": []}


def test_unpinning_clears_the_selection(client, boards, board_client):
    page_id = _seed_page(client)
    client.put("/v1/boards/primary/active-page", json={"page_id": page_id})

    response = client.put("/v1/boards/primary/active-page", json={"page_id": None})

    assert response.status_code == 200
    assert response.json()["page_id"] is None
    assert client.get("/v1/boards/primary").json()["active_page_id"] is None


def test_pinning_a_page_that_does_not_fit_the_board_is_a_400(client, boards, board_client):
    _, secondary_id = boards
    page_id = _seed_page(client)

    response = client.put(f"/v1/boards/{secondary_id}/active-page", json={"page_id": page_id})

    assert response.status_code == 400
    assert "not compatible with board" in response.json()["detail"]


# ── pages, schedules, collections ───────────────────────────────────────────


def test_page_crud_round_trips(client):
    created = client.post(
        "/v1/pages",
        json={"name": "Round Trip", "type": "template", "device_type": "flagship", "template": ["A"]},
    )
    assert created.status_code == 201
    page_id = created.json()["id"]

    assert client.get(f"/v1/pages/{page_id}").json()["name"] == "Round Trip"
    assert client.get("/v1/pages").json()["total"] == 1

    updated = client.put(f"/v1/pages/{page_id}", json={"name": "Renamed"})
    assert updated.status_code == 200
    assert updated.json()["page"]["name"] == "Renamed"

    deleted = client.delete(f"/v1/pages/{page_id}")
    assert deleted.status_code == 200
    assert deleted.json()["id"] == page_id
    assert client.get(f"/v1/pages/{page_id}").status_code == 404


def test_an_unknown_page_is_a_404_with_the_id_in_the_detail(client):
    response = client.get("/v1/pages/nope")

    assert response.status_code == 404
    assert response.json() == {"detail": "Page not found: nope"}


def test_schedule_crud_round_trips(client, boards):
    page_id = _seed_page(client)
    primary_id, _ = boards

    created = client.post(
        "/v1/schedules",
        json={"board_id": primary_id, "page_id": page_id, "start_time": "08:00", "end_time": "09:00"},
    )
    assert created.status_code == 201
    schedule_id = created.json()["id"]

    assert client.get(f"/v1/schedules/{schedule_id}").json()["start_time"] == "08:00"
    assert client.get("/v1/schedules", params={"board_id": primary_id}).json()["total"] == 1

    updated = client.put(f"/v1/schedules/{schedule_id}", json={"start_time": "10:00"})
    assert updated.status_code == 200
    assert updated.json()["start_time"] == "10:00"
    assert updated.json()["end_time"] == "09:00", "a partial update must not wipe the fields it omits"

    deleted = client.delete(f"/v1/schedules/{schedule_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"id": schedule_id}


def test_creating_a_schedule_on_an_unknown_board_is_a_404(client):
    page_id = _seed_page(client)

    response = client.post(
        "/v1/schedules",
        json={"board_id": "nope", "page_id": page_id, "start_time": "08:00"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Board not found: nope"}


def test_collection_crud_round_trips(client):
    first = _seed_page(client, "One")
    second = _seed_page(client, "Two")

    created = client.post("/v1/collections", json={"name": "Rotation", "page_ids": [first, second]})
    assert created.status_code == 201
    collection_id = created.json()["id"]
    assert collection_id.startswith("collection:")

    assert client.get(f"/v1/collections/{collection_id}").json()["page_ids"] == [first, second]
    assert client.get("/v1/collections").json()["total"] == 1

    updated = client.put(f"/v1/collections/{collection_id}", json={"name": "Renamed"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed"

    deleted = client.delete(f"/v1/collections/{collection_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"id": collection_id}


def test_a_collection_referencing_a_missing_page_is_a_400(client):
    response = client.post("/v1/collections", json={"name": "Bad", "page_ids": ["nope"]})

    assert response.status_code == 400
    assert response.json() == {"detail": "Page not found: nope"}


# ── plugins ─────────────────────────────────────────────────────────────────


def test_the_plugin_catalogue_merges_plugins_and_displays(client):
    """/plugins and /displays were the same registry listing, published twice."""
    response = client.get("/v1/plugins")

    assert response.status_code == 200
    body = response.json()
    ids = {plugin["id"] for plugin in body["plugins"]}
    assert "date_time" in ids
    assert body["total"] == len(body["plugins"])
    assert body["enabled_count"] == sum(1 for p in body["plugins"] if p["enabled"])
    assert set(body["plugins"][0]) == {
        "id",
        "name",
        "version",
        "description",
        "author",
        "category",
        "plugin_type",
        "icon",
        "enabled",
        "configured",
    }
    # The legacy pair answers the same catalogue.
    assert ids == {entry["type"] for entry in client.get("/displays").json()["displays"]}


def test_patch_collapses_enable_disable_and_config(client):
    enabled = client.patch("/v1/plugins/date_time", json={"enabled": True})
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True

    configured = client.patch("/v1/plugins/date_time", json={"config": {"time_format": "24h"}})
    assert configured.status_code == 200
    assert configured.json()["config"]["time_format"] == "24h"

    disabled = client.patch("/v1/plugins/date_time", json={"enabled": False})
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False


def test_patch_with_an_empty_body_is_a_400(client):
    response = client.patch("/v1/plugins/date_time", json={})

    assert response.status_code == 400
    assert response.json() == {"detail": "Send at least one of enabled or config."}


def test_patching_an_unknown_plugin_is_a_404(client):
    response = client.patch("/v1/plugins/nope", json={"enabled": True})

    assert response.status_code == 404
    assert response.json() == {"detail": "Plugin not found: nope"}


def test_plugin_data_serves_both_the_raw_payload_and_the_board_lines(client):
    client.patch("/v1/plugins/date_time", json={"enabled": True})

    response = client.get("/v1/plugins/date_time/data")

    assert response.status_code == 200
    body = response.json()
    assert body["plugin_id"] == "date_time"
    assert body["available"] is True
    assert "date" in body["data"]
    assert body["text"] == "\n".join(body["lines"])
    assert body["error"] is None


def test_plugin_data_for_a_disabled_plugin_is_a_400(client):
    response = client.get("/v1/plugins/date_time/data")

    assert response.status_code == 400
    assert response.json() == {"detail": "Plugin not enabled: date_time"}


# ── templating and service ──────────────────────────────────────────────────


def test_variables_merges_the_engine_and_plugin_catalogues(client):
    response = client.get("/v1/variables")

    assert response.status_code == 200
    body = response.json()
    assert body["colors"]["red"] == 63
    assert "sun" in body["symbols"]
    assert body["plugin_system_enabled"] is True
    assert set(body) == {
        "variables",
        "max_lengths",
        "variable_metadata",
        "variable_groups",
        "colors",
        "symbols",
        "filters",
        "formatting",
        "syntax_examples",
        "plugin_system_enabled",
    }


def test_functions_lists_the_expression_helpers(client):
    response = client.get("/v1/functions")

    assert response.status_code == 200
    assert response.json()["functions"]["IF"] == {
        "category": "logic",
        "signature": "IF(cond, then[, else])",
        "summary": "Conditional value",
    }


def test_render_sizes_the_output_to_the_named_board(client, boards):
    _, secondary_id = boards

    flagship = client.post("/v1/render", json={"template": ["HI"]}, params={"board": "primary"})
    note = client.post("/v1/render", json={"template": ["HI"]}, params={"board": secondary_id})

    assert flagship.status_code == 200
    assert flagship.json()["line_count"] == FLAGSHIP_ROWS
    assert note.json()["line_count"] == NOTE_ROWS


def test_render_against_an_unknown_board_is_a_404(client, boards):
    response = client.post("/v1/render", json={"template": ["HI"]}, params={"board": "nope"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Board not found: nope"}


def test_render_never_writes_to_a_board(client, boards, board_client):
    client.post("/v1/render", json={"template": ["HI"]}, params={"board": "primary"})

    board_client.render.assert_not_called()


def test_health_answers_without_a_configured_board(client):
    response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service_running"] is False


def test_status_reports_per_board_state(client, boards, board_client):
    primary_id, _ = boards

    response = client.get("/v1/status")

    assert response.status_code == 200
    assert response.json()["boards"][primary_id]["paused"] is False
