"""Offline reducer tests: retain partial evidence and reject false completeness."""

import json
import tempfile
import unittest
from pathlib import Path

from runtime_report import read_jsonl, report_records


def phase_records():
    return [{"record_type": "phase", "phase": phase, "event": event, "monotonic_elapsed_s": elapsed}
            for phase, event, elapsed in [("warmup", "start", 0), ("warmup", "end", 600),
                                          ("activity", "start", 600), ("activity", "end", 6600),
                                          ("drain", "start", 6600), ("drain", "end", 7200)]]


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
        records = [{"record_type": "resource", "monotonic_elapsed_s": t,
                    "processes": [{"role": "api", "pid": 42, "start_time_ticks": start, "rss_bytes": 100000}]}
                   for t, start in [(0, 100), (5, 100), (10, 200)]]
        report = report_records(records)
        self.assertEqual(report.get("process_restarts"), [{"role": "api", "pid": 42, "from_start": 100, "to_start": 200}])

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
        records = [{"record_type": "request", "phase": "sample", "operation": "render", "batch": batch,
                    "geometry": geometry, "cache": cache, "auth": "browser-cookie", "elapsed_ms": elapsed,
                    "http_status": status, "semantic_success": status == 200, "timed_out": False}
                   for batch, geometry, cache, elapsed, status in [(1, "note", "cached", 10, 200),
                                                                  (1, "panel", "cached", 500, 200),
                                                                  (2, "note", "cached", 20, 200),
                                                                  (1, "note", "forced", 0.1, 401)]]
        report = report_records(records)
        self.assertEqual(len(report.get("strata", [])), 4)
        panel = next(s for s in report["strata"] if s["geometry"] == "panel")
        self.assertEqual(panel["latency_ms"]["p95"], 500)
        failure = next(s for s in report["strata"] if s["cache"] == "forced")
        self.assertFalse(failure["valid"])
        self.assertIsNone(failure["latency_ms"]["p95"])


if __name__ == "__main__":
    unittest.main()
