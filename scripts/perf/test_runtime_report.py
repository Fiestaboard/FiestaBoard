"""Offline reducer tests: retain partial evidence and reject false completeness."""

import json
import tempfile
import unittest
from pathlib import Path

from runtime_report import main as report_main
from runtime_report import read_jsonl, report_records


def phase_records():
    return [
        {"record_type": "phase", "phase": phase, "event": event, "monotonic_elapsed_s": elapsed}
        for phase, event, elapsed in [
            ("warmup", "start", 0),
            ("warmup", "end", 600),
            ("activity", "start", 600),
            ("activity", "end", 6600),
            ("drain", "start", 6600),
            ("drain", "end", 7200),
        ]
    ]


def continuous_records():
    records = [
        {
            "record_type": "metadata",
            "run_id": "run-1",
            "source_commit": "83236253aa8103db856b7efa456e088b9c9ec548",
            "planned_phase_seconds": [600, 6000, 600],
            "collector_interval_seconds": 5,
            "boot_id": "boot-a",
            "collector_pid_namespace": "pid:[100]",
            "synthetic_clock": False,
            "diagnostic": False,
        }
    ]
    records[0]["dispatch_grace_seconds"] = 0.05
    records.extend({**record, "run_id": "run-1"} for record in phase_records())
    for slot in range(6000):
        records.append(
            {
                "record_type": "request",
                "run_id": "run-1",
                "phase": "activity",
                "cycle": slot // 10,
                "cycle_slot": slot % 10,
                "operation": f"slot{slot % 10}",
                "geometry": "note",
                "cache": "mixed",
                "auth": "browser-cookie",
                "batch": 1,
                "elapsed_ms": 100,
                "http_status": 200,
                "semantic_success": True,
                "timed_out": False,
                "scheduled_elapsed_s": 600 + slot,
                "started_elapsed_s": 600 + slot,
                "monotonic_elapsed_s": 600 + slot + 0.1,
                "activity_kind": "transition" if slot < 12 else "ordinary",
                "transition_index": slot if slot < 12 else None,
                "transition_target": f"collection-{slot}" if slot < 12 else None,
            }
        )
    records.extend(
        {
            "record_type": "request",
            "run_id": "run-1",
            "phase": "drain",
            "cycle": slot // 10,
            "cycle_slot": slot % 10,
            "operation": "cadence_restore",
            "geometry": "all",
            "cache": "control",
            "auth": "browser-cookie",
            "batch": 1,
            "elapsed_ms": 100,
            "http_status": 200,
            "semantic_success": True,
            "timed_out": False,
            "scheduled_elapsed_s": 6600 + slot,
            "started_elapsed_s": 6600 + slot,
            "monotonic_elapsed_s": 6600 + slot + 0.1,
            "activity_kind": "transition",
            "transition_index": slot,
            "transition_target": f"collection-{slot}",
        }
        for slot in range(12)
    )
    records.extend(
        {
            "record_type": "resource",
            "run_id": "run-1",
            "monotonic_elapsed_s": second,
            "boot_id": "boot-a",
            "pid_namespace": "pid:[100]",
            "processes": [{"role": "api", "pid": 42, "start_time_ticks": 100, "rss_bytes": 100000}],
        }
        for second in range(0, 7201, 5)
    )
    records.append(
        {
            "record_type": "driver_summary",
            "run_id": "run-1",
            "monotonic_elapsed_s": 7200.2,
            "subscenarios_verified": True,
            "selection_verified": True,
            "final_state_verified": True,
            "warmup_controls_completed_elapsed_s": 240,
            "steady_settling_seconds": 360,
        }
    )
    return records


