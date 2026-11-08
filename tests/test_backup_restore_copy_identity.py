"""A later restore must not overwrite a previously advertised rollback copy."""

import tempfile
import unittest
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.backup.service import BACKUP_FILE_MARKER, BACKUP_SCHEMA_VERSION, BackupRestoreAborted, BackupService


def document(marker):
    return {
        BACKUP_FILE_MARKER: True,
        "schema_version": BACKUP_SCHEMA_VERSION,
        "data": {"config": {"marker": marker}, "pages": {"pages": [], "marker": marker}},
    }


class TestRestoreCopyIdentity(unittest.TestCase):
    def test_same_clock_restores_keep_each_advertised_multifile_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = {"config.json": b'{"original":"config"}\n', "pages.json": b'{"original":"pages"}\n'}
            for name, data in original.items():
                (root / name).write_bytes(data)
            fixed = datetime(2026, 11, 4, 12, 0, 0, 123456, tzinfo=UTC)
            with (
                patch("src.backup.service.datetime") as clock,
                patch("src.backup.service._reload_services", return_value=[]),
                patch.object(BackupService, "_owning_lock", side_effect=lambda filename: nullcontext()),
            ):
                clock.now.return_value = fixed
                first = BackupService(root).import_from_dict(document("FIRST"), reinstall_plugins=False)
                intermediate = {name: (root / name).read_bytes() for name in original}
                second = BackupService(root).import_from_dict(document("SECOND"), reinstall_plugins=False)
            for name, data in original.items():
                self.assertEqual((root / (name + first["pre_restore_backup_suffix"])).read_bytes(), data)
                self.assertEqual((root / (name + second["pre_restore_backup_suffix"])).read_bytes(), intermediate[name])
            self.assertNotEqual(first["pre_restore_backup_suffix"], second["pre_restore_backup_suffix"])
            self.assertEqual(first["pre_restore_backup_files"], ["config.json", "pages.json"])
            self.assertEqual(second["pre_restore_backup_files"], ["config.json", "pages.json"])

    def test_failed_second_copy_cannot_delete_first_restores_rollback_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = b'{"marker":"ORIGINAL"}\n'
            (root / "config.json").write_bytes(original)
            fixed = datetime(2026, 11, 4, 12, tzinfo=UTC)
            with (
                patch("src.backup.service.datetime") as clock,
                patch("src.backup.service._reload_services", return_value=[]),
                patch.object(BackupService, "_owning_lock", side_effect=lambda filename: nullcontext()),
            ):
                clock.now.return_value = fixed
                first = BackupService(root).import_from_dict(document("FIRST"), reinstall_plugins=False)
                prior = root / ("config.json" + first["pre_restore_backup_suffix"])
                live_before = (root / "config.json").read_bytes()

                def partial_copy(source, destination):
                    Path(destination).write_bytes(b"PARTIAL")
                    raise OSError("synthetic backup copy failure")

                with patch("src.backup.service.shutil.copy2", side_effect=partial_copy):
                    with self.assertRaises(BackupRestoreAborted):
                        BackupService(root).import_from_dict(document("SECOND"), reinstall_plugins=False)
            self.assertTrue(prior.exists(), "failed copy cleanup deleted the earlier rollback file")
            self.assertEqual(prior.read_bytes(), original)
            self.assertEqual((root / "config.json").read_bytes(), live_before)
            self.assertEqual(list(root.glob("config.json.pre-restore-*")), [prior])
