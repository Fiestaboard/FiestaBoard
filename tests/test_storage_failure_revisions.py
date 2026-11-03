"""A rejected persistence attempt must leave the editor's revision retryable."""

import errno
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.collections.models import Collection
from src.collections.storage import CollectionStorage
from src.pages.models import Page
from src.pages.storage import CURRENT_SCHEMA_VERSION, PageRevisionConflict, PageStorage
from src.schedules.models import ScheduleEntry
from src.schedules.storage import ScheduleStorage


class TestStorageFailureRevisions(unittest.TestCase):
    def check_revision_retry(self, operation):
        cases = (
            (PageStorage, Page(name="Original", type="template", template=["KEEP"]), {"name": "Edited"}),
            (CollectionStorage, Collection(name="Original", page_ids=["page-a"]), {"name": "Edited"}),
            (ScheduleStorage, ScheduleEntry(page_id="page-a", start_time="09:00"), {"page_id": "page-b"}),
        )
        for storage_type, record, update in cases:
            with self.subTest(store=storage_type.__name__), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "records.json"
                store = storage_type(str(path))
                original = store.create(record)
                before = path.read_bytes()
                with patch("src.atomic_io.os.replace", side_effect=OSError(errno.ENOSPC, "synthetic disk full")):
                    with self.assertRaises(OSError):
                        if operation == "update":
                            store.update(original.id, update, expected_revision=original.revision)
                        else:
                            store.delete(original.id, expected_revision=original.revision)
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(store.get(original.id), original)

                # The original editor can explicitly retry after disk recovery.
                if operation == "update":
                    saved = store.update(original.id, update, expected_revision=original.revision)
                    self.assertNotEqual(saved.revision, original.revision)
                    with self.assertRaises(PageRevisionConflict):
                        store.delete(original.id, expected_revision=original.revision)
                    reloaded = storage_type(str(path)).get(original.id)
                    for key, value in update.items():
                        self.assertEqual(getattr(reloaded, key), value)
                else:
                    self.assertTrue(store.delete(original.id, expected_revision=original.revision))
                    self.assertEqual(storage_type(str(path)).count(), 0)

    def test_failed_update_preserves_revision_for_explicit_retry(self):
        self.check_revision_retry("update")

    def test_failed_delete_preserves_revision_for_explicit_retry(self):
        self.check_revision_retry("delete")

    def test_rejected_flexible_blocks_do_not_replace_document_on_later_save(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pages.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": CURRENT_SCHEMA_VERSION,
                        "future_document": {"authoring": "preserve"},
                        "pages": [
                            {
                                "id": "flex",
                                "name": "Flexible",
                                "type": "flexible",
                                "blocks": [{"id": "text", "kind": "text", "text": "KEEP"}],
                            }
                        ],
                    }
                )
            )
            store = PageStorage(str(path))
            original = store.get("flex")
            before = path.read_bytes()
            with patch("src.atomic_io.os.replace", side_effect=OSError(errno.ENOSPC, "synthetic disk full")):
                with self.assertRaises(OSError):
                    store.update(
                        original.id,
                        {"blocks": [{"id": "text", "kind": "text", "text": "REJECTED"}]},
                        expected_revision=original.revision,
                    )
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(store.get("flex").blocks[0].text, "KEEP")
            store.update(original.id, {"name": "Accepted"}, expected_revision=original.revision)
            persisted = json.loads(path.read_text())
            self.assertEqual(persisted["future_document"], {"authoring": "preserve"})
            self.assertEqual(persisted["pages"][0]["blocks"][0]["text"], "KEEP")
            for key in ("revision", "expected_revision", "edit_protocol", "document_protocol"):
                self.assertNotIn(key, persisted["pages"][0])
            reloaded = PageStorage(str(path)).get("flex")
            self.assertEqual(reloaded.name, "Accepted")
            self.assertEqual(reloaded.blocks[0].text, "KEEP")
