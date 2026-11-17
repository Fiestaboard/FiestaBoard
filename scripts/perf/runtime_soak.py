"""Monotonic, bounded-arrival soak driver; execution must be serialized by the operator."""

import math
import time
import json
from pathlib import Path

from runtime_common import JsonlWriter, ProtocolError, SOURCE_COMMIT
from runtime_common import require_ok
from runtime_api import ApiOperation, api_operations
from runtime_collect import validate_collector_anchor
from runtime_seed import verify_manifest


def run_soak(client, manifest, out_dir, anchor, collector_ready, *, phase_seconds=(600, 6000, 600),
             clock=None, sleep=None, operation_factory=None):
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
    results = {}
    try:
        remaining = start - clock()
        if remaining > 0:
            sleep(remaining)
        for phase, duration, cadence in zip(("warmup", "activity", "drain"), phase_seconds, (6, 1, 5)):
            phase_start = clock()
            if phase == "drain":
                status = next(op for op in api_operations(manifest) if op.name == "status")
                operations = [status] * 10
            elif phase == "warmup" and operation_factory is None:
                operations = lambda cycle: factory(cycle + 600)
            else:
                operations = factory
            result = run_phase(client, operations, writer, phase=phase, start=phase_start, duration=duration,
                               slot_seconds=cadence, clock=clock, sleep=sleep, measurement_start=start)
            results[phase] = result
            if result["aborted"]:
                break
        report = {"complete": False, "requires_resource_merge": True, "diagnostic": diagnostic,
                  "measured_seconds": clock() - start, "activity_requests": results.get("activity", {}).get("attempted", 0),
                  "whole_window_requests": sum(result["attempted"] for result in results.values()),
                  "phases": results, "subscenarios_verified": False}
        writer.write("driver_summary", monotonic_elapsed_s=clock() - start, **report)
        (out_dir / "driver-summary.json").write_text(json.dumps(report, indent=2) + "\n")
        return report
    except Exception as exc:
        writer.write("interrupted", error=f"Soak driver stopped: {type(exc).__name__}", monotonic_elapsed_s=clock() - start)
        raise
    finally:
        writer.close()


def run_phase(client, operations, writer, *, phase, start, duration, slot_seconds, clock, sleep, measurement_start,
              dispatch_grace_seconds=0.05):
    if not callable(operations) and len(operations) != 10:
        raise ProtocolError("A phase cycle needs exactly ten declared slots")
    factory = operations if callable(operations) else lambda cycle: operations
    cycles = {}
    pacer = SlotPacer(start, duration, slot_seconds)
    if not math.isfinite(dispatch_grace_seconds) or not 0 <= dispatch_grace_seconds < slot_seconds:
        raise ProtocolError("Dispatch grace must be finite/nonnegative and shorter than an arrival slot")
    writer.write("phase", phase=phase, event="start", monotonic_elapsed_s=start - measurement_start)
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
        payload = operation.payload() if callable(operation.payload) else operation.payload
        started = clock()
        result = client.request(operation.method, operation.path, payload)
        semantic_success, error = False, result.error
        try:
            if operation.validate(require_ok(result)) is False:
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
        if result.status == 401:
            aborted = True
            writer.write("interrupted", phase=phase, reason="Authentication failed; no retry/relogin/cleanup",
                         monotonic_elapsed_s=clock() - measurement_start)
            break
    if not aborted:
        remaining = start + duration - clock()
        if remaining > 0:
            sleep(remaining)
    ended = clock()
    writer.write("phase", phase=phase, event="end", monotonic_elapsed_s=ended - measurement_start)
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
