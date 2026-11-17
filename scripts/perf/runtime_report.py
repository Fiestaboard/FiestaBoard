"""Offline standard-library reducer for retained runtime JSONL observations."""

from collections import defaultdict
import json
import math
from pathlib import Path

from runtime_common import AMD64_MANIFEST, SOURCE_COMMIT, summarize_requests


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
    duplicate_phase = False
    resources, requests, gaps = [], [], []
    strata = defaultdict(list)
    identities, restarts = {}, []
    cycles = defaultdict(set)
    for record in records:
        kind = record.get("record_type")
        if kind == "phase":
            key = record.get("phase"), record.get("event")
            duplicate_phase = duplicate_phase or key in phases
            phases[key] = record.get("monotonic_elapsed_s")
        elif kind == "request":
            requests.append(record)
            key = tuple(record.get(field) for field in ("run_id", "batch", "operation", "geometry", "cache", "auth", "phase"))
            strata[key].append(record)
            if record.get("phase") == "activity" and record.get("semantic_success") is True:
                cycles[record.get("cycle")].add(record.get("cycle_slot"))
        elif kind == "resource":
            resources.append(record)
            for process in record.get("processes", []):
                role, pid, start = process.get("role"), process.get("pid"), process.get("start_time_ticks")
                previous = identities.get(role)
                if previous is not None and previous != (pid, start):
                    restarts.append({"role": role, "pid": pid, "from_start": previous[1], "to_start": start})
                identities[role] = pid, start
        elif kind in {"gap", "missed_slot", "interrupted", "error"}:
            gaps.append(record)
    expected = {("warmup", "start"): 0, ("warmup", "end"): 600, ("activity", "start"): 600,
                ("activity", "end"): 6600, ("drain", "start"): 6600, ("drain", "end"): 7200}
    window_complete = not duplicate_phase and all(
        isinstance(phases.get(key), (int, float)) and expected_time <= phases[key] <= expected_time + 2
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
    complete_cycles = sum(slots == set(range(10)) for cycle, slots in cycles.items() if cycle is not None)
    run_ids = {r.get("run_id") for r in records}
    one_run = len(run_ids) == 1 and all(isinstance(value, str) and value for value in run_ids)
    metadata = [r for r in records if r.get("record_type") == "metadata"]
    declared_window = len(metadata) == 1 and metadata[0].get("planned_phase_seconds") == [600, 6000, 600]
    if declared_window:
        declared_window = metadata[0].get("source_commit") == SOURCE_COMMIT

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
        if (deadline != 600 + cycle * 10 + slot or not deadline <= started < deadline + 1
                or not started <= ended <= 6600 or started < previous_end):
            requests_valid = False
        previous_end = ended
    resource_times = [r.get("monotonic_elapsed_s") for r in resources]
    resources_valid = bool(resources) and all(finite(value) for value in resource_times)
    if resources_valid:
        resources_valid = (resource_times == sorted(resource_times) and resource_times[0] <= 5 and resource_times[-1] >= 7195
                           and all(0 < later - earlier <= 7.5 for earlier, later in zip(resource_times, resource_times[1:])))
    expected_roles = None
    for resource in resources:
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
    complete = (window_complete and one_run and declared_window and not errors and not gaps and not restarts
                and requests_valid and complete_cycles == 600 and resources_valid)
    return {"window_complete": window_complete, "complete": complete, "process_restarts": restarts, "strata": summaries,
            "activity_requests": len(activity), "completed_cycles": complete_cycles, "realized_activity_factor": complete_cycles / 100,
            "resource_samples": len(resources), "gaps": len(gaps), "parse_errors": list(errors),
            "one_run": one_run, "requests_valid": requests_valid, "resources_valid": resources_valid,
            "python_heap": {"available": False}, "queues": {"available": False}}
