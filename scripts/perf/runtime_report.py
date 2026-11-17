"""Offline standard-library reducer for retained runtime JSONL observations."""

from collections import defaultdict
import json
from pathlib import Path

from runtime_common import summarize_requests


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


def report_records(records):
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
    complete = (window_complete and not gaps and not restarts and len(activity) == 6000 and complete_cycles == 600
                and all(r.get("semantic_success") is True for r in activity) and bool(resources))
    return {"window_complete": window_complete, "complete": complete, "process_restarts": restarts, "strata": summaries,
            "activity_requests": len(activity), "completed_cycles": complete_cycles, "realized_activity_factor": complete_cycles / 100,
            "resource_samples": len(resources), "gaps": len(gaps),
            "python_heap": {"available": False}, "queues": {"available": False}}
