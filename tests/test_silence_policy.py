"""Shared silence decisions, settings persistence and additive status contract."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src import board_guards, silence_queue
from src.config import Config, resolve_silence_schedule
from src.config_manager import ConfigManager
from tests.fake_clock import FakeClock, install_fake_time_service


@pytest.fixture
def setup_policy(tmp_path, monkeypatch):
    from src.api_server import app

    path = tmp_path / "config.json"
    path.write_text(json.dumps({"features": {"silence_schedule": {"by_board": {}}}}))
    cm = ConfigManager(config_path=str(path))
    cm.set_feature("silence_schedule", {"enabled": True, "start_time": "22:00+00:00", "end_time": "07:00+00:00"})
    service = SimpleNamespace(
        get_primary_board_id=lambda: "a",
        get_board_settings=lambda: SimpleNamespace(boards=[{"id": "a"}, {"id": "b"}]),
    )
    monkeypatch.setattr("src.api_server.get_settings_service", lambda: service)
    monkeypatch.setattr(board_guards, "get_settings_service", lambda: service)
    monkeypatch.setattr("src.settings.service.get_settings_service", lambda: service)
    monkeypatch.setattr("src.service_api.routes.get_config_manager", lambda: cm)
    clock = FakeClock(datetime(2026, 10, 24, 23, 30, tzinfo=UTC))
    install_fake_time_service(monkeypatch, clock)
    return cm, TestClient(app), clock


def test_settings_default_is_opt_out():
    assert resolve_silence_schedule({}).get("show_queued_on_exit") is False


def test_settings_resolves_board_override_without_changing_install_default(setup_policy):
    cm, _, _ = setup_policy
    cm.set_feature("silence_schedule", {"show_queued_on_exit": True})
    cm.set_silence_schedule_for_board("b", {"show_queued_on_exit": False})
    assert Config.silence_config_for("a").get("show_queued_on_exit") is True
    assert Config.silence_config_for("b").get("show_queued_on_exit") is False


@pytest.mark.parametrize("board_id", [None, "b"])
def test_settings_accepts_holding_and_preserves_omitted_updates(setup_policy, board_id):
    cm, client, _ = setup_policy
    body = {"enabled": True, "start_time": "22:00+00:00", "end_time": "07:00+00:00"}
    if board_id:
        body["board_id"] = board_id
    result = client.put("/settings/silence-schedule", json={**body, "show_queued_on_exit": True})
    assert result.status_code == 200
    assert result.json()["config"].get("show_queued_on_exit") is True
    assert client.put("/settings/silence-schedule", json=body).json()["config"]["show_queued_on_exit"] is True
    assert (
        client.put("/settings/silence-schedule", json={**body, "show_queued_on_exit": False}).json()["config"][
            "show_queued_on_exit"
        ]
        is False
    )
    assert cm.get_feature("silence_schedule")["by_board"].get("a") is None


@pytest.mark.parametrize("value", ["true", "false", 1, [], {}])
def test_settings_rejects_non_boolean_holding(setup_policy, value):
    _, client, _ = setup_policy
    response = client.put(
        "/settings/silence-schedule",
        json={"enabled": True, "start_time": "22:00+00:00", "end_time": "07:00+00:00", "show_queued_on_exit": value},
    )
    assert response.status_code == 422


def _verdict(*args, **kwargs):
    assert hasattr(board_guards, "silence_verdict"), "Shared silence decision is not implemented"
    return board_guards.silence_verdict(*args, **kwargs)


def test_guard_refuses_without_opt_in_and_does_not_replace_held_intent(setup_policy):
    silence_queue.hold(silence_queue.HeldSend.text("KEEP", board_id="a"))
    result = _verdict(None, override_silence=False, hold=lambda b: silence_queue.HeldSend.text("NEW", board_id=b))
    assert result.silenced is True
    assert result.held is False
    assert result.ends_at_utc == "2026-10-25T07:00:00+00:00"
    assert silence_queue.peek("a").payload == "KEEP"


def test_guard_holds_for_resolved_primary_only_when_opted_in(setup_policy):
    cm, _, _ = setup_policy
    cm.set_silence_schedule_for_board("a", {"show_queued_on_exit": True})
    result = _verdict(None, override_silence=False, hold=lambda b: silence_queue.HeldSend.text("LATER", board_id=b))
    assert (result.silenced, result.held) == (True, True)
    assert silence_queue.peek("a").payload == "LATER"
    assert silence_queue.peek("b") is None


@pytest.mark.parametrize("override", [True, False])
def test_guard_does_not_hold_when_override_or_outside_window(setup_policy, override):
    cm, _, clock = setup_policy
    cm.set_feature("silence_schedule", {"show_queued_on_exit": True})
    if not override:
        clock.set(datetime(2026, 10, 25, 12, tzinfo=UTC))
    result = _verdict("b", override_silence=override, hold=lambda b: silence_queue.HeldSend.text("NOW", board_id=b))
    assert (result.silenced, result.held, result.ends_at_utc) == (False, False, None)
    assert silence_queue.peek("b") is None


def test_guard_no_factory_call_when_holding_disabled(setup_policy):
    def factory(_board_id):
        pytest.fail("Refused sends must not construct an unused held intent")

    assert _verdict("a", override_silence=False, hold=factory).held is False


def test_guard_rejects_intent_for_different_board(setup_policy):
    cm, _, _ = setup_policy
    cm.set_feature("silence_schedule", {"show_queued_on_exit": True})
    with pytest.raises(ValueError, match="board"):
        _verdict("a", override_silence=False, hold=silence_queue.HeldSend.text("WRONG", board_id="b"))
    assert silence_queue.peek("a") is None
    assert silence_queue.peek("b") is None


@pytest.mark.parametrize(
    "hour,day,want",
    # v9's existing TimeService includes the exact ending instant.
    [
        (23, 24, "2026-10-25T07:00:00+00:00"),
        (1, 25, "2026-10-25T07:00:00+00:00"),
        (7, 25, "2026-10-25T07:00:00+00:00"),
        (12, 25, None),
    ],
)
def test_guard_window_end_crosses_midnight(setup_policy, hour, day, want):
    _, _, clock = setup_policy
    clock.set(datetime(2026, 10, day, hour, tzinfo=UTC))
    assert hasattr(board_guards, "silence_window_end"), "Window ending instant is missing"
    assert board_guards.silence_window_end("a") == want


def test_status_reports_held_preview_and_end_without_consuming(setup_policy):
    cm, client, _ = setup_policy
    cm.set_silence_schedule_for_board("a", {"show_queued_on_exit": True})
    silence_queue.hold(silence_queue.HeldSend.text("GOOD MORNING", board_id="a"))
    result = client.get("/silence-status").json()
    assert result.get("ends_at_utc") == "2026-10-25T07:00:00+00:00"
    assert result.get("holds_blocked_sends") is True
    assert result.get("held", {}).get("preview") == "GOOD MORNING"
    assert result["held"]["kind"] == "text"
    assert datetime.fromisoformat(result["held"]["queued_at"]).tzinfo is not None
    assert silence_queue.peek("a").payload == "GOOD MORNING"
    assert client.get("/silence-status?board_id=b").json()["held"] is None


def test_status_unknown_board_keeps_read_fallback(setup_policy):
    _, client, _ = setup_policy
    response = client.get("/silence-status?board_id=unknown")
    assert response.status_code == 200
    assert response.json().get("held", "missing") is None
    assert response.json().get("holds_blocked_sends") is False


def test_status_disabled_has_no_end(setup_policy):
    cm, client, _ = setup_policy
    cm.set_feature("silence_schedule", {"enabled": False})
    result = client.get("/silence-status").json()
    assert "ends_at_utc" in result
    assert result["ends_at_utc"] is None
    assert result["seconds_until_next_change"] is None


def test_discard_is_scoped_and_defaults_to_primary(setup_policy):
    _, client, _ = setup_policy
    silence_queue.hold(silence_queue.HeldSend.text("A", board_id="a"))
    silence_queue.hold(silence_queue.HeldSend.text("B", board_id="b"))
    response = client.delete("/silence-queue?board_id=b")
    assert response.status_code == 200
    assert response.json() == {"board_id": "b", "discarded": True}
    assert silence_queue.peek("a").payload == "A"
    assert client.delete("/silence-queue?board_id=b").json() == {"board_id": "b", "discarded": False}
    assert client.delete("/silence-queue").json() == {"board_id": "a", "discarded": True}


def test_discard_unknown_board_is_404_and_preserves_pending(setup_policy):
    _, client, _ = setup_policy
    silence_queue.hold(silence_queue.HeldSend.text("KEEP", board_id="a"))
    response = client.delete("/silence-queue?board_id=unknown")
    assert response.status_code == 404
    assert response.json()["detail"] == "Board not found: unknown"
    assert silence_queue.peek("a").payload == "KEEP"


def test_discard_with_no_configured_board_is_404(setup_policy, monkeypatch):
    _, client, _ = setup_policy
    monkeypatch.setattr(
        board_guards, "get_settings_service", lambda: SimpleNamespace(get_primary_board_id=lambda: None)
    )
    response = client.delete("/silence-queue")
    assert response.status_code == 404
    assert response.json()["detail"] == "No board is configured"


def test_settings_single_board_install_update_preserves_opt_in_before_pruning_override(setup_policy, monkeypatch):
    cm, client, _ = setup_policy
    service = SimpleNamespace(
        get_primary_board_id=lambda: "a",
        get_board_settings=lambda: SimpleNamespace(boards=[{"id": "a"}]),
    )
    monkeypatch.setattr("src.api_server.get_settings_service", lambda: service)
    cm.set_silence_schedule_for_board("a", {"show_queued_on_exit": True})
    result = client.put(
        "/settings/silence-schedule",
        json={"enabled": True, "start_time": "23:00+00:00", "end_time": "08:00+00:00"},
    )
    assert result.status_code == 200
    assert result.json()["config"]["show_queued_on_exit"] is True
    assert Config.silence_config_for("a")["show_queued_on_exit"] is True
    assert cm.get_feature("silence_schedule")["by_board"].get("a") is None
