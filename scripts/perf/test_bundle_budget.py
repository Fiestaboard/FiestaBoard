"""Offline utility regression tests; safe for local standard-library execution."""

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from bundle_budget import check_budget, measure


class BundleBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.client = self.root / "client"
        (self.client / "assets").mkdir(parents=True)
        self.write("index.html", b"<html></html>")
        self.write("assets/a.js", b"12345")
        self.write("sw.js", b"123")
        self.write("assets/a.css", b"1234")
        self.write("assets/font.woff2", b"123456")
        self.budget = {
            "schema_version": 1,
            "limits": {
                "javascript_bytes": 8,
                "css_bytes": 4,
                "font_bytes": 6,
                "largest_javascript_bytes": 5,
            },
        }

    def write(self, name, content):
        (self.client / name).write_bytes(content)

    def test_counts_all_chunks_and_service_worker_once(self):
        report = measure(self.client)
        self.assertEqual(report["metrics"], self.budget["limits"])
        self.assertEqual(report["groups"]["javascript"]["count"], 2)
        self.assertEqual(report["groups"]["font"]["count"], 1)

    def test_maps_are_storage_not_served_code(self):
        self.write("assets/a.js.map", b"x" * 1000)
        report = measure(self.client)
        self.assertEqual(report["metrics"]["javascript_bytes"], 8)
        self.assertEqual(report["groups"]["source_map"]["raw_bytes"], 1000)
        # 13 HTML + 8 JavaScript + 4 CSS + 6 font + 1000 map bytes.
        self.assertEqual(report["total_disk_bytes"], 1031)

    def test_file_hashes_and_paths_are_stable(self):
        report = measure(self.client)
        paths = [item["path"] for item in report["files"]]
        self.assertEqual(paths, sorted(paths))
        js = next(item for item in report["files"] if item["path"] == "assets/a.js")
        self.assertEqual(js["sha256"], hashlib.sha256(b"12345").hexdigest())
        self.assertEqual(js["raw_bytes"], 5)
        # Tiny five-byte payload plus the gzip header/trailer: fixed 25 bytes.
        self.assertEqual(js["gzip6_bytes"], 25)
        self.assertEqual(report, measure(self.client))

    def test_rejects_missing_root(self):
        with self.assertRaisesRegex(ValueError, "directory"):
            measure(self.root / "absent")

    def test_rejects_incomplete_output(self):
        for path, message in [("index.html", "index.html"), ("assets/a.css", "CSS")]:
            with self.subTest(path=path):
                file = self.client / path
                data = file.read_bytes()
                file.unlink()
                with self.assertRaisesRegex(ValueError, message):
                    measure(self.client)
                file.write_bytes(data)

    def test_rejects_absent_javascript(self):
        (self.client / "assets/a.js").unlink()
        (self.client / "sw.js").unlink()
        with self.assertRaisesRegex(ValueError, "JavaScript"):
            measure(self.client)

    def test_rejects_symlinked_files_and_directories(self):
        for target in [self.client / "index.html", self.client / "assets"]:
            with self.subTest(target=target):
                link = self.client / "link"
                link.symlink_to(target)
                with self.assertRaisesRegex(ValueError, "symlink"):
                    measure(self.client)
                link.unlink()

    def test_rejects_unreadable_subdirectory_instead_of_undercounting(self):
        blocked = self.client / "blocked"
        blocked.mkdir()
        (blocked / "large.js").write_bytes(b"x" * 10000)
        blocked.chmod(0)
        try:
            try:
                list(blocked.iterdir())
            except PermissionError:
                pass
            else:
                self.skipTest("Process can read chmod-000 directories")
            with self.assertRaises(PermissionError):
                measure(self.client)
        finally:
            blocked.chmod(0o700)

    def test_equality_passes_and_each_overshoot_fails(self):
        report = measure(self.client)
        self.assertEqual(check_budget(report, self.budget), [])
        for metric in self.budget["limits"]:
            with self.subTest(metric=metric):
                smaller = copy.deepcopy(self.budget)
                smaller["limits"][metric] -= 1
                violations = check_budget(report, smaller)
                self.assertEqual(len(violations), 1)
                self.assertIn(metric, violations[0])

    def test_missing_budget_metric_fails_closed(self):
        del self.budget["limits"]["css_bytes"]
        with self.assertRaisesRegex(ValueError, "limits"):
            check_budget(measure(self.client), self.budget)

    def test_invalid_budget_values_fail_closed(self):
        for value in [-1, True, "8", 8.0, float("nan"), None]:
            with self.subTest(value=value):
                self.budget["limits"]["javascript_bytes"] = value
                with self.assertRaisesRegex(ValueError, "integer"):
                    check_budget(measure(self.client), self.budget)

    def test_invalid_budget_schema_fails_closed(self):
        for value in [None, [], {"schema_version": 2, "limits": {}}, {"schema_version": True}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                check_budget(measure(self.client), value)

    def test_cli_writes_report_even_when_budget_exceeded(self):
        self.write("assets/new.js", b"too much javascript")
        budget_path = self.root / "budget.json"
        budget_path.write_text(json.dumps(self.budget))
        report_path = self.root / "report.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("bundle_budget.py")),
                "--client",
                str(self.client),
                "--budget",
                str(budget_path),
                "--report",
                str(report_path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stderr)
        report = json.loads(report_path.read_text())
        self.assertEqual(report["budget_status"], "fail")
        self.assertEqual(len(report["violations"]), 2)
        self.assertEqual(report["metrics"]["javascript_bytes"], 27)


if __name__ == "__main__":
    unittest.main()
