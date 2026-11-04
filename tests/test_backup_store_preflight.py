"""Validate every consumed store before a restore changes any file."""

import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.backup.routes import router
from src.backup.service import BACKUP_FILE_MARKER, BACKUP_SCHEMA_VERSION, BackupError, BackupService


def document(data):
    return {BACKUP_FILE_MARKER: True, "schema_version": BACKUP_SCHEMA_VERSION, "data": data}


class TestBackupStorePreflight(unittest.TestCase):
    def test_malformed_consumed_store_is_rejected_before_earlier_files_change(self):
        for key in ("config", "settings", "pages", "collections", "schedules", "panels", "carousels"):
            for invalid in ([], "not an object", 17, False):
                with self.subTest(key=key, invalid=invalid), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    original = b'{"original":"preserve exactly"}\n'
                    (root / "config.json").write_bytes(original)
                    data = {"config": {"new": "must not land"}, key: invalid}
                    with (
                        patch("src.backup.service._reload_services") as reload,
                        patch.object(BackupService, "_reinstall_plugins") as reinstall,
                        patch.object(BackupService, "_owning_lock", side_effect=lambda name: nullcontext()),
                    ):
                        with self.assertRaises(BackupError):
                            BackupService(root).import_from_dict(document(data))
                    self.assertEqual((root / "config.json").read_bytes(), original)
                    self.assertEqual(sorted(p.name for p in root.iterdir()), ["config.json"])
                    reload.assert_not_called()
                    reinstall.assert_not_called()

    def test_malformed_late_payload_is_a_400_and_preserves_live_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = b'{"original":true}\n'
            (root / "config.json").write_bytes(original)
            app = FastAPI()
            app.include_router(router)
            with (
                patch("src.backup.get_backup_service", return_value=BackupService(root)),
                patch("src.backup.service._reload_services", return_value=[]),
                patch.object(BackupService, "_owning_lock", side_effect=lambda name: nullcontext()),
                TestClient(app) as client,
            ):
                response = client.post(
                    "/backup/import?reinstall_plugins=false",
                    json=document({"config": {"new": "not accepted"}, "schedules": ["invalid"]}),
                )
            self.assertEqual(response.status_code, 400)
            self.assertIn("schedules", response.json()["detail"])
            self.assertEqual((root / "config.json").read_bytes(), original)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["config.json"])

    def test_nullable_opaque_and_unused_legacy_values_keep_existing_compatibility(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = {
                "config": {"kept": {"opaque": [1, None]}},
                "settings": None,
                "collections": {"collections": []},
                "carousels": "unused legacy extra",
                "future_store": ["opaque"],
            }
            with (
                patch("src.backup.service._reload_services", return_value=[]),
                patch.object(BackupService, "_owning_lock", side_effect=lambda name: nullcontext()),
            ):
                result = BackupService(root).import_from_dict(document(data), reinstall_plugins=False)
            self.assertEqual(result["restored_files"], ["config.json", "collections.json"])
            self.assertIn("settings.json", result["skipped_files"])
            self.assertFalse((root / "future_store.json").exists())
            self.assertFalse((root / "carousels.json").exists())

    def test_consumed_legacy_carousel_object_remains_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = {"carousels": [{"id": "old", "page_ids": ["page"]}]}
            with (
                patch("src.backup.service._reload_services", return_value=[]),
                patch.object(BackupService, "_owning_lock", side_effect=lambda name: nullcontext()),
            ):
                result = BackupService(root).import_from_dict(
                    document({"collections": None, "carousels": legacy}), reinstall_plugins=False
                )
            self.assertEqual(result["restored_files"], ["carousels.json (legacy)"])
            self.assertTrue((root / "carousels.json").exists())
            self.assertFalse((root / "collections.json").exists())
