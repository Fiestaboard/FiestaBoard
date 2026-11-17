# ruff: noqa: F811 - imported pytest fixtures intentionally use their registered names
"""Actual FastAPI boundary for a captured Compose intent and its later release."""

from datetime import UTC, datetime, timedelta

import pytest

from src import api_server, display_runtime, silence_queue
from src.config import Config
from src.send_outcome import SendOutcome
from src.settings.service import get_settings_service
from tests.test_auth_mobile_control_scope import auth  # noqa: F401
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
    config = {
        "enabled": True,
        "start_time": "00:00+00:00",
        "end_time": "23:59+00:00",
        "show_queued_on_exit": False,
        "mode": "freeze",
    }
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
    release = datetime.now(UTC) + timedelta(hours=7)
    from src.compose import service as compose

    monkeypatch.setattr(compose, "now", lambda: release)
    silence(monkeypatch, active=False)
    service._deliver_held_send(held, service.runtimes[board], wait=True)
    override = get_settings_service().get_temporary_override(board)
    assert datetime.fromisoformat(override.expires_at) == release + timedelta(minutes=120)
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
    end = start + timedelta(seconds=1)
    from src.compose import service as compose

    clock = [start]
    monkeypatch.setattr(compose, "now", lambda: clock[0])

    def finish_late(*args, **kwargs):
        clock[0] = end + timedelta(seconds=1)
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


def test_explicit_hold_releases_on_engine_tick_without_automatic_hold_policy(client, hardware, monkeypatch):
    service, drivers, (board, _) = hardware
    silence(monkeypatch)
    assert client.post(f"/v1/boards/{board}/compose", json=request()).status_code == 202
    silence(monkeypatch, active=False)
    service.check_and_send_for_board(board, service.runtimes[board], is_primary=True, wait=True)
    assert drivers[board].render.call_count == 1
    assert silence_queue.peek(board) is None
    assert get_settings_service().get_temporary_override(board) is not None


@pytest.mark.parametrize(
    "outcome,code,status",
    [
        (SendOutcome(True, False), 200, "unchanged"),
        (SendOutcome(True, False, throttled=True, retry_after_seconds=9), 429, "not_sent"),
        (SendOutcome(False, False, partial=True), 502, "partial"),
        (SendOutcome(False, False, superseded=True), 409, "superseded"),
        (SendOutcome(False, False), 502, "not_sent"),
    ],
)
def test_full_driver_outcome_controls_status_without_replay(client, hardware, outcome, code, status):
    _, drivers, (board, _) = hardware
    drivers[board].render.return_value = outcome
    body = request()
    first = client.post(f"/v1/boards/{board}/compose", json=body)
    assert first.status_code == code, first.text
    receipt = first.json() if code == 200 else first.json()["detail"]
    assert receipt["status"] == status
    second = client.post(f"/v1/boards/{board}/compose", json=body)
    assert second.json() == first.json() and second.status_code == code
    assert drivers[board].render.call_count == 1
    override = get_settings_service().get_temporary_override(board)
    assert (override is not None) is (status == "unchanged")
    if code == 429:
        assert first.headers["retry-after"] == "9"


def test_newer_manual_intent_during_ack_prevents_old_override_arm(client, hardware):
    _, drivers, (board, _) = hardware
    settings = get_settings_service()

    def newer(*args, **kwargs):
        from src.override_undo import _manual_operation

        with _manual_operation():
            pass
        return SendOutcome(True, True)

    drivers[board].render.side_effect = newer
    response = client.post(f"/v1/boards/{board}/compose", json=request())
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["status"] == "superseded"
    assert response.json()["detail"]["sent"] is True
    assert settings.get_temporary_override(board) is None


def test_replacement_held_intent_during_ack_is_never_consumed_or_armed(client, hardware, monkeypatch):
    service, drivers, (board, _) = hardware
    silence(monkeypatch)
    assert client.post(f"/v1/boards/{board}/compose", json=request()).status_code == 202
    captured = silence_queue.peek(board)
    replacement = silence_queue.HeldSend.compose(request(), board_id=board)

    def replace(*args, **kwargs):
        silence_queue.hold(replacement, strict=True)
        return SendOutcome(True, True)

    drivers[board].render.side_effect = replace
    silence(monkeypatch, active=False)
    service._deliver_held_send(captured, service.runtimes[board], wait=True)
    assert silence_queue.peek(board) == replacement
    assert get_settings_service().get_temporary_override(board) is None


