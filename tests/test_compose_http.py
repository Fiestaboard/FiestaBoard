# ruff: noqa: F811 - imported pytest fixtures intentionally use their registered names
"""Actual FastAPI boundary for a captured Compose intent and its later release."""
from datetime import UTC, datetime, timedelta

import pytest

from src import api_server, display_runtime, silence_queue
from src.config import Config
from src.send_outcome import SendOutcome
from src.settings.service import get_settings_service
from tests.test_compose_intent import request
from tests.test_per_board_engine import _service_with_runtimes
from tests.test_v1_contract import boards, client  # noqa: F401


@pytest.fixture
def hardware(client, boards, monkeypatch):
    settings = get_settings_service()
    service, clients = _service_with_runtimes(settings.get_board_settings().boards)
    for driver in clients.values():
        driver.render.return_value = SendOutcome(True, True)
    monkeypatch.setattr(api_server, "get_service", lambda: service)
    monkeypatch.setattr(display_runtime, "get_service", lambda: service)
    silence_queue.clear()
    yield service, clients, boards
    for runtime in service.runtimes.values():
        if runtime.send_worker:
            runtime.send_worker.stop()
    silence_queue.clear()


def silence(monkeypatch, active=True):
    config = {"enabled": True, "start_time": "00:00+00:00", "end_time": "23:59+00:00", "show_queued_on_exit": False}
    monkeypatch.setattr(Config, "is_silence_mode_active", lambda board_id=None: active)
    monkeypatch.setattr(Config, "silence_config_for", lambda board_id=None: config)


def test_capability_is_explicit_per_target(client, hardware):
    _, _, (board, _) = hardware
    response = client.get(f"/v1/boards/{board}")
    assert response.status_code == 200
    assert response.json()["compose_protocol"] == "compose-intent-v1"


def test_sent_compose_preserves_original_template_formatting_and_readback_uuid(client, hardware):
    _, drivers, (board, _) = hardware
    body = request()
    result = client.post(f"/v1/boards/{board}/compose", json=body)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "sent" and result.json()["sent"] is True
    assert result.headers["cache-control"] == "no-store"
    override = get_settings_service().get_temporary_override(board)
    assert override.template == body["template"]
    assert override.line_metadata == body["line_metadata"]
    assert override.compose_request_id == body["request_id"]
    assert drivers[board].render.call_count == 1
    detail = client.get(f"/v1/boards/{board}").json()
    assert detail["compose_receipt"]["request_id"] == body["request_id"]


def test_duplicate_uuid_returns_original_expiry_without_second_write(client, hardware):
    _, drivers, (board, _) = hardware
    body = request()
    first = client.post(f"/v1/boards/{board}/compose", json=body)
    assert first.status_code == 200, first.text
    second = client.post(f"/v1/boards/{board}/compose", json=body)
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    assert drivers[board].render.call_count == 1


def test_pause_refuses_before_queue_or_driver_even_with_silence_override(client, hardware, monkeypatch):
    _, drivers, (board, _) = hardware
    get_settings_service().set_paused(True, board_id=board)
    silence(monkeypatch)
    result = client.post(f"/v1/boards/{board}/compose", json=request(silence="override"))
    assert result.status_code == 409
    assert silence_queue.peek(board) is None
    drivers[board].render.assert_not_called()


def test_explicit_hold_preserves_duration_even_when_automatic_holds_are_disabled(client, hardware, monkeypatch):
    _, drivers, (board, _) = hardware
    silence(monkeypatch)
    body = request()
    result = client.post(f"/v1/boards/{board}/compose", json=body)
    assert result.status_code == 202, result.text
    assert result.json()["status"] == "held" and result.json()["sent"] is False
    assert result.json()["expires_at"] is None
    assert result.json()["duration"] == body["duration"]
    held = silence_queue.peek(board)
    assert held.kind == "compose"
    assert held.payload["template"] == body["template"]
    assert held.payload["line_metadata"] == body["line_metadata"]
    assert get_settings_service().get_temporary_override(board) is None
    drivers[board].render.assert_not_called()


def test_held_duration_starts_on_actual_release_and_uses_original_formatting(client, hardware, monkeypatch):
    service, drivers, (board, _) = hardware
    silence(monkeypatch)
    body = request()
    assert client.post(f"/v1/boards/{board}/compose", json=body).status_code == 202
    held = silence_queue.peek(board)
    release = datetime.now(UTC)+timedelta(hours=7)
    from src.compose import service as compose
    monkeypatch.setattr(compose, "now", lambda: release)
    silence(monkeypatch, active=False)
    service._deliver_held_send(held, service.runtimes[board], wait=True)
    override = get_settings_service().get_temporary_override(board)
    assert datetime.fromisoformat(override.expires_at) == release+timedelta(minutes=120)
    assert override.template == body["template"] and override.line_metadata == body["line_metadata"]
    assert silence_queue.peek(board) is None
    assert drivers[board].render.call_count == 1


def test_explicit_until_cancel_is_not_an_ordinary_untimed_send(client, hardware):
    _, _, (board, _) = hardware
    body = request(duration={"kind": "until_cancel"})
    result = client.post(f"/v1/boards/{board}/compose", json=body)
    assert result.status_code == 200, result.text
    override = get_settings_service().get_temporary_override(board)
    assert override is not None and override.expires_at is None
    assert override.compose_request_id == body["request_id"]


@pytest.mark.parametrize("end", ["0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00", "NaN"])
def test_bad_offset_instants_are_http_422_not_server_errors(client, hardware, end):
    _, drivers, (board, _) = hardware
    result = client.post(f"/v1/boards/{board}/compose", json=request(duration={"kind": "until", "ends_at": end}))
    assert result.status_code == 422
    assert "OverflowError" not in result.text
    drivers[board].render.assert_not_called()


def test_absolute_end_expiring_during_driver_ack_is_not_rounded_or_indefinite(client, hardware, monkeypatch):
    _, drivers, (board, _) = hardware
    start = datetime.now(UTC)
    end = start+timedelta(seconds=1)
    from src.compose import service as compose
    clock = [start]
    monkeypatch.setattr(compose, "now", lambda: clock[0])
    def finish_late(*args, **kwargs):
        clock[0] = end+timedelta(seconds=1)
        return SendOutcome(True, True)
    drivers[board].render.side_effect = finish_late
    body = request(prepared_at=start.isoformat(), duration={"kind": "until", "ends_at": end.isoformat()})
    result = client.post(f"/v1/boards/{board}/compose", json=body)
    assert result.status_code == 409
    assert result.json()["detail"]["sent"] is True
    assert get_settings_service().get_temporary_override(board) is None
    assert drivers[board].render.call_count == 1


def test_stale_geometry_refuses_before_driver(client, hardware):
    _, drivers, (board, _) = hardware
    result = client.post(f"/v1/boards/{board}/compose", json=request(geometry={"device_type": "note"}))
    assert result.status_code == 409
    drivers[board].render.assert_not_called()
