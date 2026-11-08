"""H1: a timed override per display.

Each board has its own temporary override: set, read and cleared by board id,
applied by that board's display pass, reverted on that board when it expires,
and reported on that board's surfaces (``/v1/boards/{b}``, panel status, the
schedule's active page). Omitting the board means the primary board, which is
exactly what every caller did before.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.settings.service import PRIMARY_RUNTIME_KEY, SettingsService, TemporaryOverride
from tests.test_per_board_engine import (
    _board,
    _drive,
    _page_service,
    _schedule_service,
    _service_with_runtimes,
    _settings_service,
)
from tests.test_v1_contract import _seed_page, board_client, boards, client  # noqa: F401 - fixtures


def _later(minutes=30):
    return (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat()


def _earlier(minutes=1):
    return (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()


@pytest.fixture
def mock_config():
    with patch("src.config.Config") as mock:
        mock.FB_TRANSITION_STRATEGY = "column"
        mock.FB_TRANSITION_INTERVAL_MS = 100
        mock.FB_TRANSITION_STEP_SIZE = 2
        mock.OUTPUT_TARGET = "board"
        yield mock


def _two_board_file(path: Path, **extra) -> str:
    raw = {
        "board": {
            "board_type": "black",
            "boards": [
                {"id": "board-1", "name": "Kitchen", "device_type": "flagship", "board_color": "black"},
                {"id": "board-2", "name": "Hallway", "device_type": "flagship", "board_color": "white"},
            ],
        },
        **extra,
    }
    path.write_text(json.dumps(raw))
    return str(path)


@pytest.fixture
def store(tmp_path, mock_config):
    return SettingsService(settings_file=_two_board_file(tmp_path / "settings.json"))


# --- The store -----------------------------------------------------------------


def test_each_board_has_its_own_override(store):
    store.set_temporary_override(TemporaryOverride(page_id="p1", expires_at=_later()))
    store.set_temporary_override(TemporaryOverride(page_id="p2", expires_at=_later()), board_id="board-2")
    assert store.get_temporary_override().page_id == "p1"
    assert store.get_temporary_override(board_id="board-1").page_id == "p1"
    assert store.get_temporary_override(board_id="board-2").page_id == "p2"
    store.clear_temporary_override(board_id="board-2")
    assert store.get_temporary_override(board_id="board-2") is None
    assert store.get_temporary_override().page_id == "p1"


@pytest.mark.parametrize("primary", [None, "", PRIMARY_RUNTIME_KEY, "board-1"])
def test_every_name_for_the_primary_reaches_the_same_override(store, primary):
    store.set_temporary_override(TemporaryOverride(page_id="p1"), board_id=primary)
    assert store.peek_temporary_override(board_id="board-1").page_id == "p1"
    assert store.peek_temporary_override().page_id == "p1"


def test_consume_expires_only_that_board(store):
    store.set_temporary_override(TemporaryOverride(page_id="p1", expires_at=_later()))
    store.set_temporary_override(TemporaryOverride(page_id="p2", expires_at=_earlier()), board_id="board-2")
    expired = store.consume_temporary_override(board_id="board-2")
    assert expired.page_id == "p2" and expired.is_expired()
    assert store.consume_temporary_override(board_id="board-2") is None
    assert store.consume_temporary_override(board_id="board-1").page_id == "p1"


def test_peek_never_expires(store):
    store.set_temporary_override(TemporaryOverride(page_id="p2", expires_at=_earlier()), board_id="board-2")
    assert store.peek_temporary_override(board_id="board-2") is not None
    assert store.peek_temporary_override(board_id="board-2") is not None


def test_live_overrides_lists_unexpired_ones_by_board(store):
    store.set_temporary_override(TemporaryOverride(page_id="p1", expires_at=_earlier()))
    store.set_temporary_override(TemporaryOverride(page_id="p2"), board_id="board-2")
    live = store.list_temporary_overrides()
    assert list(live) == ["board-2"] and live["board-2"].page_id == "p2"


def test_removing_a_board_drops_its_override(store):
    store.set_temporary_override(TemporaryOverride(page_id="p2"), board_id="board-2")
    store.remove_board("board-2")
    assert store.peek_temporary_override(board_id="board-2") is None


def test_an_override_stays_with_its_board_when_the_primary_changes(store):
    store.set_temporary_override(TemporaryOverride(page_id="p1"), board_id="board-1")
    store.set_temporary_override(TemporaryOverride(page_id="p2"), board_id="board-2")
    store.remove_board("board-1")  # board-2 is now the primary
    assert store.get_primary_board_id() == "board-2"
    assert store.get_temporary_override().page_id == "p2"


def test_a_new_override_has_a_start_time(store):
    before = datetime.now(UTC) - timedelta(seconds=1)
    override = store.set_temporary_override(TemporaryOverride(page_id="p2"), board_id="board-2")
    assert override.started_at is not None
    assert datetime.fromisoformat(override.started_at) >= before


# --- On disk ----------------------------------------------------------------------


def test_the_primary_uses_the_legacy_key_and_others_a_map(tmp_path, store):
    store.set_temporary_override(TemporaryOverride(page_id="p1"))
    store.set_temporary_override(TemporaryOverride(page_id="p2", expires_at=_later()), board_id="board-2")
    raw = json.loads((tmp_path / "settings.json").read_text())
    assert raw["temporary_override"]["page_id"] == "p1"
    assert set(raw["temporary_overrides"]) == {"board-2"}
    assert raw["temporary_overrides"]["board-2"]["page_id"] == "p2"


def test_a_reload_restores_every_board(tmp_path, store, mock_config):
    first = store.set_temporary_override(TemporaryOverride(page_id="p1"))
    store.set_temporary_override(TemporaryOverride(page_id="p2", expires_at=_later()), board_id="board-2")
    again = SettingsService(settings_file=str(tmp_path / "settings.json"))
    assert again.get_temporary_override().page_id == "p1"
    assert again.get_temporary_override().started_at == first.started_at
    assert again.get_temporary_override(board_id="board-2").page_id == "p2"


def test_an_old_file_loads_as_the_primarys_override(tmp_path, mock_config):
    legacy = TemporaryOverride(page_id="p1", expires_at=_later()).to_dict()
    legacy.pop("started_at", None)
    path = _two_board_file(tmp_path / "settings.json", temporary_override=legacy)
    loaded = SettingsService(settings_file=path)
    assert loaded.get_temporary_override(board_id="board-1").page_id == "p1"
    assert loaded.get_temporary_override(board_id="board-1").started_at is None
    assert loaded.get_temporary_override(board_id="board-2") is None


def test_unknown_boards_and_expired_entries_are_dropped_on_load(tmp_path, mock_config):
    path = _two_board_file(
        tmp_path / "settings.json",
        temporary_overrides={
            "gone": TemporaryOverride(page_id="x").to_dict(),
            "board-2": TemporaryOverride(page_id="p2", expires_at=_earlier()).to_dict(),
        },
    )
    loaded = SettingsService(settings_file=path)
    assert loaded.list_temporary_overrides() == {}
    assert loaded.peek_temporary_override(board_id="board-2") is None


# --- REST ---------------------------------------------------------------------------


def test_rest_sets_reads_and_clears_one_board(client, boards):  # noqa: F811
    primary, second = boards
    body = {"template": ["HELLO HALL"], "duration_minutes": 30, "board_id": second}
    set_response = client.post("/settings/temporary-override", json=body)
    assert set_response.status_code == 200, set_response.text
    payload = set_response.json()
    assert payload["active"] is True and payload["board_id"] == second and payload["started_at"]

    assert client.get(f"/settings/temporary-override?board_id={second}").json()["active"] is True
    primary_view = client.get("/settings/temporary-override").json()
    assert primary_view["active"] is False and primary_view["board_id"] == primary

    listed = client.get("/settings/temporary-overrides").json()["overrides"]
    assert [row["board_id"] for row in listed] == [second]

    assert client.delete(f"/settings/temporary-override?board_id={second}").status_code == 200
    assert client.get(f"/settings/temporary-override?board_id={second}").json()["active"] is False


def test_rest_unknown_board_is_404(client, boards):  # noqa: F811
    assert client.get("/settings/temporary-override?board_id=nope").status_code == 404
    response = client.post("/settings/temporary-override", json={"template": ["X"], "board_id": "nope"})
    assert response.status_code == 404
    assert client.delete("/settings/temporary-override?board_id=nope").status_code == 404


def test_rest_without_a_board_is_the_primary(client, boards):  # noqa: F811
    primary, _ = boards
    assert client.post("/settings/temporary-override", json={"template": ["HI"]}).status_code == 200
    from src.settings.service import get_settings_service

    assert get_settings_service().peek_temporary_override(board_id=primary).template == ["HI"]


def test_rest_clear_reverts_the_page_on_that_board(client, boards):  # noqa: F811
    primary, second = boards
    page_id = _seed_page(client, "Revert")
    body = {"template": ["X"], "duration_minutes": 5, "revert_mode": "page", "revert_page_id": page_id}
    assert client.post("/settings/temporary-override", json={**body, "board_id": second}).status_code == 200
    assert client.delete(f"/settings/temporary-override?board_id={second}").json()["revert_mode"] == "page"
    from src.settings.service import get_settings_service

    settings = get_settings_service()
    assert settings.get_active_page_id(board_id=second) == page_id
    assert settings.get_active_page_id(board_id=primary) != page_id


def test_schedules_active_page_reports_that_boards_override(client, boards):  # noqa: F811
    _, second = boards
    client.post("/settings/temporary-override", json={"template": ["HALL"], "board_id": second})
    assert client.get(f"/schedules/active/page?board_id={second}").json()["temporary_override"]["active"] is True
    assert client.get("/schedules/active/page").json()["temporary_override"]["active"] is False


# --- /v1 ------------------------------------------------------------------------------


def test_v1_times_a_message_on_a_second_board(client, boards, board_client):  # noqa: F811
    primary, second = boards
    response = client.post(f"/v1/boards/{second}/message", json={"text": "Back soon", "duration_minutes": 20})
    assert response.status_code == 200, response.text
    assert response.json()["expires_at"] is not None
    detail = client.get(f"/v1/boards/{second}").json()
    assert detail["override_expires_at"] is not None and detail["override_started_at"] is not None
    assert client.get(f"/v1/boards/{primary}").json()["override_expires_at"] is None


def test_v1_clearing_a_message_clears_only_that_board(client, boards, board_client):  # noqa: F811
    primary, second = boards
    client.post(f"/v1/boards/{second}/message", json={"text": "Hall", "duration_minutes": 20})
    client.post("/v1/boards/primary/message", json={"text": "Kitchen", "duration_minutes": 20})
    assert client.delete(f"/v1/boards/{second}/message").status_code == 200
    from src.settings.service import get_settings_service

    settings = get_settings_service()
    assert settings.peek_temporary_override(board_id=second) is None
    assert settings.peek_temporary_override(board_id=primary) is not None


def test_v1_raw_grid_with_a_duration_is_still_refused(client, boards, board_client):  # noqa: F811
    _, second = boards
    response = client.post(f"/v1/boards/{second}/message", json={"fill": 0, "duration_minutes": 5})
    assert response.status_code == 400


# --- The display pass -------------------------------------------------------------------


def _override(page_id, expires_at=None, **kw):
    return TemporaryOverride(page_id=page_id, expires_at=expires_at, **kw)


def test_a_second_board_shows_its_own_override():
    boards_ = [_board("b1", "One"), _board("b2", "Two", port=7001)]
    svc, clients = _service_with_runtimes(boards_)
    pages = _page_service({"pA": {"content": "ALPHA"}, "pB": {"content": "BETA"}, "pO": {"content": "OVR"}})
    schedule = _schedule_service({"b1": "pA", "b2": "pB"})
    settings = _settings_service(boards_, override={"b2": _override("pO", _later())})

    _drive(svc, boards_, settings=settings, pages=pages, schedule=schedule)

    assert clients["b2"].render.called and clients["b1"].render.called
    assert svc.runtimes["b2"].last_active_page_id == "pO"
    assert svc.runtimes["b1"].last_active_page_id == "pA"


def test_a_second_boards_expiry_reverts_only_that_board():
    boards_ = [_board("b1", "One"), _board("b2", "Two", port=7001)]
    svc, _clients = _service_with_runtimes(boards_)
    pages = _page_service({"pA": {"content": "ALPHA"}, "pB": {"content": "BETA"}, "pR": {"content": "BACK"}})
    schedule = _schedule_service({"b1": "pA", "b2": "pB"})
    expired = _override("pO", _earlier(), revert_mode="page", revert_page_id="pR")
    settings = _settings_service(boards_, override={"b2": expired})

    _drive(svc, boards_, settings=settings, pages=pages, schedule=schedule)

    settings.set_active_page_id.assert_called_once_with("pR", board_id="b2")


# --- Panel status (H13) ---------------------------------------------------------------------


def test_a_panel_on_a_second_board_reports_its_boards_override(store):
    from src.panels.status import panel_status

    store.set_temporary_override(TemporaryOverride(page_id="p2", expires_at=_later()), board_id="board-2")
    with (
        patch("src.panels.status.get_settings_service", return_value=store),
        patch("src.panels.status.Config") as cfg,
    ):
        cfg.is_silence_mode_active.return_value = False
        second = panel_status("board-2")
        first = panel_status("board-1")
    assert second.override_active is True and second.mode == "override"
    assert second.override_started_at is not None
    assert first.override_active is False


# --- MCP / ops ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ops_set_and_cancel_target_one_board(client, boards):  # noqa: F811
    from src.ops import executors
    from src.settings.service import get_settings_service

    primary, second = boards
    result = await executors.set_temporary_override(template_lines=["HALL"], board_id=second)
    assert result["status"] == "success", result
    settings = get_settings_service()
    assert settings.peek_temporary_override(board_id=second).template == ["HALL"]
    assert settings.peek_temporary_override(board_id=primary) is None
    cancelled = await executors.cancel_temporary_override(board_id=second)
    assert cancelled["was_active"] is True
    assert settings.peek_temporary_override(board_id=second) is None


# --- Content references ---------------------------------------------------------------------


def test_a_page_used_by_a_second_boards_override_cannot_be_deleted(client, boards):  # noqa: F811
    _, second = boards
    page_id = _seed_page(client, "Used")
    client.post("/settings/temporary-override", json={"page_id": page_id, "board_id": second})
    assert client.delete(f"/v1/pages/{page_id}").status_code == 409


def test_the_control_scope_can_list_overrides():
    from src.auth import scopes

    assert scopes.permits(scopes.CONTROL, "GET", "/settings/temporary-overrides")


def test_engine_harness_override_shape_is_per_board():
    # Guards the harness itself: a dict override applies to the named boards only.
    settings = _settings_service([_board("b1", "One"), _board("b2", "Two")], override={"b2": SimpleNamespace()})
    assert settings.consume_temporary_override(board_id="b1") is None
    assert settings.consume_temporary_override(board_id="b2") is not None