def test_uuid_payload_change_is_a_conflict_without_second_write(client, hardware):
    _, drivers, (board, _) = hardware
    body = request()
    assert client.post(f"/v1/boards/{board}/compose", json=body).status_code == 200
    body["template"] = ["CHANGED"]
    assert client.post(f"/v1/boards/{board}/compose", json=body).status_code == 409
    assert drivers[board].render.call_count == 1


def test_ui_only_target_cannot_arm_an_override_or_dispatch(client, hardware):
    _, drivers, (board, _) = hardware
    get_settings_service().set_output_target("ui")
    response = client.post(f"/v1/boards/{board}/compose", json=request())
    assert response.status_code == 409, response.text
    assert get_settings_service().get_temporary_override(board) is None
    drivers[board].render.assert_not_called()


def test_held_absolute_expiry_never_dispatches_after_its_original_end(client, hardware, monkeypatch):
    service, drivers, (board, _) = hardware
    start = datetime.now(UTC)
    end = start + timedelta(minutes=5)
    silence(monkeypatch)
    body = request(prepared_at=start.isoformat(), duration={"kind": "until", "ends_at": end.isoformat()})
    assert client.post(f"/v1/boards/{board}/compose", json=body).status_code == 202
    held = silence_queue.peek(board)
    from src.compose import service as compose

    monkeypatch.setattr(compose, "now", lambda: end)
    silence(monkeypatch, active=False)
    service._deliver_held_send(held, service.runtimes[board], wait=True)
    drivers[board].render.assert_not_called()
    assert silence_queue.peek(board) is None
    assert get_settings_service().get_temporary_override(board) is None
    receipt = client.get(f"/v1/boards/{board}/compose/{body['request_id']}")
    assert receipt.status_code == 200 and receipt.json()["status"] == "expired"


def test_pending_outcome_is_readable_by_uuid_without_another_mutation(client, hardware):
    _, drivers, (board, _) = hardware
    body = request()
    response = client.post(f"/v1/boards/{board}/compose", json=body)
    assert response.status_code == 200
    receipt = client.get(f"/v1/boards/{board}/compose/{body['request_id']}")
    assert receipt.status_code == 200 and receipt.json() == response.json()
    assert receipt.headers["cache-control"] == "no-store"
    assert drivers[board].render.call_count == 1


def test_mobile_scope_and_uuid_receipts_are_bound_to_the_issuing_session(client, hardware, auth):
    from tests.test_auth_mobile_control_scope import IOS, TV, bearer_client, sign_in

    _, drivers, (board, _) = hardware
    first = bearer_client(sign_in(IOS)["access_token"])
    second = bearer_client(sign_in(IOS)["access_token"])
    television = bearer_client(sign_in(TV)["access_token"])
    body = request()
    assert first.post(f"/v1/boards/{board}/compose", json=body).status_code == 200
    assert second.post(f"/v1/boards/{board}/compose", json=body).status_code == 409
    assert second.get(f"/v1/boards/{board}/compose/{body['request_id']}").status_code == 409
    assert television.post(f"/v1/boards/{board}/compose", json=request()).status_code == 403
    assert client.post(f"/v1/boards/{board}/compose", json=request()).status_code == 401
    assert drivers[board].render.call_count == 1


def test_runtime_replacement_during_ack_never_arms_old_target(client, hardware):
    service, drivers, (board, _) = hardware
    from src.main import BoardRuntime

    def replace_runtime(*args, **kwargs):
        service.runtimes[board] = BoardRuntime(client=drivers[board], board_id=board)
        return SendOutcome(True, True)

    drivers[board].render.side_effect = replace_runtime
    response = client.post(f"/v1/boards/{board}/compose", json=request())
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["sent"] is True
    assert get_settings_service().get_temporary_override(board) is None


def test_failed_hold_persistence_returns_error_without_admitting_delivery(client, hardware, monkeypatch):
    _, drivers, (board, _) = hardware
    silence(monkeypatch)
    save = silence_queue._save_locked

    def fail_strict(**kwargs):
        if kwargs.get("strict"):
            raise OSError("read only")
        return save(**kwargs)

    monkeypatch.setattr(silence_queue, "_save_locked", fail_strict)
    response = client.post(f"/v1/boards/{board}/compose", json=request())
    assert response.status_code == 503, response.text
    assert silence_queue.peek(board) is None
    drivers[board].render.assert_not_called()


