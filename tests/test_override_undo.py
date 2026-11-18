"""Atomic cancel authority never becomes an unconditional override write."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from src.auth.scopes import CONTROL, TV_PANELS, permits
from src.settings.service import SettingsService, TemporaryOverride
from tests.test_auth_mobile_control_scope import auth, phone, tv  # noqa: F401 - fixtures


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "board": {
                    "boards": [
                        {"id": "a", "name": "A", "device_type": "flagship"},
                        {"id": "b", "name": "B", "device_type": "flagship"},
                    ]
                }
            }
        )
    )
    return SettingsService(str(path))


def start(store, **kwargs):
    value = TemporaryOverride(
        template=["HELLO"],
        line_metadata=[{"align": "center"}],
        expires_at=(datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        **kwargs,
    )
    store.set_temporary_override(value, "a")
    return value.to_dict()


def cancel(store, actor="phone-1"):
    return store.cancel_temporary_override("a", actor=actor, undo=True)


def restore(store, token, board="a", actor="phone-1"):
    return store.undo_temporary_override(board, token, actor=actor)


def test_cancel_restores_exact_payload_and_original_expiry_and_run(store):
    original = start(store)
    _, token, deadline = cancel(store)
    assert store.get_temporary_override("a") is None
    assert datetime.fromisoformat(deadline) <= datetime.now(UTC) + timedelta(seconds=30)
    assert restore(store, token).to_dict() == original
    assert SettingsService(str(store.settings_file)).get_temporary_override("a").to_dict() == original
    with pytest.raises(ValueError):
        restore(store, token)


def test_receipt_is_bound_to_display_and_actor(store):
    start(store)
    _, token, _ = cancel(store)
    for board, actor in [("b", "phone-1"), ("a", "phone-2")]:
        with pytest.raises(ValueError):
            restore(store, token, board, actor)
    assert restore(store, token).template == ["HELLO"]


def test_receipt_cannot_restore_a_replacement_even_after_replacement_cancel(store):
    start(store)
    _, token, _ = cancel(store)
    store.set_temporary_override(TemporaryOverride(page_id="replacement"), "a")
    store.clear_temporary_override("a")
    with pytest.raises(ValueError):
        restore(store, token)
    assert store.get_temporary_override("a") is None


def test_original_expiry_and_short_receipt_deadline_are_both_enforced(store):
    start(store)
    _, token, _ = cancel(store)
    with patch("src.settings.service.time.monotonic", return_value=10**15):
        with pytest.raises(ValueError):
            restore(store, token)
    start(store)
    _, token, _ = cancel(store)
    with patch.object(TemporaryOverride, "is_expired", return_value=True):
        with pytest.raises(ValueError):
            restore(store, token)


def test_restart_and_reload_discard_receipt_authority(store):
    start(store)
    _, token, _ = cancel(store)
    with pytest.raises(ValueError):
        restore(SettingsService(str(store.settings_file)), token)
    store.reload()
    with pytest.raises(ValueError):
        restore(store, token)


def test_cancel_applies_page_revert_before_issuing_receipt(store):
    start(store, revert_mode="page", revert_page_id="after")
    _, token, _ = cancel(store)
    assert store.get_active_page_id("a") == "after"
    assert restore(store, token).revert_page_id == "after"


def test_concurrent_restores_have_one_winner(store):
    start(store)
    _, token, _ = cancel(store)

    def attempt(_):
        try:
            restore(store, token)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(16))) == 1


def test_pending_mutation_blocks_without_consuming_and_failure_preserves_receipt(store):
    start(store)
    _, token, _ = cancel(store)
    store.begin_override_mutation()
    with pytest.raises(ValueError):
        restore(store, token)
    store.finish_override_mutation(success=False)
    assert restore(store, token).template == ["HELLO"]


def test_successful_relevant_mutation_invalidates_receipt(store):
    start(store)
    _, token, _ = cancel(store)
    store.begin_override_mutation()
    store.finish_override_mutation(success=True)
    with pytest.raises(ValueError):
        restore(store, token)


def test_unrelated_settings_save_keeps_the_receipt(store):
    start(store)
    _, token, _ = cancel(store)
    store.set_polling_interval(42)
    assert restore(store, token).template == ["HELLO"]


def test_another_displays_cancel_keeps_the_receipt(store):
    start(store)
    store.set_temporary_override(TemporaryOverride(template=["B"]), "b")
    _, token, _ = cancel(store)
    _, other, _ = store.cancel_temporary_override("b", actor="phone-1", undo=True)
    assert other
    assert restore(store, token).template == ["HELLO"]
    assert restore(store, other, board="b").template == ["B"]


def test_another_displays_page_and_expiry_keep_the_receipt(store):
    start(store)
    expired = TemporaryOverride(template=["OLD"], expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat())
    store.set_temporary_override(expired, "b")
    _, token, _ = cancel(store)
    store.set_active_page_id("p2", board_id="b")
    assert store.get_temporary_override("b") is None  # expiry GC saves
    assert restore(store, token).template == ["HELLO"]


@pytest.mark.parametrize(
    "change",
    [
        lambda store: store.set_active_page_id("p2", board_id="a"),
        lambda store: store.remove_board("a"),
    ],
)
def test_a_change_to_the_same_display_revokes_the_receipt(store, change):
    start(store)
    _, token, _ = cancel(store)
    change(store)
    with pytest.raises(ValueError):
        restore(store, token)


def test_a_page_set_and_set_back_never_revives_the_receipt(store):
    start(store)
    _, token, _ = cancel(store)
    before = store.get_active_page_id("a")
    store.set_active_page_id("p2", board_id="a")
    store.set_active_page_id(before, board_id="a")
    with pytest.raises(ValueError):
        restore(store, token)


def test_failed_restore_persistence_consumes_receipt(store):
    start(store)
    _, token, _ = cancel(store)
    with patch.object(store, "_save_to_file", side_effect=OSError("full")):
        with pytest.raises(OSError):
            restore(store, token)
    with pytest.raises(ValueError):
        restore(store, token)


def test_exact_mobile_scope_addition_does_not_grant_admin_or_tv_access():
    assert permits(CONTROL, "POST", "/settings/temporary-override/undo")
    assert not permits(CONTROL, "PUT", "/settings/temporary-override/undo")
    assert not permits(TV_PANELS, "POST", "/settings/temporary-override/undo")
    assert not permits(CONTROL, "POST", "/settings/reload")


@pytest.fixture
def http(store, monkeypatch):
    from fastapi.testclient import TestClient

    import src.settings.service as services
    from src import api_server
    from src.settings import routes

    monkeypatch.setattr(services, "get_settings_service", lambda: store)
    monkeypatch.setattr(api_server, "get_settings_service", lambda: store)
    monkeypatch.setattr(routes, "_drop_board_cache", lambda board: None)
    return TestClient(api_server.app)


def test_http_opt_in_receipt_and_one_use_restore(http, store):
    original = start(store)
    result = http.delete("/settings/temporary-override?board_id=a&undo=true")
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    token = result.json()["undo_token"]
    assert token
    result = http.post("/settings/temporary-override/undo", json={"board_id": "a", "undo_token": token})
    assert result.status_code == 200, result.text
    assert result.json()["expires_at"] == original["expires_at"]
    assert (
        http.post("/settings/temporary-override/undo", json={"board_id": "a", "undo_token": token}).status_code == 409
    )


def test_legacy_cancel_keeps_its_exact_response(http, store):
    start(store)
    response = http.delete("/settings/temporary-override?board_id=a")
    assert response.status_code == 200
    assert response.json() == {"revert_mode": "schedule"}


def test_a_successful_manual_write_over_http_revokes_the_receipt(http, store, monkeypatch):
    # The send job the write starts would revoke it too; take it out so the
    # middleware's 2xx rule is what this pins.
    monkeypatch.setattr("src.main.track_send_job", lambda key: None)
    monkeypatch.setattr("src.board_send_executor.track_send_job", lambda key: None)
    start(store)
    token = http.delete("/settings/temporary-override?board_id=a&undo=true").json()["undo_token"]
    # Another display: only the middleware's 2xx rule can revoke display a's receipt.
    written = http.put("/settings/active-page", json={"page_id": None, "board_id": "b"})
    assert 200 <= written.status_code < 300, written.text
    result = http.post("/settings/temporary-override/undo", json={"board_id": "a", "undo_token": token})
    assert result.status_code == 409


def test_a_refused_manual_write_over_http_keeps_the_receipt(http, store):
    start(store)
    token = http.delete("/settings/temporary-override?board_id=a&undo=true").json()["undo_token"]
    refused = http.put("/settings/active-page", json={"page_id": "missing-page", "board_id": "a"})
    assert refused.status_code == 404, refused.text
    result = http.post("/settings/temporary-override/undo", json={"board_id": "a", "undo_token": token})
    assert result.status_code == 200, result.text


def test_internal_page_save_invalidates_http_receipt(http, store):
    from src.pages.service import get_page_service

    start(store)
    token = http.delete("/settings/temporary-override?board_id=a&undo=true").json()["undo_token"]
    # Simulates an internal/SSE/background writer after its HTTP response.
    pages = get_page_service().storage
    with pages.lock:
        pages._save()
    result = http.post("/settings/temporary-override/undo", json={"board_id": "a", "undo_token": token})
    assert result.status_code == 409


def test_preview_and_failed_mutation_do_not_invalidate_receipt(http, store):
    # The production engine is ordinarily initialized at startup; its first
    # registry bootstrap can persist plugin defaults, an actual config change.
    assert http.post("/templates/validate", json={"template": ["HELLO"]}).status_code == 200
    start(store)
    token = http.delete("/settings/temporary-override?board_id=a&undo=true").json()["undo_token"]
    assert http.post("/templates/validate", json={"template": ["HELLO"]}).status_code == 200
    assert http.put("/pages/missing-page", json={"name": "X"}).status_code >= 400
    assert (
        http.post("/settings/temporary-override/undo", json={"board_id": "a", "undo_token": token}).status_code == 200
    )


def test_restore_rejects_unknown_display_and_client_payload(http, store):
    start(store)
    token = http.delete("/settings/temporary-override?board_id=a&undo=true").json()["undo_token"]
    assert (
        http.post("/settings/temporary-override/undo", json={"board_id": "gone", "undo_token": token}).status_code
        == 404
    )
    assert (
        http.post(
            "/settings/temporary-override/undo", json={"board_id": "a", "undo_token": token, "expires_at": "2099-01-01"}
        ).status_code
        == 422
    )


def test_native_receipt_bound_to_issuing_session_and_tv_denied(http, store, phone, tv):  # noqa: F811
    from tests.test_auth_mobile_control_scope import IOS, bearer_client, sign_in

    first, _ = phone
    television, _ = tv
    second = bearer_client(sign_in(IOS)["access_token"])
    start(store)
    token = first.delete("/settings/temporary-override?board_id=a&undo=true").json()["undo_token"]
    body = {"board_id": "a", "undo_token": token}
    assert television.post("/settings/temporary-override/undo", json=body).status_code == 403
    assert second.post("/settings/temporary-override/undo", json=body).status_code == 409
    assert first.post("/settings/temporary-override/undo", json=body).status_code == 200


def test_unauthenticated_send_does_not_invalidate_native_receipt(http, store, phone):  # noqa: F811
    first, _ = phone
    start(store)
    token = first.delete("/settings/temporary-override?board_id=a&undo=true").json()["undo_token"]
    assert http.post("/send-message", json={"text": "NO"}).status_code == 401
    assert (
        first.post("/settings/temporary-override/undo", json={"board_id": "a", "undo_token": token}).status_code == 200
    )


def test_internal_manual_writer_blocks_undo_during_run_and_invalidates_after(store, monkeypatch):
    import src.settings.service as services
    from src.override_undo import manual_mutation

    monkeypatch.setattr(services, "get_settings_service", lambda: store)
    start(store)
    _, token, _ = cancel(store)

    @manual_mutation
    def writer():
        with pytest.raises(ValueError, match="in progress"):
            restore(store, token)
        return {"status": "success"}

    writer()
    with pytest.raises(ValueError):
        restore(store, token)


def test_no_authority_or_content_is_written_to_disk_by_cancellation(store):
    start(store)
    _, token, _ = cancel(store)
    persisted = store.settings_file.read_text()
    assert token not in persisted
    assert "HELLO" not in persisted


def test_content_generation_mismatch_prevents_restore(store):
    start(store)
    _, token, _ = store.cancel_temporary_override("a", actor="phone-1", undo=True, content_revision=("before",))
    with pytest.raises(ValueError):
        store.undo_temporary_override("a", token, actor="phone-1", content_revision=("after",))


def test_capability_is_explicit_on_override_status(http):
    assert http.get("/settings/temporary-override?board_id=a").json()["undo_supported"] is True


def test_receipt_deadline_never_exceeds_original_expiry(store):
    original = TemporaryOverride(page_id="short", expires_at=(datetime.now(UTC) + timedelta(seconds=2)).isoformat())
    store.set_temporary_override(original, "a")
    _, _, deadline = cancel(store)
    assert datetime.fromisoformat(deadline) <= datetime.fromisoformat(original.expires_at)


def test_non_ascii_token_is_a_refusal_not_a_server_error(store):
    start(store)
    cancel(store)
    with pytest.raises(ValueError):
        restore(store, "é")


def test_cold_preview_config_bootstrap_conservatively_refuses_receipt(http, store):
    start(store)
    token = http.delete("/settings/temporary-override?board_id=a&undo=true").json()["undo_token"]
    from src.config_manager import get_config_manager

    before = get_config_manager().config_generation
    assert http.post("/templates/validate", json={"template": ["HELLO"]}).status_code == 200
    assert get_config_manager().config_generation > before
    assert (
        http.post("/settings/temporary-override/undo", json={"board_id": "a", "undo_token": token}).status_code == 409
    )


def test_reload_does_not_forget_an_in_flight_manual_writer(store):
    store.begin_override_mutation()
    store.reload()
    start(store)
    _, token, _ = cancel(store)
    with pytest.raises(ValueError, match="in progress"):
        restore(store, token)
    store.finish_override_mutation(success=True)
    with pytest.raises(ValueError):
        restore(store, token)


@pytest.mark.parametrize("path", ["/pages/p1/send", "/settings/active-page", "/v1/boards/a/active-page"])
def test_every_physical_write_front_door_enters_barrier(path):
    from src.override_undo import _MANUAL

    assert _MANUAL.fullmatch(path)


def test_uncertain_executor_error_invalidates_receipt(store, monkeypatch):
    import src.settings.service as services
    from src.override_undo import manual_mutation

    monkeypatch.setattr(services, "get_settings_service", lambda: store)
    start(store)
    _, token, _ = cancel(store)

    @manual_mutation
    def timed_out_after_hardware_write():
        return {"status": "error", "error": "timeout after dispatch"}

    timed_out_after_hardware_write()
    with pytest.raises(ValueError):
        restore(store, token)


def test_async_internal_mutation_owns_barrier_until_awaited_completion(store, monkeypatch):
    import asyncio

    import src.settings.service as services
    from src.override_undo import manual_mutation

    monkeypatch.setattr(services, "get_settings_service", lambda: store)
    start(store)
    _, token, _ = cancel(store)

    @manual_mutation
    async def write():
        await asyncio.sleep(0)
        with pytest.raises(ValueError, match="in progress"):
            restore(store, token)
        return {"status": "success"}

    asyncio.run(write())
    with pytest.raises(ValueError):
        restore(store, token)


def test_worker_barrier_retires_only_when_superseding_job_finishes(store):
    from src.displays.send_worker import SendJob

    start(store)
    _, token, _ = cancel(store)
    store.begin_override_mutation()
    old = SendJob(
        key=("trigger", "old"), run=lambda: True, on_settled=lambda: store.finish_override_mutation(success=True)
    )
    latest = SendJob(key=("page", "new"), run=lambda: True)
    latest.adopt(old)
    with pytest.raises(ValueError, match="in progress"):
        restore(store, token)
    latest.execute()
    assert store._override_mutations_pending == 0
    with pytest.raises(ValueError):
        restore(store, token)


def test_fire_and_forget_trigger_blocks_receipt_issued_after_enqueue(store, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    import src.settings.service as services
    from src.main import DisplayService

    monkeypatch.setattr(services, "get_settings_service", lambda: store)
    runtime = SimpleNamespace(board_id="a", output=SimpleNamespace(preempt=Mock()), last_active_page_id=None)
    import threading

    service = DisplayService.__new__(DisplayService)
    service._send_capture = threading.local()
    service.runtimes = {"a": runtime}
    pending = []
    monkeypatch.setattr(service, "_worker_for", lambda rt: SimpleNamespace(submit=pending.append))
    assert service._dispatch_send(
        runtime,
        "a",
        key=("trigger", "HI"),
        send=lambda: (True, True),
        on_complete=lambda *args: False,
        wait=False,
        sink=None,
    )
    start(store)
    _, token, _ = cancel(store)
    with pytest.raises(ValueError, match="in progress"):
        restore(store, token)
    pending[0].execute()
    assert store._override_mutations_pending == 0
    with pytest.raises(ValueError):
        restore(store, token)


def test_real_executor_write_then_timeout_invalidates_receipt(store, monkeypatch):
    from types import SimpleNamespace

    import src.settings.service as services
    from src.ops import executors

    start(store)
    _, token, _ = cancel(store)
    writes = []

    def uncertain_render(*args, **kwargs):
        writes.append("physical write attempted")
        raise TimeoutError("response lost after sending")

    target = SimpleNamespace(client=SimpleNamespace(render=uncertain_render))
    monkeypatch.setattr(services, "get_settings_service", lambda: store)
    monkeypatch.setattr(executors, "_resolve_send_target", lambda *args, **kwargs: (target, None))
    monkeypatch.setattr(executors, "_transition_for", lambda *args, **kwargs: (None, None, None))
    result = executors.send_characters([[1]], board_id="a")
    assert writes == ["physical write attempted"]
    assert result["status"] == "error"
    with pytest.raises(ValueError):
        restore(store, token)


def test_stopped_worker_retires_manual_authority_without_leaking_pending_count(store):
    from src.displays.send_worker import BoardSendWorker, SendJob

    start(store)
    _, token, _ = cancel(store)
    worker = BoardSendWorker("undo-stopped")
    worker.stop()
    store.begin_override_mutation()
    job = SendJob(
        key=("trigger", "stopped"), run=lambda: True, on_settled=lambda: store.finish_override_mutation(success=True)
    )
    worker.submit(job)
    assert job.wait(0)
    assert store._override_mutations_pending == 0
    with pytest.raises(ValueError):
        restore(store, token)


def test_root_path_double_form_tracks_the_actual_routed_write(store, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import src.settings.service as services
    from src.override_undo import OverrideMutationMiddleware

    monkeypatch.setattr(services, "get_settings_service", lambda: store)
    app = FastAPI(root_path="/api")
    app.add_middleware(OverrideMutationMiddleware)

    @app.post("/pages/{page_id}/send")
    async def send(page_id: str):
        return {"pending": store._override_mutations_pending}

    result = TestClient(app).post("/api/pages/p/send")
    assert result.status_code == 200
    assert result.json()["pending"] > 0


def test_mqtt_active_page_physical_phase_has_manual_authority(store, monkeypatch):
    from types import SimpleNamespace

    import src.settings.service as services
    from src.mqtt.commands import CommandHandler

    monkeypatch.setattr(services, "get_settings_service", lambda: store)
    observed = []
    handler = CommandHandler(SimpleNamespace())
    monkeypatch.setattr(
        handler,
        "_display_service",
        lambda: SimpleNamespace(check_and_send_active_page=lambda: observed.append(store._override_mutations_pending)),
    )
    monkeypatch.setattr(handler, "_invalidate_board_content", lambda board: None)
    handler._force_send_active_page(None)
    assert observed and observed[0] > 0


def test_output_action_hardware_phase_blocks_undo(store, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    import src.settings.service as services
    from src.outputs.actions import execute_action

    monkeypatch.setattr(services, "get_settings_service", lambda: store)
    start(store)
    _, token, _ = cancel(store)

    class Output:
        @staticmethod
        def handle_action(context):
            with pytest.raises(ValueError, match="in progress"):
                restore(store, token)
            return {"status": "ok"}

    asyncio.run(
        execute_action(
            SimpleNamespace(plugin_class=Output, id="test"), "identify", board={"id": "a"}, board_id="a", inputs={}
        )
    )
    with pytest.raises(ValueError):
        restore(store, token)


def test_cancelling_await_does_not_end_a_running_hardware_thread_barrier(store, monkeypatch):
    import asyncio
    import threading

    import src.settings.service as services
    from src.board_send_executor import run_board_send
    from src.override_undo import manual_mutation

    monkeypatch.setattr(services, "get_settings_service", lambda: store)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    def hardware():
        entered.set()
        try:
            assert release.wait(5)
        finally:
            finished.set()

    @manual_mutation
    async def request():
        await run_board_send(hardware)

    async def exercise():
        task = asyncio.create_task(request())
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            start(store)
            _, token, _ = cancel(store)
            with pytest.raises(ValueError, match="in progress"):
                restore(store, token)
        finally:
            release.set()
            assert await asyncio.to_thread(finished.wait, 2)
            for _ in range(100):
                if store._override_mutations_pending == 0:
                    break
                await asyncio.sleep(0.01)
        assert store._override_mutations_pending == 0

    asyncio.run(exercise())
