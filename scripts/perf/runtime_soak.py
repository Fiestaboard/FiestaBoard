"""Monotonic, bounded-arrival soak driver; execution must be serialized by the operator."""

import math
import time
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

from runtime_common import JsonlWriter, ProtocolError, SOURCE_COMMIT
from runtime_common import require_ok
from runtime_api import ApiOperation, api_operations
from runtime_collect import validate_collector_anchor
from runtime_seed import verify_manifest


class WarmupScenarios:
    def __init__(self, manifest, *, utcnow=None, elapsed_clock=None):
        self.manifest = manifest
        self.board = manifest["boards"]["flagship"]
        self.utcnow = utcnow or (lambda: datetime.now(timezone.utc))
        self.elapsed_clock = elapsed_clock
        self.state = "override_start"
        self.failed = False
        self.events = []
        self.elapsed = 0
        self.completed_elapsed = None
        self.override_expires = None
        self.quiet = None
        self.quiet_end = None

    def _check(self, condition):
        if not condition:
            self.failed = True
            raise ProtocolError("Warmup transition/frame assertion failed; explicit recovery required")

    def _frame(self, body, marker, *, baseline=False):
        frame = body.get("characters")
        self._check(body.get("id") == self.board["id"] and isinstance(frame, list) and len(frame) == self.board["rows"]
                    and all(isinstance(row, list) and len(row) == self.board["cols"] for row in frame)
                    and body.get("expected_characters") == frame and marker in (body.get("text") or ""))
        if baseline:
            self._check(body.get("active_page_id") == self.board["page_ids"][0]
                        and body.get("resolved_page_id") == self.board["page_ids"][0])

    def _operation(self, name, method, path, payload, validate, *, status=200):
        def observed(body):
            validate(body)
            elapsed = self.elapsed_clock() if self.elapsed_clock is not None else self.elapsed
            self.events.append({"operation": name, "elapsed_s": elapsed, "observed_utc": self.utcnow().isoformat(), "state": self.state})
            if self.state == "complete":
                self.completed_elapsed = elapsed
        return ApiOperation(name, "flagship", "warmup-control", method, path, payload, observed,
                            expected_status=status, abort_on_failure=True)

    def next_operation(self, elapsed):
        self.elapsed = elapsed
        if self.failed:
            raise ProtocolError("Warmup controls failed; explicit operator recovery required")
        if self.state == "complete":
            return None
        if elapsed >= 300:
            self.failed = True
            raise ProtocolError("Warmup controls/restoration did not complete by300 seconds")
        bid = self.board["id"]
        page_id = self.board["page_ids"][0]
        marker = next(p["name"] for p in self.manifest["pages"] if p["id"] == page_id)
        if self.state == "override_start":
            payload = {"board_id": bid, "page_id": self.board["page_ids"][1], "duration_minutes": 1,
                       "revert_mode": "page", "revert_page_id": page_id}
            def begin(body):
                self._check(body.get("active") is True and body.get("board_id") == bid and body.get("page_id") == payload["page_id"])
                try:
                    self.override_expires = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
                    self._check(self.override_expires.tzinfo is not None and self.override_expires > self.utcnow())
                except (KeyError, ValueError, TypeError):
                    self._check(False)
                self.state = "override_wait"
            return self._operation("override_begin", "POST", "/api/settings/temporary-override", payload, begin)
        if self.state == "override_wait":
            def expiry(body):
                self._check(body.get("board_id") == bid and isinstance(body.get("active"), bool))
                if body["active"] is False:
                    self._check(self.utcnow() >= self.override_expires)
                    self.state = "override_frame"
            return self._operation("override_expiry_poll", "GET", f"/api/settings/temporary-override?board_id={bid}", None, expiry)
        if self.state == "override_frame":
            def restored(body):
                self._frame(body, marker, baseline=True)
                self.state = "silence_start"
            return self._operation("override_restored_frame", "GET", f"/api/v1/boards/{bid}", None, restored)
        if self.state == "silence_start":
            start = self.utcnow().replace(second=0, microsecond=0) + timedelta(minutes=1)
            self.quiet_end = start + timedelta(minutes=1)
            self.quiet = {"board_id": bid, "enabled": True, "start_time": start.strftime("%H:%M+00:00"),
                          "end_time": self.quiet_end.strftime("%H:%M+00:00"), "mode": "freeze", "show_queued_on_exit": True}
            def configured(body):
                config = body.get("config", {})
                self._check(body.get("board_id") == bid and config.get("enabled") is True and config.get("show_queued_on_exit") is True)
                self.state = "silence_wait"
            return self._operation("silence_configure", "PUT", "/api/settings/silence-schedule", self.quiet, configured)
        if self.state == "silence_wait":
            def quiet(body):
                self._check(body.get("board_id") == bid and body.get("enabled") is True and isinstance(body.get("active"), bool))
                if body["active"]:
                    self.state = "silence_hold"
                else:
                    self._check(self.utcnow() < self.quiet_end)
            return self._operation("silence_enter_poll", "GET", f"/api/silence-status?board_id={bid}", None, quiet)
        if self.state == "silence_hold":
            def held(body):
                self._check(body.get("board_id") == bid and body.get("held") is True and body.get("sent") is False and body.get("silenced") is True)
                self.state = "silence_queue"
            return self._operation("silence_held_send", "POST", f"/api/v1/boards/{bid}/message",
                                   {"lines": ["PERF HELD"] + [""] * (self.board["rows"] - 1)}, held, status=202)
        if self.state == "silence_queue":
            def queued(body):
                held = body.get("held")
                self._check(body.get("board_id") == bid and body.get("enabled") is True and
                            isinstance(held, dict) and held.get("kind") == "lines" and "PERF HELD" in held.get("preview", ""))
                self.state = "silence_release"
            return self._operation("silence_queue_verify", "GET", f"/api/silence-status?board_id={bid}", None, queued)
        if self.state == "silence_release":
            def released(body):
                self._check(body.get("board_id") == bid and body.get("enabled") is True and isinstance(body.get("active"), bool))
                if body.get("active") is False and body.get("held") is None:
                    self._check(self.utcnow() >= self.quiet_end)
                    self.state = "silence_frame"
            return self._operation("silence_release_poll", "GET", f"/api/silence-status?board_id={bid}", None, released)
        if self.state == "silence_frame":
            def shown(body):
                self._frame(body, "PERF HELD")
                self.state = "silence_disable"
            return self._operation("silence_held_frame", "GET", f"/api/v1/boards/{bid}", None, shown)
        if self.state == "silence_disable":
            payload = {**self.quiet, "enabled": False, "show_queued_on_exit": False}
            def disabled(body):
                self._check(body.get("board_id") == bid and body.get("config", {}).get("enabled") is False)
                self.state = "manual_restore"
            return self._operation("silence_disable", "PUT", "/api/settings/silence-schedule", payload, disabled)
        if self.state == "manual_restore":
            def pinned(body):
                self._check(body.get("board_id") == bid and body.get("page_id") == page_id and body.get("sent") is True and not body.get("error"))
                self.state = "final_frame"
            return self._operation("warmup_manual_restore", "PUT", f"/api/v1/boards/{bid}/active-page", {"page_id": page_id}, pinned)
        if self.state == "final_frame":
            def final(body):
                self._frame(body, marker, baseline=True)
                self.state = "complete"
            return self._operation("warmup_restored_frame", "GET", f"/api/v1/boards/{bid}", None, final)
        raise ProtocolError("Unknown warmup subscenario state")

    def verification(self):
        return {"complete": self.state == "complete" and not self.failed, "state": self.state,
                "completed_elapsed_s": self.completed_elapsed, "requires_operator_recovery": self.state not in {"override_start", "complete"},
                "events": list(self.events)}


