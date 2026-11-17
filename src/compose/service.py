"""One-shot Compose delivery on the existing target's terminal send worker."""

import logging
from datetime import UTC, datetime

from src import display_runtime, silence_queue
from src.config import Config
from src.devices import geometry_of, resolve_dimensions
from src.displays.send_worker import SendJob
from src.outputs.cells import project_for_output
from src.outputs.display_profile import render_kw
from src.override_undo import _manual_operation, track_send_job
from src.send_outcome import WriteResult
from src.settings.service import TemporaryOverride, get_settings_service
from src.templates.engine import get_template_engine
from src.text_to_board import text_to_board_array

from .ledger import get_compose_ledger
from .models import ComposeRequest, InvalidComposeDuration

logger = logging.getLogger(__name__)
SEND_WAIT_TIMEOUT = 30.0


def now() -> datetime:
    return datetime.now(UTC)


def _entry(settings, board_id):
    return next((b for b in settings.get_board_settings().boards if b.get("id") == board_id), None)


def _policy(settings, request, board_id):
    entry = _entry(settings, board_id)
    if entry is None:
        return "The target display was removed"
    if tuple(geometry_of(entry)) != tuple(request.geometry.model_dump().values()):
        return "The captured display geometry has changed"
    if settings.is_paused(board_id=board_id):
        return "The target display is paused"
    if not settings.should_send_to_board():
        return "The install output target does not permit this send"
    return None


def _hold(request, board_id, ledger):
    held = silence_queue.HeldSend.compose(request.model_dump(mode="json"), board_id=board_id)
    silence_queue.hold(held, strict=True)
    from src.board_guards import silence_window_end

    return ledger.mark_held(request, board_id=board_id, held_until=silence_window_end(board_id))


def _reconcile(ledger, board_id):
    held = silence_queue.peek(board_id)
    current_id = held.payload.get("request_id") if held is not None and held.kind == "compose" else None
    ledger.reconcile_held(board_id=board_id, current_request_id=current_id)


def recorded_outcome(request_id, *, board_id, actor):
    settings = get_settings_service()
    ledger = get_compose_ledger()
    with settings.lock:
        _reconcile(ledger, board_id)
        return ledger.get(request_id, board_id=board_id, actor=actor)


def submit(request: ComposeRequest, *, board_id: str, actor: str):
    """Reserve a durable UUID before touching queue, runtime or hardware."""
    settings = get_settings_service()
    ledger = get_compose_ledger()
    with settings.lock:
        _reconcile(ledger, board_id)
        receipt, fresh = ledger.begin(request, board_id=board_id, actor=actor, now=now())
        if not fresh:
            return receipt
        with _manual_operation("compose:" + str(request.request_id)):
            reason = _policy(settings, request, board_id)
            if reason:
                return ledger.update(request, board_id=board_id, status="rejected", sent=False, reason=reason)
            if request.silence == "hold" and Config.is_silence_mode_active(board_id):
                try:
                    return _hold(request, board_id, ledger)
                except OSError:
                    return ledger.update(
                        request,
                        board_id=board_id,
                        status="unknown",
                        sent=False,
                        reason="The held intent could not be persisted",
                    )
            service = display_runtime.get_service()
            rt = service.get_runtime(board_id) if service is not None else None
            if rt is None or rt.client is None:
                return ledger.update(
                    request,
                    board_id=board_id,
                    status="unknown",
                    sent=False,
                    reason="The display runtime is unavailable",
                )
            job = _enqueue(request, board_id, service, rt, ledger, silence_queue.peek(board_id))
    if job is not None:
        job.wait(SEND_WAIT_TIMEOUT)
    return ledger.status(request, board_id=board_id)


def release(held, service, rt, *, wait=True) -> bool:
    """A typed Hold may dispatch once; a missing/terminal ledger never replays it."""
    request = ComposeRequest.model_validate(held.payload)
    settings = get_settings_service()
    ledger = get_compose_ledger()
    with settings.lock:
        if silence_queue.peek(held.board_id) != held:
            return False
        receipt = ledger.status(request, board_id=held.board_id)
        if receipt.status != "held":
            if receipt.status not in {"preparing", "dispatching"}:
                silence_queue.discard_if_current(held)
            return False
        if Config.is_silence_mode_active(held.board_id):
            return False
        with _manual_operation("compose-release:" + str(request.request_id)):
            job = _enqueue(request, held.board_id, service, rt, ledger, held)
    if wait and job is not None:
        job.wait(SEND_WAIT_TIMEOUT)
    return ledger.status(request, board_id=held.board_id).status == "sent"


