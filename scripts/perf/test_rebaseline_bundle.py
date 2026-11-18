"""Re-baseline and published-client replay tests; standard library only, no network."""

import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from fetch_published_client import replay_layer
from rebaseline_bundle import ceiling, rebaseline, sample_name

PERF = Path(__file__).resolve().parent


def layer(*entries):
    """An in-memory layer tar from (name, kind, payload) entries."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, kind, payload in entries:
            info = tarfile.TarInfo(name)
            if kind == "file":
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            elif kind == "dir":
                info.type = tarfile.DIRTYPE
                archive.addfile(info)
            elif kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = payload
                archive.addfile(info)
    buffer.seek(0)
    return tarfile.open(fileobj=buffer, mode="r")


class CeilingTests(unittest.TestCase):
    def test_committed_ceilings_are_exactly_the_rule_applied_to_the_committed_baseline(self):
        budget = json.loads((PERF / "bundle-budget.json").read_text())
        sample = json.loads((PERF / budget["baseline"]).read_text())
        self.assertEqual({key: ceiling(value) for key, value in sample["metrics"].items()}, budget["limits"])

    def test_reproduces_the_original_alpha3_ceilings(self):
        alpha3 = {
            "javascript_bytes": 6421698,
            "css_bytes": 255096,
            "font_bytes": 138068,
            "largest_javascript_bytes": 576617,
        }
        self.assertEqual(
            {key: ceiling(value) for key, value in alpha3.items()},
            {
                "javascript_bytes": 7064576,
                "css_bytes": 281600,
                "font_bytes": 152576,
                "largest_javascript_bytes": 634880,
            },
        )

    def test_rounds_up_to_whole_kib_and_never_below_110_percent(self):
        self.assertEqual(ceiling(0), 0)
        self.assertEqual(ceiling(1), 1024)
        self.assertEqual(ceiling(930), 1024)  # 1023 -> 1024
        self.assertEqual(ceiling(931), 2048)  # 1024.1 -> 2048
        for observed in (255096, 6421698, 7004704):
            self.assertGreaterEqual(ceiling(observed), observed * 1.1)
            self.assertLess(ceiling(observed), observed * 1.1 + 1024)

    def test_rejects_non_integer_input(self):
        for bad in (-1, 1.5, True, "1"):
            with self.assertRaises(ValueError):
                ceiling(bad)

    def test_sample_name_follows_version(self):
        self.assertEqual(sample_name("11.0.0-alpha.10"), "published-v11-alpha10.json")
        with self.assertRaises(ValueError):
            sample_name("11.0.0")


class RebaselineTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.fetched = self.root / "fetched"
        client = self.fetched / "client" / "assets"
        client.mkdir(parents=True)
        (self.fetched / "client" / "index.html").write_bytes(b"<html></html>")
        (client / "a.js").write_bytes(b"x" * 2000)
        (client / "a.css").write_bytes(b"y" * 100)
        (client / "f.woff2").write_bytes(b"z" * 10)
        (self.fetched / "provenance.json").write_text(json.dumps({"version_env": "11.0.0-alpha.10"}))
        self.perf = self.root / "perf"
        self.perf.mkdir()

    def test_writes_sample_and_budget_from_the_published_measurement(self):
        budget = rebaseline(self.fetched, "11.0.0-alpha.10", self.perf)
        self.assertEqual(budget["baseline"], "published-v11-alpha10.json")
        self.assertEqual(
            budget["limits"],
            {"css_bytes": 1024, "font_bytes": 1024, "javascript_bytes": 3072, "largest_javascript_bytes": 3072},
        )
        sample = json.loads((self.perf / "published-v11-alpha10.json").read_text())
        self.assertEqual(sample["metrics"]["javascript_bytes"], 2000)
        self.assertEqual(sample["provenance"]["version_env"], "11.0.0-alpha.10")
        self.assertEqual(json.loads((self.perf / "bundle-budget.json").read_text()), budget)

    def test_refuses_an_image_whose_version_does_not_match(self):
        with self.assertRaisesRegex(ValueError, "not '11.0.0-alpha.11'"):
            rebaseline(self.fetched, "11.0.0-alpha.11", self.perf)
        self.assertFalse((self.perf / "bundle-budget.json").exists())


class ReplayLayerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dest = Path(temp.name)

    def test_copies_only_regular_client_files_and_later_layers_replace_earlier(self):
        replay_layer(
            layer(
                ("app/web/build/client", "dir", b""),
                ("app/web/build/client/index.html", "file", b"one"),
                ("app/src/main.py", "file", b"not client"),
            ),
            self.dest,
        )
        affected = replay_layer(layer(("./app/web/build/client/index.html", "file", b"two")), self.dest)
        self.assertEqual((self.dest / "index.html").read_bytes(), b"two")
        self.assertEqual([item["path"] for item in affected], ["index.html"])
        self.assertFalse((self.dest / "main.py").exists())

    def test_fails_closed_on_a_symlink_in_the_client_tree(self):
        with self.assertRaisesRegex(ValueError, "Non-regular"):
            replay_layer(layer(("app/web/build/client/a.js", "symlink", "/etc/passwd")), self.dest)

    def test_fails_closed_on_whiteouts_that_touch_the_client_tree(self):
        for name in (
            "app/web/build/client/assets/.wh.old.js",
            "app/web/build/client/.wh..wh..opq",
            "app/web/build/.wh.client",
        ):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Whiteout"):
                replay_layer(layer((name, "file", b"")), self.dest)

    def test_ignores_whiteouts_elsewhere(self):
        replay_layer(layer(("app/src/.wh.legacy.py", "file", b"")), self.dest)
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_rejects_path_traversal(self):
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            replay_layer(layer(("app/web/build/client/../../../../x", "file", b"x")), self.dest)


if __name__ == "__main__":
    unittest.main()
