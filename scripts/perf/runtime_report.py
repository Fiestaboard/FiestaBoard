"""Offline standard-library reducer for retained runtime JSONL observations."""

from collections import defaultdict
import json
import math
import argparse
from pathlib import Path

from runtime_common import AMD64_MANIFEST, SOURCE_COMMIT, summarize_requests


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline reduction; incomplete/mixed/corrupt evidence exits nonzero")
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    records, errors = [], []
    for path in args.inputs:
        try:
            parsed = read_jsonl(path)
            records.extend(parsed["records"])
            errors.extend({"path": str(path), **error} for error in parsed["errors"])
        except OSError:
            errors.append({"path": str(path), "error": "Input unavailable"})
    report = report_records(records, errors=errors)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as output:
        output.write(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return 0 if report["complete"] else 2


def read_jsonl(path):
    records, errors = [], []
    with Path(path).open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("Record is not an object")
                records.append(record)
            except ValueError:
                errors.append({"line": line_number, "error": "Malformed/partial JSON object"})
    return {"records": records, "errors": errors}


def report_records(records, *, errors=()):
    phases = {}
    actual_phases = {}
    duplicate_phase = False
    resources, requests, gaps = [], [], []
    strata = defaultdict(list)
    identities, restarts = {}, []
    cycles = defaultdict(set)
    resource_blocks = {}
    for record in records:
        kind = record.get("record_type")
        if kind == "phase":
            key = record.get("phase"), record.get("event")
            duplicate_phase = duplicate_phase or key in phases
            phases[key] = record.get("scheduled_elapsed_s", record.get("monotonic_elapsed_s"))
            actual_phases[key] = record.get("monotonic_elapsed_s")
        elif kind == "request":
            requests.append(record)
            key = tuple(record.get(field) for field in ("run_id", "batch", "operation", "geometry", "cache", "auth", "phase"))
            strata[key].append(record)
            if (record.get("phase") == "activity" and record.get("semantic_success") is True
                    and record.get("activity_kind", "ordinary") == "ordinary"):
                cycles[record.get("cycle")].add(record.get("cycle_slot"))
        elif kind == "resource":
            resources.append(record)
            for process in record.get("processes", []):
                role, pid, start = process.get("role"), process.get("pid"), process.get("start_time_ticks")
                previous = identities.get(role)
                if previous is not None and previous != (pid, start):
                    restarts.append({"role": role, "pid": pid, "from_start": previous[1], "to_start": start})
                identities[role] = pid, start
                rss = process.get("rss_bytes")
                if isinstance(rss, (int, float)) and math.isfinite(rss):
                    identity = role, pid, start
                    block = resource_blocks.setdefault(identity, {"role": role, "pid": pid, "start_time_ticks": start,
                        "first_rss_bytes": rss, "last_rss_bytes": rss, "max_rss_bytes": rss, "samples": 0})
                    block["last_rss_bytes"] = rss
                    block["max_rss_bytes"] = max(block["max_rss_bytes"], rss)
                    block["samples"] += 1
        elif kind in {"gap", "missed_slot", "interrupted", "error"}:
            gaps.append(record)
    expected = {("warmup", "start"): 0, ("warmup", "end"): 600, ("activity", "start"): 600,
                ("activity", "end"): 6600, ("drain", "start"): 6600, ("drain", "end"): 7200}
    window_complete = not duplicate_phase and all(
        isinstance(phases.get(key), (int, float)) and phases[key] == expected_time
        and isinstance(actual_phases.get(key), (int, float)) and expected_time <= actual_phases[key] <= expected_time + 0.05 + 1e-9
        for key, expected_time in expected.items()
    )
    if window_complete:
        window_complete = all(phases[(phase, "end")] - phases[(phase, "start")] >= duration
                              for phase, duration in (("warmup", 600), ("activity", 6000), ("drain", 600)))
    summaries = []
    fields = ("run_id", "batch", "operation", "geometry", "cache", "auth", "phase")
    for key, observations in sorted(strata.items(), key=lambda item: repr(item[0])):
        summaries.append({**dict(zip(fields, key)), **summarize_requests(observations)})
    activity = [r for r in requests if r.get("phase") == "activity"]
    ordinary_activity = [r for r in activity if r.get("activity_kind", "ordinary") == "ordinary"]
    activity_transitions = [r for r in activity if r.get("activity_kind") == "transition"]
    drain_transitions = [r for r in requests if r.get("phase") == "drain" and r.get("activity_kind") == "transition"]
    complete_cycles = sum(slots == set(range(10)) for cycle, slots in cycles.items() if cycle is not None)
    run_ids = {r.get("run_id") for r in records}
    one_run = len(run_ids) == 1 and all(isinstance(value, str) and value for value in run_ids)
    metadata = [r for r in records if r.get("record_type") == "metadata"]
    declared_window = len(metadata) == 1 and metadata[0].get("planned_phase_seconds") == [600, 6000, 600]
    if declared_window:
        declared_window = (metadata[0].get("source_commit") == SOURCE_COMMIT
                           and metadata[0].get("synthetic_clock") is False and metadata[0].get("diagnostic") is False
                           and metadata[0].get("dispatch_grace_seconds") == 0.05
                           and bool(metadata[0].get("boot_id")) and bool(metadata[0].get("collector_pid_namespace")))

    def finite(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

    # Request completion timestamps alone cannot establish deadline arrivals or
    # one-in-flight behavior; require all three recorded clock points.
    requests_valid = len(activity) == 6000 and all(summary["valid"] for summary in summaries)
    previous_end = 600.0
    for request in activity:
        cycle, slot = request.get("cycle"), request.get("cycle_slot")
        deadline, started, ended = (request.get(key) for key in ("scheduled_elapsed_s", "started_elapsed_s", "monotonic_elapsed_s"))
        valid_indices = isinstance(cycle, int) and 0 <= cycle < 600 and isinstance(slot, int) and 0 <= slot < 10
        valid_times = all(finite(value) for value in (deadline, started, ended))
        if not valid_indices or not valid_times:
            requests_valid = False
            continue
        if (deadline != 600 + cycle * 10 + slot or not deadline <= started <= deadline + 0.05 + 1e-9
                or not started <= ended <= 6600 or started < previous_end):
            requests_valid = False
        previous_end = ended
    transitions_valid = len(activity_transitions) == 12 and len(drain_transitions) == 12
    for transitions, base in ((activity_transitions, 600), (drain_transitions, 6600)):
        targets = []
        for index, request in enumerate(transitions):
            if (request.get("transition_index") != index or request.get("scheduled_elapsed_s") != base + index
                    or not request.get("transition_target") or request.get("semantic_success") is not True
                    or request.get("http_status") != 200 or request.get("timed_out")):
                transitions_valid = False
            targets.append(request.get("transition_target"))
        if len(set(targets)) != 12:
            transitions_valid = False
    if {r.get("transition_target") for r in activity_transitions} != {r.get("transition_target") for r in drain_transitions}:
        transitions_valid = False
    for request in ordinary_activity:
        if request.get("scheduled_elapsed_s", 0) < 612:
            transitions_valid = False
    resource_times = [r.get("monotonic_elapsed_s") for r in resources]
    resources_valid = bool(resources) and all(finite(value) for value in resource_times)
    if resources_valid:
        resources_valid = (resource_times == sorted(resource_times) and resource_times[0] <= 5 and resource_times[-1] >= 7195
                           and all(0 < later - earlier <= 7.5 for earlier, later in zip(resource_times, resource_times[1:])))
    expected_roles = None
    for resource in resources:
        if (len(metadata) != 1 or resource.get("boot_id") != metadata[0].get("boot_id")
                or resource.get("pid_namespace") != metadata[0].get("collector_pid_namespace")):
            resources_valid = False
        processes = resource.get("processes", [])
        roles = [p.get("role") for p in processes]
        if not processes or "api" not in roles or len(set(roles)) != len(roles):
            resources_valid = False
        if expected_roles is None:
            expected_roles = set(roles)
        elif set(roles) != expected_roles:
            resources_valid = False
        for process in processes:
            if (not isinstance(process.get("pid"), int) or process["pid"] <= 0
                    or not isinstance(process.get("start_time_ticks"), int) or process["start_time_ticks"] <= 0
                    or not finite(process.get("rss_bytes")) or process["rss_bytes"] < 0):
                resources_valid = False
    driver_summaries = [r for r in records if r.get("record_type") == "driver_summary"]
    protocol_valid = len(driver_summaries) == 1
    if protocol_valid:
        driver = driver_summaries[0]
        protocol_valid = (driver.get("subscenarios_verified") is True and driver.get("selection_verified") is True
                          and driver.get("final_state_verified") is True
                          and finite(driver.get("warmup_controls_completed_elapsed_s"))
                          and driver["warmup_controls_completed_elapsed_s"] <= 300
                          and finite(driver.get("steady_settling_seconds")) and driver["steady_settling_seconds"] >= 300)
    complete = (window_complete and one_run and declared_window and not errors and not gaps and not restarts
                and requests_valid and transitions_valid and protocol_valid and complete_cycles == 598 and resources_valid)
    active_seconds = phases.get(("activity", "end"), 0) - phases.get(("activity", "start"), 0)
    active_minutes = active_seconds / 60 if active_seconds > 0 else None
    blocks = [{**block, "delta_rss_bytes": block["last_rss_bytes"] - block["first_rss_bytes"]} for block in resource_blocks.values()]
    return {"window_complete": window_complete, "complete": complete, "process_restarts": restarts, "strata": summaries,
            "activity_requests": len(activity), "ordinary_activity_requests": len(ordinary_activity),
            "activity_transition_requests": len(activity_transitions), "drain_transition_requests": len(drain_transitions),
            "completed_cycles": complete_cycles, "realized_activity_factor": complete_cycles / active_minutes if active_minutes else None,
            "ordinary_request_factor": len(ordinary_activity) / (active_minutes * 10) if active_minutes else None,
            "per_slot_activity_factor": {str(slot): sum(r.get("cycle_slot") == slot for r in ordinary_activity) / active_minutes
                                         if active_minutes else None for slot in range(10)},
            "actual_rotation_event_count": None, "rotation_observability": "Configured cadence is not observed worker events; periodic board samples may alias a complete rotation",
            "resource_blocks": blocks, "transitions_valid": transitions_valid, "protocol_valid": protocol_valid,
            "resource_samples": len(resources), "gaps": len(gaps), "parse_errors": list(errors),
            "one_run": one_run, "requests_valid": requests_valid, "resources_valid": resources_valid,
            "actual_phase_observation_intervals": {phase: actual_phases[(phase, "end")] - actual_phases[(phase, "start")]
                for phase in ("warmup", "activity", "drain") if (phase, "start") in actual_phases and (phase, "end") in actual_phases},
            "python_heap": {"available": False}, "queues": {"available": False}}


if __name__ == "__main__":
    raise SystemExit(main())
