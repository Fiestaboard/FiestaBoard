"""Regenerating a demo must never commit an intermediate missing-page state."""

import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.pages.models import Page
from src.pages.service import PageService
from src.pages.storage import PageStorage

from src.plugins import routes
from src.plugins.manifest import DemoPageSchema
from src.plugins.service import PluginService
from src.storage.json_store import write_json_atomic

json_dump = json.dump


class DemoPageReplacement(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "pages.json"
        self.storage = PageStorage(str(self.path))
        self.service = PageService(self.storage)
        self.old, _ = self.service.create_demo_page("qa_demo", self.demo("Edited original"))
        self.note, _ = self.service.create_demo_page("qa_demo", self.demo("Note original", "note"))
        self.other, _ = self.service.create_demo_page("other_plugin", self.demo("Other original"))
        self.cached = object()
        self.service._preview_cache[self.old.id] = self.cached

    def tearDown(self):
        self.directory.cleanup()

    @staticmethod
    def demo(name, device_type="flagship"):
        return DemoPageSchema(name=name, template=[name], device_type=device_type)

    def fail_replacement(self, path, data, **kwargs):
        def partial_dump(payload, stream, **options):
            if any(page.get("name") == "Replacement" for page in payload["pages"]):
                stream.write("{partial")
                raise OSError("synthetic replacement save failure")
            return json_dump(payload, stream, **options)

        with patch("src.atomic_io.json.dump", side_effect=partial_dump):
            return write_json_atomic(path, data, **kwargs)

    def failed_attempt(self):
        with patch("src.storage.json_store.write_json_atomic", side_effect=self.fail_replacement):
            with self.assertRaisesRegex(OSError, "replacement save failure"):
                self.service.create_demo_page("qa_demo", self.demo("Replacement"))

    def test_failed_recreation_preserves_old_page_on_disk_in_memory_and_preview(self):
        before = self.path.read_bytes()
        self.failed_attempt()
        checks = {
            "disk": self.path.read_bytes() == before,
            "no leaked staging file": not list(self.path.parent.glob("pages.json.*.tmp")),
            "memory": self.storage.get(self.old.id) is self.old,
            "reload": PageStorage(str(self.path)).get(self.old.id) == self.old,
            "preview": self.service._preview_cache.get(self.old.id) is self.cached,
            "no phantom": not any(page.name == "Replacement" for page in self.storage.list_all()),
            "other geometry": self.storage.get(self.note.id) is self.note,
            "other plugin": self.storage.get(self.other.id) is self.other,
        }
        for name, condition in checks.items():
            with self.subTest(boundary=name):
                self.assertTrue(condition)

    def test_unrelated_save_and_retry_do_not_commit_failed_replacement(self):
        self.failed_attempt()
        unrelated = self.storage.create(Page(name="Unrelated", type="template", template=["unrelated"]))
        reloaded = PageStorage(str(self.path))
        with self.subTest(boundary="after unrelated save"):
            self.assertEqual(reloaded.get(self.old.id), self.old)
        with self.subTest(boundary="no failed replacement on disk"):
            self.assertFalse(any(page.name == "Replacement" for page in reloaded.list_all()))
        fresh, recreated = self.service.create_demo_page("qa_demo", self.demo("Retry"))
        self.assertTrue(recreated)
        self.assertNotEqual(fresh.id, self.old.id)
        self.assertIsNone(self.storage.get(self.old.id))
        self.assertEqual(PageStorage(str(self.path)).get(fresh.id), fresh)
        self.assertEqual(self.storage.get(unrelated.id), unrelated)
        self.assertNotIn(self.old.id, self.service._preview_cache)

    def test_successful_recreation_commits_one_complete_snapshot(self):
        snapshots = []

        def record(path, data, **kwargs):
            snapshots.append(data)
            return write_json_atomic(path, data, **kwargs)

        with patch("src.storage.json_store.write_json_atomic", side_effect=record):
            fresh, recreated = self.service.create_demo_page("qa_demo", self.demo("Replacement"))
        self.assertTrue(recreated)
        self.assertNotEqual(fresh.id, self.old.id)
        with self.subTest(boundary="one atomic write"):
            self.assertEqual(len(snapshots), 1)
        for snapshot in snapshots:
            with self.subTest(boundary="no committed gap"):
                selected = [
                    page
                    for page in snapshot["pages"]
                    if page.get("demo_plugin_id") == "qa_demo" and page.get("device_type") == "flagship"
                ]
                self.assertEqual(len(selected), 1)
        self.assertEqual(self.storage.get(self.note.id), self.note)
        self.assertEqual(self.storage.get(self.other.id), self.other)
        self.assertNotIn(self.old.id, self.service._preview_cache)

    def test_readers_keep_old_page_while_replacement_write_is_pending(self):
        entered = threading.Event()
        release = threading.Event()
        errors = []

        def blocked_write(path, data, **kwargs):
            if any(page.get("name") == "Replacement" for page in data["pages"]):
                entered.set()
                if not release.wait(3):
                    raise RuntimeError("test barrier timed out")
            return write_json_atomic(path, data, **kwargs)

        def replace():
            try:
                self.service.create_demo_page("qa_demo", self.demo("Replacement"))
            except BaseException as error:
                errors.append(error)

        worker = threading.Thread(target=replace)
        with patch("src.storage.json_store.write_json_atomic", side_effect=blocked_write):
            worker.start()
            try:
                self.assertTrue(entered.wait(3))
                with self.subTest(boundary="memory before commit"):
                    self.assertIs(self.storage.get(self.old.id), self.old)
                with self.subTest(boundary="disk before commit"):
                    self.assertEqual(PageStorage(str(self.path)).get(self.old.id), self.old)
                with self.subTest(boundary="preview before commit"):
                    self.assertIs(self.service._preview_cache.get(self.old.id), self.cached)
            finally:
                release.set()
                worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertIsNone(self.storage.get(self.old.id))
        self.assertEqual(self.service.get_demo_page("qa_demo", device_type="flagship").name, "Replacement")

    def test_http_recreation_failure_preserves_page_and_retry_succeeds(self):
        manifest = SimpleNamespace(demo={"flagship": self.demo("Replacement")}, settings_schema={})
        registry = SimpleNamespace(get_manifest=lambda identity: manifest)
        service = PluginService(registry=registry, page_service=self.service)
        app = FastAPI()
        app.include_router(routes.router, prefix="/api/v1")
        before = self.path.read_bytes()
        with patch.object(routes, "_plugin_service", return_value=service):
            with TestClient(app, raise_server_exceptions=False) as client:
                with patch("src.storage.json_store.write_json_atomic", side_effect=self.fail_replacement):
                    failed = client.post("/api/v1/plugins/qa_demo/demo-page?device_type=flagship")
                self.assertEqual(failed.status_code, 500)
                with self.subTest(boundary="HTTP failed save preserves disk"):
                    self.assertEqual(self.path.read_bytes(), before)
                with self.subTest(boundary="HTTP failed save preserves selected page"):
                    self.assertEqual(self.storage.get(self.old.id), self.old)
                retried = client.post("/api/v1/plugins/qa_demo/demo-page?device_type=flagship")
        self.assertEqual(retried.status_code, 201, retried.text)
        self.assertTrue(retried.json()["recreated"])
        self.assertEqual(PageStorage(str(self.path)).get(retried.json()["page"]["id"]).name, "Replacement")

    def test_failed_initial_creation_does_not_publish_a_phantom_demo(self):
        with patch("src.storage.json_store.write_json_atomic", side_effect=self.fail_replacement):
            with self.assertRaisesRegex(OSError, "replacement save failure"):
                self.service.create_demo_page("new_plugin", self.demo("Replacement"))
        self.assertIsNone(self.service.get_demo_page("new_plugin"))

    def test_replacement_preserves_unparseable_entries(self):
        data = json.loads(self.path.read_text())
        preserved = {"id": "future-page", "name": "Future", "type": "future-page-kind", "extra": "keep"}
        data["pages"].append(preserved)
        self.path.write_text(json.dumps(data))
        service = PageService(PageStorage(str(self.path)))
        fresh, recreated = service.create_demo_page("qa_demo", self.demo("Replacement"))
        self.assertTrue(recreated)
        data = json.loads(self.path.read_text())
        self.assertIn(preserved, data["pages"])
        self.assertIn(fresh.id, [page["id"] for page in data["pages"]])
        self.assertNotIn(self.old.id, [page["id"] for page in data["pages"]])
