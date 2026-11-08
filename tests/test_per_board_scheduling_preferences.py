"""Scheduling preferences are board-owned, including legacy API aliases."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.main import BoardRuntime, DisplayService
from src.settings.service import SettingsService


@pytest.fixture
def settings(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 7,
                "board": {"boards": [{"id": "a"}, {"id": "b"}]},
                "polling": {"interval_seconds": 45, "board_read_interval_local": 60, "board_read_interval_cloud": 240},
                "schedule": {"defer_on_reenable": True},
            }
        )
    )
    return SettingsService(str(path))


def test_upgrade_preserves_legacy_preferences_on_each_existing_board(settings):
    for board in settings.get_board_settings().boards:
        assert board["polling_interval_seconds"] == 45
        assert board["board_read_interval_local"] == 60
        assert board["board_read_interval_cloud"] == 240
        assert board["schedule_defer_on_reenable"] is True
    assert json.loads(settings.settings_file.read_text())["schema_version"] == 8


def test_new_boards_start_with_fixed_defaults_instead_of_primary_preferences(settings):
    settings.add_board({"id": "new", "device_type": "flagship"})
    board = settings.get_board_settings().boards[-1]
    assert board["polling_interval_seconds"] == 15
    assert board["board_read_interval_local"] == 30
    assert board["board_read_interval_cloud"] == 180
    assert board["schedule_defer_on_reenable"] is False


def test_board_write_persists_only_its_own_preferences(settings):
    boards = settings.get_board_settings().to_dict()["boards"]
    boards[1].update(
        polling_interval_seconds=90,
        board_read_interval_local=120,
        board_read_interval_cloud=600,
        schedule_defer_on_reenable=False,
    )
    settings.set_boards(boards)
    restored = SettingsService(str(settings.settings_file))
    assert restored.get_polling_interval(board_id="a") == 45
    assert restored.get_polling_interval(board_id="b") == 90
    assert restored.get_schedule_settings(board_id="a").defer_on_reenable is True
    assert restored.get_schedule_settings(board_id="b").defer_on_reenable is False


def test_older_client_board_write_preserves_existing_scheduling_preferences(settings):
    settings.set_boards([{"id": "a", "name": "Renamed"}, {"id": "b"}])
    assert settings.get_polling_interval(board_id="a") == 45
    assert settings.get_schedule_settings(board_id="b").defer_on_reenable is True


@pytest.mark.parametrize(
    "key,value",
    [
        ("polling_interval_seconds", 9),
        ("polling_interval_seconds", 3601),
        ("polling_interval_seconds", True),
        ("polling_interval_seconds", "45"),
        ("polling_interval_seconds", 45.0),
        ("schedule_defer_on_reenable", 1),
        ("board_read_interval_local", 19),
        ("board_read_interval_cloud", 3601),
        ("schedule_defer_on_reenable", "false"),
    ],
)
def test_invalid_board_preferences_refuse_entire_write(settings, key, value):
    before = settings.settings_file.read_text()
    boards = settings.get_board_settings().to_dict()["boards"]
    boards[1][key] = value
    with pytest.raises(ValueError):
        settings.set_boards(boards)
    assert settings.settings_file.read_text() == before


def test_legacy_setters_target_primary_and_explicit_setters_target_one_board(settings):
    settings.set_polling_interval(75)
    settings.set_board_read_intervals(local_seconds=90)
    settings.set_schedule_defer_on_reenable(False)
    assert settings.get_polling_interval(board_id="b") == 45
    assert settings.get_polling_settings(board_id="b").board_read_interval_local == 60
    assert settings.get_schedule_settings(board_id="b").defer_on_reenable is True
    settings.set_polling_interval(120, board_id="b")
    assert settings.get_polling_interval() == 75
    with pytest.raises(ValueError, match="not found"):
        settings.set_polling_interval(60, board_id="missing")


def test_reader_uses_each_boards_own_interval(settings):
    settings.set_board_read_intervals(local_seconds=20, board_id="a")
    settings.set_board_read_intervals(local_seconds=60, board_id="b")
    service = DisplayService()
    clients = [MagicMock(is_virtual=False) for _ in range(2)]
    for client in clients:
        client.read_back = SimpleNamespace(supported=True, cost="local")
    service.runtimes = {bid: BoardRuntime(client, bid) for bid, client in zip(("a", "b"), clients, strict=True)}
    service._primary_board_id = "a"
    for rt in service.runtimes.values():
        rt.poll_attempted_at = 100
    with (
        patch("src.main.get_settings_service", return_value=settings),
        patch("src.main.time.monotonic", return_value=120),
    ):
        service._poll_all_boards_once()
        assert service._board_poll_tick(20) <= 20
    assert clients[0].read_current_message.call_count == 1
    assert clients[1].read_current_message.call_count == 0


def test_engine_refresh_cadence_is_independent_and_updates_live(settings):
    settings.set_polling_interval(10, board_id="a")
    settings.set_polling_interval(30, board_id="b")
    service = DisplayService()
    service.runtimes = {bid: BoardRuntime(MagicMock(), bid) for bid in ("a", "b")}
    service._primary_board_id = "a"
    with patch("src.main.get_settings_service", return_value=settings):
        assert service._boards_due_for_refresh(100) == {"a", "b"}
        assert service._boards_due_for_refresh(110) == {"a"}
        assert service._boards_due_for_refresh(120) == {"a"}
        assert service._boards_due_for_refresh(130) == {"a", "b"}
        settings.set_polling_interval(10, board_id="b")
        assert service._boards_due_for_refresh(140) == {"a", "b"}


def test_device_probes_keep_the_boards_local_read_cadence_on_fast_loop(settings):
    service = DisplayService()
    clients = [MagicMock(), MagicMock()]
    service.runtimes = {bid: BoardRuntime(client, bid) for bid, client in zip(("a", "b"), clients, strict=True)}
    settings.set_board_read_intervals(local_seconds=20, board_id="a")
    with patch("src.main.get_settings_service", return_value=settings), patch("src.main.time.monotonic") as clock:
        clock.return_value = 100
        service._poll_output_devices()
        clock.return_value = 120
        service._poll_output_devices()
    assert clients[0].poll_device.call_count == 2
    assert clients[1].poll_device.call_count == 1


def test_removed_board_runtime_does_not_stop_refresh_pass(settings):
    service = DisplayService()
    service.runtimes = {bid: BoardRuntime(None, bid) for bid in ("a", "b")}
    settings.remove_board("b")
    with patch("src.main.get_settings_service", return_value=settings):
        assert service._boards_due_for_refresh(100) == {"a"}


def test_real_loop_only_drives_due_boards_even_with_fast_peer_collection(settings):
    settings.set_polling_interval(10, board_id="a")
    settings.set_polling_interval(30, board_id="b")
    settings.set_active_page_id("collection:fast", board_id="a")
    settings.set_active_page_id("ordinary", board_id="b")
    service = DisplayService()
    service.runtimes = {bid: BoardRuntime(MagicMock(), bid) for bid in ("a", "b")}
    service._primary_board_id = "a"
    clock = [0]
    sent = {"a": [], "b": []}

    def send(board_id, rt, **kwargs):
        sent[board_id].append(clock[0])

    def sleep(_):
        clock[0] += 1
        if clock[0] >= 32:
            service.running = False

    collections = MagicMock()
    collections.seconds_until_next_check.return_value = 5
    with (
        patch("src.main.get_settings_service", return_value=settings),
        patch("src.main.time.time", side_effect=lambda: clock[0]),
        patch("src.main.time.sleep", side_effect=sleep),
        patch("src.main.get_collection_service", return_value=collections),
        patch.object(service, "_silence_state_changed", return_value=False),
        patch.object(service, "take_wake", return_value=False),
        patch.object(service, "check_and_send_for_board", side_effect=send),
    ):
        service.run()
    assert sent["b"] == [0, 30]
    assert 5 in sent["a"] and 15 in sent["a"] and 25 in sent["a"]


def test_migration_preserves_long_legacy_intervals_and_allows_unrelated_edits(tmp_path):
    path = tmp_path / "long.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 7,
                "board": {"boards": [{"id": "a"}]},
                "polling": {"interval_seconds": 7200, "board_read_interval_local": 8000},
            }
        )
    )
    settings = SettingsService(str(path))
    assert settings.get_polling_interval() == 7200
    assert settings.get_polling_settings().board_read_interval_local == 8000
    boards = settings.get_board_settings().to_dict()["boards"]
    boards[0]["name"] = "Renamed"
    settings.set_boards(boards)
    assert settings.get_polling_interval() == 7200
    with pytest.raises(ValueError):
        settings.set_polling_interval(7201)


def test_new_board_silence_defaults_do_not_inherit_legacy_enabled_window(settings, tmp_path):
    from src.config import resolve_silence_schedule
    from src.config_manager import ConfigManager

    manager = ConfigManager(str(tmp_path / "config.json"))
    manager.set_feature("silence_schedule", {"enabled": True, "start_time": "02:00+00:00", "mode": "indicator"})
    with patch("src.config_manager.get_config_manager", return_value=manager):
        settings.add_board({"id": "new", "device_type": "flagship"})
    feature = manager.get_feature("silence_schedule")
    assert resolve_silence_schedule(feature, "a")["enabled"] is True
    fresh = resolve_silence_schedule(feature, "new")
    assert fresh["enabled"] is False
    assert fresh["mode"] == "freeze"
    assert fresh["start_time"] != "02:00+00:00"
    assert fresh["start_time"].endswith("+00:00")


def test_reenable_defer_preference_is_independent(settings):
    settings.set_schedule_defer_on_reenable(False, board_id="a")
    service = DisplayService()
    first, second = BoardRuntime(None, "a"), BoardRuntime(None, "b")
    first.last_schedule_enabled = second.last_schedule_enabled = False
    now = MagicMock()
    schedules = MagicMock()
    schedules.get_active_schedule_entry.return_value.id = "window"
    with (
        patch("src.main.get_settings_service", return_value=settings),
        patch("src.main.get_schedule_service", return_value=schedules),
    ):
        assert service._schedule_defer_active(first, now, "a") is False
        assert service._schedule_defer_active(second, now, "b") is True


@pytest.fixture
def api(settings):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.schedules.routes import router as schedule_router
    from src.settings.routes import router as settings_router

    app = FastAPI()
    app.include_router(settings_router)
    app.include_router(schedule_router)
    with (
        patch("src.settings.routes.get_settings_service", return_value=settings),
        patch("src.schedules.routes.get_settings_service", return_value=settings),
    ):
        yield TestClient(app)


def test_scoped_polling_endpoint_applies_live_to_one_board(api):
    response = api.put("/settings/polling", json={"board_id": "b", "interval_seconds": 120})
    assert response.status_code == 200
    assert response.json()["requires_restart"] is False
    assert api.get("/settings/polling?board_id=b").json()["interval_seconds"] == 120
    assert api.get("/settings/polling").json()["interval_seconds"] == 45


def test_scoped_schedule_behavior_endpoint_isolates_boards(api):
    response = api.put("/schedules/settings", json={"board_id": "b", "defer_on_reenable": False})
    assert response.status_code == 200
    assert api.get("/schedules/settings?board_id=b").json()["defer_on_reenable"] is False
    assert api.get("/schedules/settings").json()["defer_on_reenable"] is True


@pytest.mark.parametrize(
    "path,body",
    [("/settings/polling", {"interval_seconds": 60}), ("/schedules/settings", {"defer_on_reenable": False})],
)
def test_unknown_board_is_refused_for_preferences_reads_and_writes(api, path, body):
    assert api.get(path + "?board_id=missing").status_code == 404
    assert api.put(path, json={**body, "board_id": "missing"}).status_code == 404


def test_invalid_partial_polling_update_leaves_both_values_unchanged(api):
    response = api.put(
        "/settings/polling", json={"board_id": "b", "interval_seconds": 90, "board_read_interval_local": 5}
    )
    assert response.status_code in (400, 422)
    assert api.get("/settings/polling?board_id=b").json()["interval_seconds"] == 45


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "category,values", [("polling", {"interval_seconds": 60}), ("schedule_behavior", {"defer_on_reenable": False})]
)
async def test_ai_settings_result_names_actual_board_for_navigation(api, settings, category, values):
    from src.ops.executors import update_setting

    with patch("src.settings.service.get_settings_service", return_value=settings):
        result = await update_setting(category, {**values, "board_id": "b"})
        assert result["status"] == "success"
        assert result["board_id"] == "b"
        legacy = await update_setting(category, values)
        assert legacy["board_id"] == "a"
