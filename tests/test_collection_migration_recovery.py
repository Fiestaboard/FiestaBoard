"""Legacy migration must remain retryable until the new store is committed."""

import errno
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.collections.storage import CollectionStorage


class TestCollectionMigrationRecovery(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.legacy = self.root / "carousels.json"
        self.target = self.root / "collections.json"
        self.backup = self.root / "carousels.json.pre-collections-backup"
        self.original = json.dumps(
            {
                "carousels": [
                    {
                        "id": "carousel:morning",
                        "name": "Morning",
                        "page_ids": ["one", "two"],
                        "interval_seconds": 45,
                    }
                ]
            }
        )
        self.legacy.write_text(self.original)

    def test_failed_target_commit_can_retry_on_next_start(self):
        with patch("src.atomic_io.os.replace", side_effect=OSError(errno.ENOSPC, "synthetic disk full")):
            with self.assertRaises(OSError):
                CollectionStorage(str(self.target))
        self.assertFalse(self.target.exists())

        # A new service instance after storage recovers must import without
        # requiring an operator to find and rename the backup manually.
        restarted = CollectionStorage(str(self.target))
        recovered = restarted.get("collection:morning")
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.page_ids, ["one", "two"])
        self.assertEqual(recovered.time.interval_seconds, 45)
        self.assertEqual(self.backup.read_text(), self.original)

    def test_legacy_is_archived_only_after_converted_data_is_readable(self):
        rename = Path.rename

        def observe_commit(source, destination):
            if source == self.legacy:
                self.assertTrue(self.target.exists(), "legacy source archived before target commit")
                persisted = json.loads(self.target.read_text())
                self.assertEqual(persisted["collections"][0]["id"], "collection:morning")
            return rename(source, destination)

        with patch.object(Path, "rename", observe_commit):
            storage = CollectionStorage(str(self.target))
        self.assertEqual(storage.count(), 1)
        self.assertFalse(self.legacy.exists())
        self.assertEqual(self.backup.read_text(), self.original)

    def test_archive_failure_does_not_reimport_over_the_committed_store(self):
        with patch.object(Path, "rename", side_effect=PermissionError("synthetic archive failure")):
            storage = CollectionStorage(str(self.target))
        self.assertEqual(storage.count(), 1)
        self.assertTrue(self.legacy.exists())
        storage.update("collection:morning", {"name": "Edited after migration"})

        restarted = CollectionStorage(str(self.target))
        self.assertEqual(restarted.get("collection:morning").name, "Edited after migration")
        self.assertEqual(self.legacy.read_text(), self.original)
