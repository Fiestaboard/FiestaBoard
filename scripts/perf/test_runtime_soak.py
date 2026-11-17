"""Offline scheduling and Linux-telemetry tests; never start a runtime."""

import tempfile
import unittest
from pathlib import Path

from runtime_collect import collect_snapshot
from runtime_soak import SlotPacer


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


if __name__ == "__main__":
    unittest.main()
