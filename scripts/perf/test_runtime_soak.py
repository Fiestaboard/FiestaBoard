"""Offline scheduling and Linux-telemetry tests; never start a runtime."""

import tempfile
import unittest
from pathlib import Path
import json

from runtime_collect import collect_snapshot, validate_collector_anchor
from runtime_collect import main as collector_main
from runtime_soak import SlotPacer, run_phase, soak_operations, run_soak
from runtime_common import HttpResult, JsonClient, JsonlWriter, ProtocolError
from runtime_api import ApiOperation
from test_runtime_api import fixture, fixture_transport, run_context
from contextlib import redirect_stderr
import io


class ManualClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class SoakContractTests(unittest.TestCase):
    def test_overrun_drops_missed_arrivals_and_waits_for_next_deadline(self):
        # Scheduling the oldest due slot after an overrun creates a catch-up burst.
        pacer = SlotPacer(start=100.0, duration=10.0)
        first = pacer.next_slot(100.0)
        self.assertEqual(first, {"slot": 0, "deadline": 100.0, "missed": []})
        next_slot = pacer.next_slot(102.4)
        self.assertEqual(next_slot, {"slot": 3, "deadline": 103.0, "missed": [1, 2]})
        self.assertEqual(pacer.next_slot(103.0)["deadline"], 104.0)

    def test_phase_tail_retains_dropped_slots_without_running_them(self):
        # Losing end-of-phase misses would exaggerate achieved compression/counts.
        pacer = SlotPacer(start=0.0, duration=4.0)
        pacer.next_slot(0.0)
        tail = pacer.next_slot(5.0)
        self.assertIsNone(tail["slot"])
        self.assertEqual(tail["missed"], [1, 2, 3])

    def test_proc_identity_and_rss_units_are_preserved_heap_stays_unavailable(self):
        # RSS kB is not bytes or Python heap; stat's command can contain spaces/parentheses.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proc = root / "proc"
            process = proc / "42"
            process.mkdir(parents=True)
            # Fields3..21 are19 entries; field22 is process start time.
            (process / "stat").write_text("42 (api worker (main)) " + " ".join(["S"] + ["0"] * 18 + ["12345", "0"]))
            (process / "status").write_text("VmRSS:\t100 kB\nRssAnon:\t60 kB\nThreads:\t3\n")
            (process / "fd").mkdir()
            (process / "fd" / "0").touch()
            cgroup = root / "cgroup"
            cgroup.mkdir()
            (cgroup / "memory.current").write_text("204800\n")
            data = root / "data"
            data.mkdir()
            (data / "pages.json").write_bytes(b"12345")
            report = collect_snapshot(proc, cgroup, data, {"api": 42})
        self.assertIsNotNone(report.get("processes"))
        api = report["processes"][0]
        self.assertEqual(api["start_time_ticks"], 12345)
        self.assertEqual(api["rss_bytes"], 102400)
        self.assertEqual(api["rss_anon_bytes"], 61440)
        self.assertEqual(api["fd_count"], 1)
        self.assertEqual(report["data_store_bytes"], 5)
        self.assertEqual(report["cgroup"]["memory.current"], 204800)
        self.assertFalse(report["python_heap"]["available"])
        self.assertFalse(report["queues"]["available"])

    def test_executable_phase_drops_overrun_slots_without_concurrent_catchup(self):
        # A correct pacer can still be misused by a driver that replays its missed list as work.
        clock = ManualClock()
        arrivals = []

        def transport(method, url, payload, headers, timeout):
            arrivals.append(clock())
            clock.now += 2.4 if len(arrivals) == 1 else 0.1
            return HttpResult(200, {"ok": True}, elapsed_ms=2400 if len(arrivals) == 1 else 100)

        client = JsonClient("http://hub.invalid:3000", {}, transport=transport)
        operations = [ApiOperation(f"slot{i}", "note", "mixed", "GET", "/api/v1/health", None, lambda body: None) for i in range(10)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "soak.jsonl"
            writer = JsonlWriter(path, "unit-run")
            try:
                result = run_phase(client, operations, writer, phase="activity", start=100.0, duration=5,
                                   slot_seconds=1, clock=clock, sleep=clock.sleep, measurement_start=100.0)
            finally:
                writer.close()
            records = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(arrivals, [100.0, 103.0, 104.0])
        self.assertEqual(result["attempted"], 3)
        self.assertEqual(result["missed"], 2)
        self.assertEqual([r["slot"] for r in records if r["record_type"] == "missed_slot"], [1, 2])

    def test_executable_auth_abort_stops_before_next_slot(self):
        # The phase driver must honor the same auth abort as endpoint calibration.
        clock = ManualClock()
        calls = []
        client = JsonClient("http://hub.invalid:3000", {}, transport=lambda *args: calls.append(args) or HttpResult(401, {}))
        operation = ApiOperation("status", "all", "n/a", "GET", "/api/v1/status", None, lambda body: None)
        with tempfile.TemporaryDirectory() as directory:
            writer = JsonlWriter(Path(directory) / "soak.jsonl", "unit-run")
            try:
                result = run_phase(client, [operation] * 10, writer, phase="activity", start=100.0, duration=20,
                                   slot_seconds=1, clock=clock, sleep=clock.sleep, measurement_start=100.0)
            finally:
                writer.close()
        self.assertTrue(result.get("aborted"))
        self.assertEqual(len(calls), 1)

    def test_soak_ring_uses_twelve_compatible_pages_and_variable_only_dryrun(self):
        # A board-agnostic ring would send a Note page to the wrong output or repeatedly save only4 pages.
        data = fixture()
        touched = set()
        for cycle in range(12):
            geometry = ("flagship", "note", "array", "panel")[cycle % 4]
            operations = soak_operations(data, geometry, (cycle // 4) % 3, cycle)
            self.assertEqual(len(operations), 10)
            save, send, dryrun = operations[7], operations[8], operations[5]
            page_id = save.path.rsplit("/", 1)[1]
            touched.add(page_id)
            self.assertEqual(send.payload["page_id"], page_id)
            self.assertEqual(send.path, f"/api/v1/boards/{data['boards'][geometry]['id']}/message")
            self.assertIn("-variable/", dryrun.path)
            self.assertEqual((dryrun.payload["window_seconds"], dryrun.payload["step_seconds"]), (3600, 300))
        self.assertEqual(len(touched), 12)

    def test_collector_refuses_foreign_clock_or_pid_namespace_or_non_api_process(self):
        # A process with the same numeric PID in another container is not the published API.
        anchor = {"schema_version": 1, "run_id": "unit-run", "boot_id": "boot-a", "pid_namespace": "pid:[100]",
                  "start_monotonic": 100.0}
        for boot_id, namespace, command in [("boot-b", "pid:[100]", "uvicorn src.api_server:app"),
                                             ("boot-a", "pid:[200]", "uvicorn src.api_server:app"),
                                             ("boot-a", "pid:[100]", "pytest test_api.py")]:
            with self.subTest(boot=boot_id, namespace=namespace, command=command):
                with self.assertRaises(ProtocolError):
                    validate_collector_anchor(anchor, boot_id=boot_id, pid_namespace=namespace, api_cmdline=command)

    def test_dynamic_phase_rotates_geometry_only_at_complete_cycle_boundaries(self):
        # A fixed operation list would measure one geometry for the whole active phase.
        clock = ManualClock()
        client = JsonClient("http://hub.invalid:3000", {}, transport=lambda *args: HttpResult(200, {}))
        geometries = ("flagship", "note", "array", "panel")

        def factory(cycle):
            return [ApiOperation(f"slot{i}", geometries[cycle % 4], "mixed", "GET", "/api/v1/health", None,
                                 lambda body: None) for i in range(10)]

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "soak.jsonl"
            writer = JsonlWriter(path, "unit-run")
            try:
                run_phase(client, factory, writer, phase="activity", start=100, duration=120, slot_seconds=1,
                          clock=clock, sleep=clock.sleep, measurement_start=100)
            finally:
                writer.close()
            requests = [json.loads(line) for line in path.read_text().splitlines() if json.loads(line)["record_type"] == "request"]
        self.assertEqual(len(requests), 120)
        self.assertEqual([r["geometry"] for r in requests[::10]], list(geometries) * 3)

    def test_short_orchestration_records_all_phases_but_never_claims_soak_completion(self):
        # A valid short diagnostic must not inherit7200s completeness from planned constants.
        clock = ManualClock()
        data = fixture()
        transport = fixture_transport(data)
        transport.responses[("GET", "/api/v1/health")] = HttpResult(200, {"status": "healthy"})
        client = JsonClient(data["base_url"], {}, transport=transport, run_context=run_context())
        anchor = {"schema_version": 1, "run_id": "unit-run", "boot_id": "boot-a", "pid_namespace": "pid:[100]",
                  "start_monotonic": 100.0}
        ready = {**anchor, "api_cmdline": "python -m uvicorn src.api_server:app", "api_pid": 42, "api_start_time_ticks": 123}
        operation = ApiOperation("health", "all", "n/a", "GET", "/api/v1/health", None, lambda body: None)
        with tempfile.TemporaryDirectory() as directory:
            report = run_soak(client, data, Path(directory), anchor, ready, phase_seconds=(1, 10, 1),
                              clock=clock, sleep=clock.sleep, operation_factory=lambda cycle: [operation] * 10)
            self.assertEqual(report.get("measured_seconds"), 12)
            self.assertEqual(report.get("activity_requests"), 10)
            self.assertFalse(report.get("complete", True))
            self.assertTrue(report.get("diagnostic"))
            path = Path(directory) / "soak.jsonl"
            self.assertTrue(path.exists())
            phases = [json.loads(line) for line in path.read_text().splitlines() if json.loads(line)["record_type"] == "phase"]
        self.assertEqual([(r["phase"], r["event"]) for r in phases], [(p, e) for p in ("warmup", "activity", "drain") for e in ("start", "end")])

    def test_wrong_collector_ready_identity_rejected_before_any_api_read(self):
        # Readiness from another namespace/clock must not start even a diagnostic phase.
        data = fixture()
        transport = fixture_transport(data)
        client = JsonClient(data["base_url"], {}, transport=transport, run_context=run_context())
        anchor = {"schema_version": 1, "run_id": "unit-run", "boot_id": "boot-a", "pid_namespace": "pid:[100]",
                  "start_monotonic": 100.0}
        ready = {**anchor, "boot_id": "boot-b", "api_cmdline": "uvicorn src.api_server:app", "api_pid": 42,
                 "api_start_time_ticks": 123}
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ProtocolError):
                run_soak(client, data, Path(directory), anchor, ready, phase_seconds=(1, 10, 1),
                         clock=ManualClock(), sleep=lambda seconds: None)
        self.assertEqual(transport.exchanges, [])

    def test_collector_cli_refuses_foreign_local_kernel_before_sampling(self):
        # CLI wiring must not skip the pure identity guard and produce plausible resource samples.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proc = root / "proc"
            (proc / "sys/kernel/random").mkdir(parents=True)
            (proc / "sys/kernel/random/boot_id").write_text("boot-b\n")
            (proc / "self/ns").mkdir(parents=True)
            (proc / "self/ns/pid").symlink_to("pid:[100]")
            (proc / "42").mkdir()
            (proc / "42/cmdline").write_text("python\0-m\0uvicorn\0src.api_server:app\0")
            anchor = {"schema_version": 1, "run_id": "unit-run", "boot_id": "boot-a", "pid_namespace": "pid:[100]",
                      "start_monotonic": 100.0}
            path = root / "anchor.json"
            path.write_text(json.dumps(anchor))
            with redirect_stderr(io.StringIO()):
                code = collector_main(["--anchor", str(path), "--proc-root", str(proc), "--api-pid", "42",
                                       "--data-dir", str(root / "data"), "--out-dir", str(root / "out")])
            self.assertEqual(code, 2)
            self.assertFalse((root / "out/resources.jsonl").exists())

    def test_initial_subslot_jitter_does_not_drop_first_arrival(self):
        # Real writer/preflight overhead makes the first clock read slightly later than the declared start.
        clock = ManualClock()
        clock.now = 100.001
        arrivals = []
        client = JsonClient("http://hub.invalid:3000", {}, transport=lambda *args: arrivals.append(clock()) or HttpResult(200, {}))
        operation = ApiOperation("status", "all", "n/a", "GET", "/api/v1/status", None, lambda body: None)
        with tempfile.TemporaryDirectory() as directory:
            writer = JsonlWriter(Path(directory) / "soak.jsonl", "unit-run")
            try:
                result = run_phase(client, [operation] * 10, writer, phase="activity", start=100, duration=2,
                                   slot_seconds=1, clock=clock, sleep=clock.sleep, measurement_start=100)
            finally:
                writer.close()
        self.assertEqual(arrivals, [100.001, 101.0])
        self.assertEqual(result["missed"], 0)

    def test_repeated_one_millisecond_wakeups_do_not_rebase_deadlines(self):
        # OS wake jitter should be retained as lateness, not shift every later planned deadline or drop all slots.
        class JitterClock(ManualClock):
            def sleep(self, seconds):
                self.now += seconds + 0.001

        clock = JitterClock()
        clock.now = 100.001
        arrivals = []
        client = JsonClient("http://hub.invalid:3000", {}, transport=lambda *args: arrivals.append(clock()) or HttpResult(200, {}))
        operation = ApiOperation("status", "all", "n/a", "GET", "/api/v1/status", None, lambda body: None)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "soak.jsonl"
            writer = JsonlWriter(path, "unit-run")
            try:
                result = run_phase(client, [operation] * 10, writer, phase="activity", start=100, duration=4,
                    slot_seconds=1, clock=clock, sleep=clock.sleep, measurement_start=100, dispatch_grace_seconds=0.05)
            finally:
                writer.close()
            requests = [r for r in map(json.loads, path.read_text().splitlines()) if r["record_type"] == "request"]
        self.assertEqual(len(arrivals), 4)
        self.assertEqual([r["scheduled_elapsed_s"] for r in requests], [0, 1, 2, 3])
        self.assertEqual(result["missed"], 0)
        for r in requests:
            self.assertAlmostEqual(r["dispatch_lateness_ms"], 1.0)

    def test_reserved_wakeup_beyond_declared_grace_drops_slot(self):
        # A50ms grace cannot quietly become a full1s arrival window and create near-adjacent catch-up requests.
        class LateClock(ManualClock):
            def sleep(self, seconds):
                self.now += seconds + 0.06

        clock, arrivals = LateClock(), []
        client = JsonClient("http://hub.invalid:3000", {}, transport=lambda *args: arrivals.append(clock()) or HttpResult(200, {}))
        operation = ApiOperation("status", "all", "n/a", "GET", "/api/v1/status", None, lambda body: None)
        with tempfile.TemporaryDirectory() as directory:
            writer = JsonlWriter(Path(directory) / "soak.jsonl", "unit-run")
            try:
                result = run_phase(client, [operation] * 10, writer, phase="activity", start=100, duration=4,
                    slot_seconds=1, clock=clock, sleep=clock.sleep, measurement_start=100, dispatch_grace_seconds=0.05)
            finally:
                writer.close()
        self.assertEqual(arrivals, [100])
        self.assertEqual(result["missed"], 3)


if __name__ == "__main__":
    unittest.main()