def test_timeout_reports_pending_and_worker_owns_later_override_arm(client, hardware, monkeypatch):
    import threading

    from src.compose import service as compose

    service, drivers, (board, _) = hardware
    entered, release = threading.Event(), threading.Event()

    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return SendOutcome(True, True)

    monkeypatch.setattr(compose, "SEND_WAIT_TIMEOUT", 0.02)
    drivers[board].render.side_effect = slow
    body = request()
    try:
        response = client.post(f"/v1/boards/{board}/compose", json=body)
        assert entered.wait(2)
        assert response.status_code == 202, response.text
        assert response.json()["status"] == "dispatching" and response.json()["sent"] is None
        assert get_settings_service()._override_mutations_pending > 0
        assert get_settings_service().get_temporary_override(board) is None
        duplicate = client.post(f"/v1/boards/{board}/compose", json=body)
        assert duplicate.status_code == 202 and drivers[board].render.call_count == 1
    finally:
        release.set()
        assert service.wait_until_idle(5)
    override = get_settings_service().get_temporary_override(board)
    assert override.compose_request_id == body["request_id"]
    assert get_settings_service()._override_mutations_pending == 0
    receipt = client.get(f"/v1/boards/{board}/compose/{body['request_id']}")
    assert receipt.status_code == 200 and receipt.json()["status"] == "sent"