class RuntimeReportTests(unittest.TestCase):
    def test_phase_window_requires_actual7200_seconds_and_complete_tail(self):
        # A short diagnostic or missing drain tail must not appear as a completed two-hour window.
        complete = report_records(phase_records())
        self.assertIs(complete.get("window_complete"), True)
        missing = report_records(phase_records()[:-1])
        self.assertIs(missing.get("window_complete"), False)
        altered = phase_records()
        altered[1]["monotonic_elapsed_s"] = 590
        self.assertIs(report_records(altered).get("window_complete"), False)

    def test_pid_reuse_is_a_restart_even_when_rss_is_flat(self):
        # PID-only joining can splice a freshly restarted API into an apparently stable curve.
        records = [
            {
                "record_type": "resource",
                "monotonic_elapsed_s": t,
                "processes": [{"role": "api", "pid": 42, "start_time_ticks": start, "rss_bytes": 100000}],
            }
            for t, start in [(0, 100), (5, 100), (10, 200)]
        ]
        report = report_records(records)
        self.assertEqual(
            report.get("process_restarts"), [{"role": "api", "pid": 42, "from_start": 100, "to_start": 200}]
        )

    def test_partial_last_jsonl_keeps_prior_observations_and_error(self):
        # Dropping the whole file or silently ignoring a partial tail destroys interrupted-run evidence.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "partial.jsonl"
            path.write_text(json.dumps({"record_type": "request", "elapsed_ms": 12}) + '\n{"record_type":')
            parsed = read_jsonl(path)
        self.assertEqual(parsed["records"], [{"record_type": "request", "elapsed_ms": 12}])
        self.assertEqual(len(parsed["errors"]), 1)
        self.assertEqual(parsed["errors"][0]["line"], 2)

    def test_different_endpoint_geometry_cache_batches_are_not_pooled(self):
        # Pooling strata can conceal a regressed phone/panel/cold case inside fast requests.
        records = [
            {
                "record_type": "request",
                "phase": "sample",
                "operation": "render",
                "batch": batch,
                "geometry": geometry,
                "cache": cache,
                "auth": "browser-cookie",
                "elapsed_ms": elapsed,
                "http_status": status,
                "semantic_success": status == 200,
                "timed_out": False,
            }
            for batch, geometry, cache, elapsed, status in [
                (1, "note", "cached", 10, 200),
                (1, "panel", "cached", 500, 200),
                (2, "note", "cached", 20, 200),
                (1, "note", "forced", 0.1, 401),
            ]
        ]
        report = report_records(records)
        self.assertEqual(len(report.get("strata", [])), 4)
        panel = next(s for s in report["strata"] if s["geometry"] == "panel")
        self.assertEqual(panel["latency_ms"]["p95"], 500)
        failure = next(s for s in report["strata"] if s["cache"] == "forced")
        self.assertFalse(failure["valid"])
        self.assertIsNone(failure["latency_ms"]["p95"])

    def test_complete_requires_one_continuous_valid_run_with_covered_telemetry(self):
        # Structural counters plus one empty resource record cannot establish a two-hour continuous run.
        self.assertTrue(report_records(continuous_records())["complete"])
        for defect in (
            "empty_resource",
            "mixed_run",
            "outside_window",
            "http_failure",
            "timeout",
            "sparse_telemetry",
            "missing_identity",
        ):
            with self.subTest(defect=defect):
                records = continuous_records()
                request = next(r for r in records if r["record_type"] == "request")
                if defect == "empty_resource":
                    records = [r for r in records if r["record_type"] != "resource"]
                    records.append(
                        {"record_type": "resource", "run_id": "run-1", "monotonic_elapsed_s": 0, "processes": []}
                    )
                elif defect == "mixed_run":
                    request["run_id"] = "other-run"
                elif defect == "outside_window":
                    request["monotonic_elapsed_s"] = 599
                elif defect == "http_failure":
                    request["http_status"] = 401
                elif defect == "timeout":
                    request["timed_out"] = True
                elif defect == "sparse_telemetry":
                    records = [
                        r for r in records if r["record_type"] != "resource" or r["monotonic_elapsed_s"] in (0, 7200)
                    ]
                else:
                    next(r for r in records if r["record_type"] == "resource")["processes"][0]["start_time_ticks"] = (
                        None
                    )
                self.assertFalse(report_records(records)["complete"])

    def test_parse_errors_are_part_of_completion_verdict(self):
        # A caller may not discard read_jsonl.errors while accepting otherwise complete counters.
        self.assertFalse(report_records(continuous_records(), errors=[{"line": 100, "error": "partial"}])["complete"])

    def test_report_cli_retains_partial_input_and_exits_nonzero(self):
        # A successful CLI exit with incomplete evidence would be a false gate pass.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw.jsonl"
            raw.write_text('{"record_type":"request","http_status":401,"semantic_success":false}\n{"partial":')
            out = root / "report.json"
            code = report_main([str(raw), "--out", str(out)])
            self.assertEqual(code, 2)
            self.assertTrue(out.exists())
            report = json.loads(out.read_text())
        self.assertFalse(report["complete"])
        self.assertEqual(len(report["parse_errors"]), 1)
        self.assertEqual(report["strata"][0]["failed"], 1)

    def test_mixed_kernel_namespace_or_synthetic_clock_cannot_complete(self):
        # Matching run IDs do not make two Linux clock domains or a unit-clock replay one measured run.
        for defect in ("kernel", "namespace", "synthetic"):
            with self.subTest(defect=defect):
                records = continuous_records()
                if defect == "synthetic":
                    records[0]["synthetic_clock"] = True
                else:
                    resource = next(r for r in records if r["record_type"] == "resource")
                    resource["boot_id" if defect == "kernel" else "pid_namespace"] = "foreign"
                self.assertFalse(report_records(records)["complete"])

    def test_report_enforces_declared_dispatch_grace(self):
        # CorrectHTTP and phase counts do not make a60ms-late dispatch comply with a50ms declared load policy.
        records = continuous_records()
        request = next(r for r in records if r["record_type"] == "request")
        request["started_elapsed_s"] += 0.06
        request["monotonic_elapsed_s"] += 0.06
        self.assertFalse(report_records(records)["complete"])

    def test_controls_selection_and_final_recovery_are_full_protocol_gates(self):
        # A valid cyclewindow is narrower than expiry/quiet/selection/recovery proof.
        for defect in ("subscenario", "selection", "final_state", "late_controls", "missing_summary", "lost_restore"):
            with self.subTest(defect=defect):
                records = continuous_records()
                summary = next(r for r in records if r["record_type"] == "driver_summary")
                if defect in {"subscenario", "selection", "final_state"}:
                    summary[
                        {
                            "subscenario": "subscenarios_verified",
                            "selection": "selection_verified",
                            "final_state": "final_state_verified",
                        }[defect]
                    ] = False
                elif defect == "late_controls":
                    summary["warmup_controls_completed_elapsed_s"] = 301
                    summary["steady_settling_seconds"] = 299
                elif defect == "missing_summary":
                    records.remove(summary)
                else:
                    records.remove(
                        next(r for r in records if r.get("phase") == "drain" and r.get("transition_index") == 3)
                    )
                self.assertFalse(report_records(records)["complete"])

    def test_control_slots_are_not_counted_as_complete_normal_api_cycles(self):
        # Twelve required control slots leave5988 ordinary requests and598 complete ordinary cycles, not600.
        report = report_records(continuous_records())
        self.assertEqual(report["activity_requests"], 6000)
        self.assertEqual(report.get("ordinary_activity_requests"), 5988)
        self.assertEqual(report.get("activity_transition_requests"), 12)
        self.assertEqual(report["completed_cycles"], 598)
        self.assertAlmostEqual(report["realized_activity_factor"], 5.98)
        self.assertIsNone(report.get("actual_rotation_event_count"))

    def test_resource_growth_blocks_never_splice_restarted_process_identity(self):
        # A restart's lowRSS must not cancel a prior process's growth in one curve.
        records = [
            {
                "record_type": "resource",
                "run_id": "run-1",
                "monotonic_elapsed_s": index * 5,
                "processes": [{"role": "api", "pid": 42, "start_time_ticks": start, "rss_bytes": rss}],
            }
            for index, (start, rss) in enumerate([(100, 100000), (100, 120000), (200, 90000)])
        ]
        report = report_records(records)
        blocks = report.get("resource_blocks", [])
        self.assertEqual(len(blocks), 2)
        self.assertEqual([b["delta_rss_bytes"] for b in blocks], [20000, 0])
        self.assertEqual([b["start_time_ticks"] for b in blocks], [100, 200])

    def test_restore_timing_rejects_bursts_overlap_and_missing_actual_clocks(self):
        # Declared1s deadlines do not prove that the twelve restores actually respected those arrivals.
        for defect in ("burst", "overlap", "missing_clock"):
            with self.subTest(defect=defect):
                records = continuous_records()
                restores = [r for r in records if r.get("phase") == "drain" and r.get("activity_kind") == "transition"]
                if defect == "burst":
                    for record in restores:
                        record["started_elapsed_s"] = 6600
                        record["monotonic_elapsed_s"] = 6600.1
                elif defect == "overlap":
                    restores[0]["monotonic_elapsed_s"] = 6601.5
                    restores[0]["elapsed_ms"] = 1500
                else:
                    restores[4]["started_elapsed_s"] = None
                self.assertFalse(report_records(records)["complete"])


if __name__ == "__main__":
    unittest.main()