def run_soak(client, manifest, out_dir, anchor, collector_ready, *, phase_seconds=(600, 6000, 600),
             clock=None, sleep=None, operation_factory=None, scenarios=None):
    synthetic_clock = clock is not None
    clock, sleep = clock or time.monotonic, sleep or time.sleep
    if len(phase_seconds) != 3 or any(not isinstance(n, (int, float)) or n <= 0 or not math.isfinite(n) for n in phase_seconds):
        raise ProtocolError("Declare three positive finite warmup/activity/drain durations")
    validate_collector_anchor(anchor, boot_id=collector_ready.get("boot_id"),
                              pid_namespace=collector_ready.get("pid_namespace"), api_cmdline=collector_ready.get("api_cmdline", ""))
    if (collector_ready.get("run_id") != anchor["run_id"] or collector_ready.get("start_monotonic") != anchor["start_monotonic"]
            or not isinstance(collector_ready.get("api_pid"), int) or not isinstance(collector_ready.get("api_start_time_ticks"), int)):
        raise ProtocolError("Collector-ready identity does not match the measurement anchor")
    if not synthetic_clock:
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        if boot_id != anchor["boot_id"]:
            raise ProtocolError("Workload must run in the same Linux clock domain as the hub collector")
    if clock() > anchor["start_monotonic"]:
        raise ProtocolError("Measurement anchor elapsed before preflight")
    session = client.session_info(min_valid_seconds=sum(phase_seconds) + 600)
    verify_manifest(client, manifest)
    if clock() > anchor["start_monotonic"]:
        raise ProtocolError("Measurement anchor elapsed during preflight")
    out_dir = Path(out_dir)
    writer = JsonlWriter(out_dir / "soak.jsonl", anchor["run_id"], secrets=client.secrets)
    start = anchor["start_monotonic"]
    diagnostic = tuple(phase_seconds) != (600, 6000, 600) or synthetic_clock
    writer.write("metadata", planned_phase_seconds=list(phase_seconds), source_commit=SOURCE_COMMIT,
                 seed_id=manifest["seed_id"], image_manifest=manifest.get("image_manifest"),
                 boot_id=anchor["boot_id"], collector_pid_namespace=anchor["pid_namespace"],
                 collector_interval_seconds=5, synthetic_clock=synthetic_clock, diagnostic=diagnostic,
                 dispatch_grace_seconds=0.05, run_context=client.run_context,
                 session=session, measurement_start_monotonic=start, monotonic_elapsed_s=0)
    geometries = ("flagship", "note", "array", "panel")
    factory = operation_factory or (lambda cycle: soak_operations(manifest, geometries[cycle % 4], (cycle // 4) % 3, cycle))
    controls = scenarios
    if controls is None and operation_factory is None:
        controls = WarmupScenarios(manifest, elapsed_clock=lambda: clock() - start)
    status_operation = next(op for op in api_operations(manifest) if op.name == "status")

    def warmup_slot(operation, index, deadline):
        if controls is not None:
            verification = controls.verification()
            if not verification.get("complete"):
                if clock() - start >= 300:
                    raise ProtocolError("Warmup controls not complete by300s; activity must not start")
                selected = controls.next_operation(clock() - start)
                if selected is None:
                    raise ProtocolError("Warmup control state is incomplete without a next operation")
                return selected
        # Settling keeps the verified baseline frame rather than continually
        # replacing it with save/send work before the activity phase.
        return status_operation if operation.name in {"save", "send"} else operation
    results = {}
    try:
        remaining = start - clock()
        if remaining > 0:
            sleep(remaining)
        phase_offset = 0
        for phase, duration, cadence in zip(("warmup", "activity", "drain"), phase_seconds, (6, 1, 5)):
            phase_start = start + phase_offset
            wait = phase_start - clock()
            if wait > 0:
                sleep(wait)
            if phase == "drain":
                status = next(op for op in api_operations(manifest) if op.name == "status")
                operations = [status] * 10
            elif phase == "warmup" and operation_factory is None:
                operations = lambda cycle: factory(cycle + 600)
            else:
                operations = factory
            result = run_phase(client, operations, writer, phase=phase, start=phase_start, duration=duration,
                               slot_seconds=cadence, clock=clock, sleep=sleep, measurement_start=start,
                               slot_transform=warmup_slot if phase == "warmup" else None)
            results[phase] = result
            phase_offset += duration
            if result["aborted"]:
                break
            if phase == "warmup" and controls is not None:
                verified = controls.verification()
                if (not verified.get("complete") or verified.get("completed_elapsed_s", float("inf")) > 300
                        or (tuple(phase_seconds) == (600, 6000, 600) and phase_start + duration - start - verified["completed_elapsed_s"] < 300)):
                    raise ProtocolError("Warmup controls/restoration and300-second settling contract incomplete")
                writer.write("warmup_controls", verification=verified, monotonic_elapsed_s=clock() - start)
        report = {"complete": False, "requires_resource_merge": True, "diagnostic": diagnostic,
                  "measured_seconds": clock() - start, "activity_requests": results.get("activity", {}).get("attempted", 0),
                  "whole_window_requests": sum(result["attempted"] for result in results.values()),
                  "phases": results, "subscenarios_verified": bool(controls and controls.verification().get("complete")),
                  "warmup_controls": controls.verification() if controls is not None else None}
        writer.write("driver_summary", monotonic_elapsed_s=clock() - start, **report)
        (out_dir / "driver-summary.json").write_text(json.dumps(report, indent=2) + "\n")
        return report
    except Exception as exc:
        writer.write("interrupted", error=f"Soak driver stopped: {type(exc).__name__}", monotonic_elapsed_s=clock() - start)
        raise
    finally:
        writer.close()


def run_phase(client, operations, writer, *, phase, start, duration, slot_seconds, clock, sleep, measurement_start,
              dispatch_grace_seconds=0.05, slot_transform=None):
    if not callable(operations) and len(operations) != 10:
        raise ProtocolError("A phase cycle needs exactly ten declared slots")
    factory = operations if callable(operations) else lambda cycle: operations
    cycles = {}
    pacer = SlotPacer(start, duration, slot_seconds)
    if not math.isfinite(dispatch_grace_seconds) or not 0 <= dispatch_grace_seconds < slot_seconds:
        raise ProtocolError("Dispatch grace must be finite/nonnegative and shorter than an arrival slot")
    writer.write("phase", phase=phase, event="start", scheduled_elapsed_s=start - measurement_start,
                 monotonic_elapsed_s=clock() - measurement_start)
    attempted, missed, successful, aborted = 0, 0, 0, False
    initial = True
    while True:
        now = clock()
        # Reserve the initial immutable deadline before dispatch overhead, as
        # later deadlines are reserved before sleep. This grace never applies
        # to an unreserved deadline passed by preceding request work.
        arrival = pacer.next_slot(start if initial and now <= start + dispatch_grace_seconds else now)
        initial = False
        for index in arrival["missed"]:
            missed += 1
            writer.write("missed_slot", phase=phase, slot=index, cycle=index // 10, cycle_slot=index % 10,
                         reason="Unreserved deadline passed",
                         scheduled_elapsed_s=start + index * slot_seconds - measurement_start,
                         monotonic_elapsed_s=clock() - measurement_start)
        if arrival["slot"] is None:
            break
        wait = arrival["deadline"] - clock()
        if wait > 0:
            sleep(wait)
        index = arrival["slot"]
        lateness = clock() - arrival["deadline"]
        if lateness > dispatch_grace_seconds + 1e-9:
            missed += 1
            writer.write("missed_slot", phase=phase, slot=index, cycle=index // 10, cycle_slot=index % 10,
                         reason="Reserved wake exceeded dispatch grace", dispatch_lateness_ms=lateness * 1000,
                         scheduled_elapsed_s=arrival["deadline"] - measurement_start,
                         monotonic_elapsed_s=clock() - measurement_start)
            continue
        cycle = index // 10
        if cycle not in cycles:
            cycles[cycle] = factory(cycle)
            if len(cycles[cycle]) != 10:
                raise ProtocolError("A dynamic phase cycle needs exactly ten declared slots")
        operation = cycles[cycle][index % 10]
        if slot_transform is not None:
            operation = slot_transform(operation, index, arrival["deadline"])
        payload = operation.payload() if callable(operation.payload) else operation.payload
        started = clock()
        if started - arrival["deadline"] > dispatch_grace_seconds + 1e-9:
            missed += 1
            writer.write("missed_slot", phase=phase, slot=index, cycle=cycle, cycle_slot=index % 10,
                         reason="Preparation exceeded dispatch grace", dispatch_lateness_ms=(started - arrival["deadline"]) * 1000,
                         scheduled_elapsed_s=arrival["deadline"] - measurement_start,
                         monotonic_elapsed_s=started - measurement_start)
            continue
        result = client.request(operation.method, operation.path, payload)
        semantic_success, error = False, result.error
        try:
            if operation.validate(require_ok(result, status=operation.expected_status)) is False:
                raise ProtocolError("Semantic validator refused result")
            semantic_success = True
        except (ProtocolError, ValueError, KeyError, TypeError):
            error = error or "HTTP or response-semantic assertion failed"
        attempted += 1
        successful += int(semantic_success)
        writer.write("request", phase=phase, operation=operation.name, geometry=operation.geometry, cache=operation.cache,
                     auth="browser-cookie", cycle=index // 10, cycle_slot=index % 10, batch=1,
                     scheduled_elapsed_s=arrival["deadline"] - measurement_start, started_elapsed_s=started - measurement_start,
                     dispatch_lateness_ms=max(0, started - arrival["deadline"]) * 1000, dispatch_grace_seconds=dispatch_grace_seconds,
                     monotonic_elapsed_s=clock() - measurement_start, elapsed_ms=result.elapsed_ms,
                     http_status=result.status, bytes=result.body_bytes, semantic_success=semantic_success,
                     error=error, timed_out=result.timed_out, timeout_seconds=client.timeout,
                     request={"method": operation.method, "path": operation.path, "body": payload},
                     response=client.safe_result(result))
        if result.status == 401 or (not semantic_success and operation.abort_on_failure):
            aborted = True
            writer.write("interrupted", phase=phase, reason="Authentication or critical control failed; explicit operator recovery required",
                         monotonic_elapsed_s=clock() - measurement_start)
            break
    if not aborted:
        remaining = start + duration - clock()
        if remaining > 0:
            sleep(remaining)
    ended = clock()
    writer.write("phase", phase=phase, event="end", scheduled_elapsed_s=start + duration - measurement_start,
                 monotonic_elapsed_s=ended - measurement_start)
    return {"attempted": attempted, "missed": missed, "successful": successful, "aborted": aborted,
            "actual_seconds": ended - start}


def soak_operations(manifest, geometry, ring_index, cycle):
    if geometry not in manifest["boards"] or ring_index not in (0, 1, 2) or cycle < 0:
        raise ProtocolError("Invalid geometry/save-send ring position")
    board = manifest["boards"][geometry]
    ring_page = board["page_ids"][ring_index + 1]
    local_boards = {key: {**value, "page_ids": list(value["page_ids"])} for key, value in manifest["boards"].items()}
    # api_operations saves index1. Keep the original manifest's board IDs/order unchanged.
    local_boards[geometry]["page_ids"][1] = ring_page
    definitions = api_operations({**manifest, "boards": local_boards})

    def operation(name, key=geometry):
        return next(op for op in definitions if op.name == name and op.geometry == key)

    save = operation("save")
    original_prepare = save.payload

    def changed_save():
        payload = original_prepare()
        # A cycle-specific marker stays changed even if the caller rebuilds the
        # operation objects before the ring's next120-second revisit.
        payload["template"][0] = f"PERF {cycle:08}"
        return payload

    save.payload = changed_save
    send = operation("send")
    send.payload = {"page_id": ring_page}
    send.cleanup = None
    preview = operation("preview_batch_prefilled")
    preview.cache = "steady-preview-mixed"
    listed = ("pages", "collections", "schedules_all")[cycle % 3]
    history = ApiOperation("history", geometry, "n/a", "GET", f"/api/pages/{ring_page}/revisions", None,
                           lambda body: None if isinstance(body.get("revisions"), list) else (_ for _ in ()).throw(
                               ProtocolError("Revision history list missing")))
    return [operation("boards", "all"), operation("board_detail"), operation(listed, "all"), preview,
            operation("render_diagnostics"), operation("collection_dry_run"), operation("schedule_at_manual"), save, send, history]


class SlotPacer:
    def __init__(self, start, duration, slot_seconds=1.0):
        if not all(math.isfinite(n) for n in (start, duration, slot_seconds)) or duration <= 0 or slot_seconds <= 0:
            raise ProtocolError("Pacing requires finite start/positive duration/interval")
        self.start = start
        self.slot_seconds = slot_seconds
        self.count = math.ceil(duration / slot_seconds)
        self.index = 0

    def next_slot(self, now):
        if not math.isfinite(now) or now < self.start:
            raise ProtocolError("Monotonic clock is invalid or precedes phase start")
        next_due = max(self.index, math.ceil((now - self.start) / self.slot_seconds))
        missed = list(range(self.index, min(self.count, next_due)))
        if next_due >= self.count:
            self.index = self.count
            return {"slot": None, "deadline": None, "missed": missed}
        self.index = next_due + 1
        return {"slot": next_due, "deadline": self.start + next_due * self.slot_seconds, "missed": missed}