def test_cancelled_http_await_keeps_terminal_worker_authority(client, hardware):
    import asyncio
    import threading

    import httpx

    service, drivers, (board, _) = hardware
    entered, release = threading.Event(), threading.Event()
    body = request()

    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return SendOutcome(True, True)

    drivers[board].render.side_effect = slow

    async def scenario():
        transport = httpx.ASGITransport(app=api_server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
            task = asyncio.create_task(http.post(f"/v1/boards/{board}/compose", json=body))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert get_settings_service()._override_mutations_pending > 0
                assert get_settings_service().get_temporary_override(board) is None
            finally:
                release.set()
                assert await asyncio.to_thread(service.wait_until_idle, 5)

    asyncio.run(scenario())
    assert get_settings_service().get_temporary_override(board).compose_request_id == body["request_id"]
    assert get_settings_service()._override_mutations_pending == 0
    assert drivers[board].render.call_count == 1


def test_replaced_pending_request_records_unsent_supersession(client, hardware, monkeypatch):
    import threading

    from src.compose import service as compose
    from src.displays.send_worker import SendJob

    service, drivers, (board, _) = hardware
    rt = service.runtimes[board]
    entered, release = threading.Event(), threading.Event()

    def blocker():
        entered.set()
        assert release.wait(5)
        return False

    service._worker_for(rt).submit(SendJob(key=("test-blocker",), run=blocker))
    assert entered.wait(2)
    monkeypatch.setattr(compose, "SEND_WAIT_TIMEOUT", 0.02)
    first, second = request(), request()
    try:
        assert client.post(f"/v1/boards/{board}/compose", json=first).status_code == 202
        assert client.post(f"/v1/boards/{board}/compose", json=second).status_code == 202
    finally:
        release.set()
        assert service.wait_until_idle(5)
    response = client.get(f"/v1/boards/{board}/compose/{first['request_id']}")
    assert response.json()["status"] == "superseded", response.text
    assert response.json()["sent"] is False
    assert drivers[board].render.call_count == 1
    assert get_settings_service().get_temporary_override(board).compose_request_id == second["request_id"]


def test_override_persistence_failure_never_leaves_an_in_memory_claim(client, hardware, monkeypatch):
    _, drivers, (board, _) = hardware
    settings = get_settings_service()
    monkeypatch.setattr(settings, "_save_to_file", lambda: (_ for _ in ()).throw(OSError("read only")))
    body = request()
    response = client.post(f"/v1/boards/{board}/compose", json=body)
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["status"] == "unknown"
    assert settings.get_temporary_override(board) is None
    assert drivers[board].render.call_count == 1
    duplicate = client.post(f"/v1/boards/{board}/compose", json=body)
    assert duplicate.status_code == 503 and drivers[board].render.call_count == 1


def test_record_mobile_authenticated_compose_corpus(client, hardware, auth, monkeypatch):
    """An opt-in artifact records actual ASGI wire responses, never bearer bytes."""
    import json
    import os
    from pathlib import Path

    from tests.test_auth_mobile_control_scope import IOS, bearer_client, sign_in

    service, drivers, (primary, secondary) = hardware
    phone = bearer_client(sign_in(IOS)["access_token"])
    records = []

    def capture(name, method, path, body=None, expected=200):
        response = phone.request(method, path, json=body)
        assert response.status_code == expected, response.text
        records.append(
            {
                "case": name,
                "method": method,
                "path": path,
                "request": body,
                "status": response.status_code,
                "response": response.json(),
                "headers": {
                    key: value for key, value in response.headers.items() if key in {"cache-control", "retry-after"}
                },
            }
        )
        return response

    capture("primary-capability", "GET", f"/v1/boards/{primary}")
    capture("secondary-capability", "GET", f"/v1/boards/{secondary}")
    timed = request()
    capture("formatted-timed-primary", "POST", f"/v1/boards/{primary}/compose", timed)
    capture("same-uuid-no-replay", "POST", f"/v1/boards/{primary}/compose", timed)
    capture("primary-readback", "GET", f"/v1/boards/{primary}")
    capture("uuid-poll", "GET", f"/v1/boards/{primary}/compose/{timed['request_id']}")
    capture(
        "indefinite-secondary",
        "POST",
        f"/v1/boards/{secondary}/compose",
        request(geometry={"device_type": "note"}, duration={"kind": "until_cancel"}),
    )
    silence(monkeypatch)
    held = request()
    capture("explicit-hold", "POST", f"/v1/boards/{primary}/compose", held, 202)
    queued = silence_queue.peek(primary)
    silence(monkeypatch, active=False)
    service._deliver_held_send(queued, service.runtimes[primary], wait=True)
    capture("held-release-receipt", "GET", f"/v1/boards/{primary}/compose/{held['request_id']}")
    get_settings_service().set_paused(True, board_id=primary)
    capture("paused", "POST", f"/v1/boards/{primary}/compose", request(silence="override"), 409)
    get_settings_service().set_paused(False, board_id=primary)
    capture(
        "geometry-mismatch", "POST", f"/v1/boards/{primary}/compose", request(geometry={"device_type": "note"}), 409
    )
    capture(
        "invalid-duration",
        "POST",
        f"/v1/boards/{primary}/compose",
        request(duration={"kind": "minutes", "minutes": 481}),
        422,
    )
    drivers[primary].render.return_value = SendOutcome(True, False, throttled=True, retry_after_seconds=9)
    capture("rate-limit", "POST", f"/v1/boards/{primary}/compose", request(), 429)
    drivers[primary].render.return_value = SendOutcome(False, False, partial=True)
    capture("partial", "POST", f"/v1/boards/{primary}/compose", request(), 502)
    drivers[primary].render.side_effect = OSError("synthetic driver acknowledgement lost")
    capture("unknown", "POST", f"/v1/boards/{primary}/compose", request(), 503)
    path = os.environ.get("COMPOSE_CORPUS_PATH")
    if path:
        Path(path).write_text(
            json.dumps(
                {
                    "protocol": "compose-intent-v1",
                    "source_sha": os.environ.get("COMPOSE_SOURCE_SHA"),
                    "boundary": "actual FastAPI ASGI with real synthetic mobile authentication; synthetic hardware drivers",
                    "records": records,
                },
                indent=2,
            )
        )


def test_openapi_declares_structured_compose_error_receipts():
    schema = api_server.app.openapi()
    response = schema["paths"]["/v1/boards/{board}/compose"]["post"]["responses"]["502"]
    assert response["content"]["application/json"]["schema"]["$ref"].endswith("/ComposeError")
    error = schema["components"]["schemas"]["ComposeError"]
    assert any(item.get("$ref", "").endswith("/ComposeReceipt") for item in error["properties"]["detail"]["anyOf"])


@pytest.mark.parametrize("consent,expected_writes", [("hold", 1), ("override", 2)])
def test_later_silence_never_promotes_hold_to_unconsented_override(
    client, hardware, monkeypatch, consent, expected_writes
):
    service, drivers, (board, _) = hardware
    silence(monkeypatch, active=False)
    response = client.post(f"/v1/boards/{board}/compose", json=request(silence=consent))
    assert response.status_code == 200
    service.runtimes[board].last_active_page_content = None
    drivers[board].render.return_value = (True, True)
    silence(monkeypatch)
    service.check_and_send_for_board(board, service.runtimes[board], is_primary=True, wait=True)
    assert drivers[board].render.call_count == expected_writes
    assert get_settings_service().get_temporary_override(board) is not None


def test_replaced_held_uuid_no_longer_claims_pending_delivery(client, hardware, monkeypatch):
    _, drivers, (board, _) = hardware
    silence(monkeypatch)
    first, second = request(), request()
    assert client.post(f"/v1/boards/{board}/compose", json=first).status_code == 202
    assert client.post(f"/v1/boards/{board}/compose", json=second).status_code == 202
    response = client.get(f"/v1/boards/{board}/compose/{first['request_id']}")
    assert response.json()["status"] == "superseded", response.text
    assert response.json()["sent"] is False
    assert silence_queue.peek(board).payload["request_id"] == second["request_id"]
    drivers[board].render.assert_not_called()


def test_compose_schema_preserves_existing_page_metadata_component_name():
    schemas = api_server.app.openapi()["components"]["schemas"]
    assert "LineMetadata" in schemas
    assert "alignment" in schemas["LineMetadata"]["properties"]


def test_real_driver_throttle_cannot_become_unchanged_or_arm_an_override(client, hardware):
    from tests.test_send_outcome import throttled_cloud_client

    service, _, (board, _) = hardware
    driver = throttled_cloud_client({"t": 1000.0}, elapsed=5)
    service.runtimes[board].client = driver
    body = request()
    response = client.post(f"/v1/boards/{board}/compose", json=body)
    assert response.status_code == 429, response.text
    assert response.headers["retry-after"] == "10"
    assert response.json()["detail"]["status"] == "not_sent"
    assert get_settings_service().get_temporary_override(board) is None
    assert client.post(f"/v1/boards/{board}/compose", json=body).json() == response.json()


def test_real_driver_partial_result_retains_failed_regions(client, hardware, monkeypatch):
    from src.send_outcome import FrameRegion
    from tests.first_party_drivers import local_driver

    service, _, (board, _) = hardware
    driver = local_driver(board_id=board)
    region = FrameRegion(0, 0, 3, 15)
    monkeypatch.setattr(
        driver.plugin, "write", lambda *args, **kwargs: SendOutcome(False, True, partial=True, failed_regions=(region,))
    )
    service.runtimes[board].client = driver
    response = client.post(f"/v1/boards/{board}/compose", json=request())
    assert response.status_code == 502, response.text
    assert response.json()["detail"]["status"] == "partial"
    assert response.json()["detail"]["failed_regions"] == [region.as_dict()]
    assert get_settings_service().get_temporary_override(board) is None


@pytest.mark.parametrize("indicator", ["", "SILENT"])
def test_compose_override_refreshes_and_expires_after_an_already_latched_silence(
    client, hardware, monkeypatch, indicator
):
    from src.board_chars import characters_to_message
    from src.pages.models import PageCreate
    from src.pages.service import get_page_service

    service, drivers, (board, _) = hardware
    settings = get_settings_service()
    page = get_page_service().create_page(PageCreate(name="Fallback", type="template", template=["NORMAL"]))
    settings.set_schedule_enabled(False, board_id=board)
    settings.set_active_page_id(page.id, board_id=board)
    silence(monkeypatch)
    config = {
        **Config.silence_config_for(board),
        "mode": "indicator",
        "indicator_text": indicator,
        "indicator_position": "center",
    }
    monkeypatch.setattr(Config, "silence_config_for", lambda board_id=None: config)
    rt = service.runtimes[board]
    rt.last_silence_mode_active = True
    rt.snoozing_message_sent = True
    rt.last_active_page_content = "snoozing"
    rt.last_active_page_id = "__silence__"
    response = client.post(f"/v1/boards/{board}/compose", json=request(template=["FIRST"], silence="override"))
    assert response.status_code == 200, response.text
    drivers[board].render.return_value = (True, True)
    rt.last_active_page_content = None
    service.check_and_send_for_board(board, rt, is_primary=True, wait=True)
    assert drivers[board].render.call_count == 2, "The active Compose override never reached the engine refresh path"
    override = settings.get_temporary_override(board)
    override.expires_at = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    service.check_and_send_for_board(board, rt, is_primary=True, wait=True)
    assert drivers[board].render.call_count == 3
    final = drivers[board].render.call_args.args[0]
    if indicator:
        assert indicator in characters_to_message(final)
    else:
        assert final == [[0] * 22 for _ in range(6)]
    assert settings.get_temporary_override(board) is None
    assert rt.last_active_page_id == "__silence__"