def _enqueue(request, board_id, service, rt, ledger, expected_held):
    settings = get_settings_service()
    revision, control = settings.runtime_revision, settings.control_revision

    def current():
        return (
            get_settings_service() is settings
            and settings.runtime_revision == revision
            and settings.control_revision == control
            and service.runtimes.get(board_id) is rt
            and silence_queue.peek(board_id) == expected_held
        )

    def finish(status, *, sent=False, reason=None, **values):
        return ledger.update(request, board_id=board_id, status=status, sent=sent, reason=reason, **values)

    def refuse_before_send():
        if not current():
            finish("superseded", reason="A newer display action replaced this intent")
            return True
        reason = _policy(settings, request, board_id)
        if reason:
            finish("rejected", reason=reason)
            return True
        try:
            request.expires_at(released_at=now())
        except InvalidComposeDuration as exc:
            finish("expired", reason=str(exc))
            silence_queue.commit_if_matches(board_id, expected_held, lambda: None)
            return True
        if request.silence == "hold" and Config.is_silence_mode_active(board_id):
            _hold(request, board_id, ledger)
            return True
        return False

    def run():
        with settings.lock:
            if refuse_before_send():
                return False
        geometry = request.geometry.model_dump()
        metadata = [m.model_dump() for m in request.line_metadata] if request.line_metadata is not None else None
        content = get_template_engine().render_lines(
            request.template, line_metadata=metadata, **geometry, **render_kw(rt.client)
        )
        dims = resolve_dimensions(**geometry)
        characters, rich = project_for_output(rt.client, content, dims.rows, dims.cols, flap=text_to_board_array)
        with settings.lock:
            if refuse_before_send():
                return False
        try:
            outcome = WriteResult.of(rt.client.render(characters, device_type=request.geometry.device_type, **rich))
        except Exception:
            logger.exception("Compose driver did not return an authoritative outcome")
            finish("unknown", sent=None, reason="The display outcome is unknown; this request will not be replayed")
            return False
        with settings.lock:
            if not current():
                finish(
                    "superseded", sent=outcome.was_sent, reason="A newer action replaced this intent during delivery"
                )
                return False
            if outcome.throttled:
                finish(
                    "not_sent",
                    reason="The display send limit deferred this request",
                    retry_after_seconds=outcome.retry_after_seconds,
                )
                return False
            if outcome.partial:
                finish(
                    "partial",
                    sent=None,
                    reason="Only part of the display accepted the content",
                    failed_regions=[r.as_dict() for r in outcome.failed_regions],
                )
                return False
            if outcome.superseded:
                finish("superseded", reason="A newer display write replaced this content")
                return False
            if not outcome.success:
                finish("not_sent", reason="The display refused the content")
                return False
            released_at = now()
            try:
                expiry = request.expires_at(released_at=released_at)
            except InvalidComposeDuration as exc:
                finish("expired", sent=outcome.was_sent, reason=str(exc))
                silence_queue.commit_if_matches(board_id, expected_held, lambda: None)
                return False

            def commit():
                override = TemporaryOverride(
                    template=list(request.template),
                    line_metadata=metadata,
                    expires_at=expiry,
                    compose_request_id=str(request.request_id),
                    compose_sent=outcome.was_sent,
                    compose_duration=request.duration.model_dump(),
                    compose_silence=request.silence,
                    **geometry,
                )
                settings.set_temporary_override(
                    override, board_id, started_at=released_at.isoformat(), rollback_on_error=True
                )
                ledger.delivered(request, board_id=board_id, released_at=released_at, sent=outcome.was_sent)
                rt.last_active_page_content = content
                rt.last_active_page_id = "__adhoc__"
                rt.content_delivered()

            if not silence_queue.commit_if_matches(board_id, expected_held, commit):
                finish("superseded", sent=outcome.was_sent, reason="A newer held intent replaced this content")
                return False
            return outcome.was_sent

    worker = service._worker_for(rt)
    if worker is None:
        finish("superseded", reason="The display runtime was replaced")
        return None
    if not ledger.mark_dispatching(request, board_id=board_id):
        return None
    settled = track_send_job(("compose", str(request.request_id)))

    executed = False

    def terminal():
        try:
            if ledger.status(request, board_id=board_id).status == "dispatching":
                finish(
                    "unknown" if executed else "superseded",
                    sent=None if executed else False,
                    reason=(
                        "The worker ended without an outcome; no replay is permitted"
                        if executed
                        else "A newer queued write replaced this unsent request"
                    ),
                )
        finally:
            if settled is not None:
                settled()

    def guarded_run():
        nonlocal executed
        executed = True
        try:
            return run()
        except Exception:
            logger.exception("Compose delivery bookkeeping failed")
            finish("unknown", sent=None, reason="The final display state could not be recorded; no replay is permitted")
            return False

    job = SendJob(key=("compose", str(request.request_id)), run=guarded_run, board_id=board_id, on_settled=terminal)
    rt.output.preempt()
    try:
        worker.submit(job)
    except BaseException:
        job._finish(False, reason="Compose submission failed")
        raise
    return job


def readback(override):
    """Nonsecret correlation from the active override, never an inferred success."""
    if override is None or override.compose_request_id is None:
        return None
    return {
        "protocol": "compose-intent-v1",
        "request_id": override.compose_request_id,
        "status": "sent" if override.compose_sent else "unchanged",
        "sent": override.compose_sent,
        "started_at": override.started_at,
        "expires_at": override.expires_at,
        "duration": override.compose_duration,
    }
