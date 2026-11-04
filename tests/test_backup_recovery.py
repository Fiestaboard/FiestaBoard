"""Caught restore failures compensate file contents without claiming crash atomicity."""

import json
import os
import shutil
import stat
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.backup.routes import router
from src.backup.service import BACKUP_FILE_MARKER, BACKUP_SCHEMA_VERSION, DATA_FILES, BackupService


def document():
    return {
        BACKUP_FILE_MARKER: True,
        "schema_version": BACKUP_SCHEMA_VERSION,
        "data": {name[:-5]: {"marker": "NEW-" + name} for name in DATA_FILES},
    }


class TestBackupRecovery(unittest.TestCase):
    @contextmanager
    def environment(self, present=DATA_FILES):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = {name: (json.dumps({"marker": "OLD-" + name}) + "\r\n").encode() for name in present}
            for name, content in before.items():
                (root / name).write_bytes(content)
                (root / name).chmod(0o600)
            (root / "unrelated.keep").write_bytes(b"UNCHANGED")
            locks = {name: RLock() for name in (*DATA_FILES, "carousels.json")}
            app = FastAPI()
            app.include_router(router)
            service = BackupService(root)
            with (
                patch("src.backup.get_backup_service", return_value=service),
                patch.object(BackupService, "_owning_lock", side_effect=lambda name: locks[name]),
                patch("src.backup.service._reload_services") as reload,
                patch.object(service, "_reinstall_plugins") as reinstall,
                TestClient(app) as client,
            ):
                yield root, before, client, reload, reinstall, locks

    def test_copy_and_commit_failures_restore_existing_and_remove_new_files(self):
        real_copy, real_replace = shutil.copy2, os.replace
        for present in (set(DATA_FILES), set(DATA_FILES[:3]), set()):
            for phase in ("copy", "commit"):
                for target in DATA_FILES:
                    if phase == "copy" and target not in present:
                        continue
                    with self.subTest(present=len(present), phase=phase, target=target), self.environment(present) as env:
                        root, before, client, reload, reinstall, _ = env
                        hit = []

                        def copy(source, destination):
                            if phase == "copy" and Path(source).name == target:
                                hit.append(True)
                                Path(destination).write_bytes(b"PARTIAL")
                                raise OSError("synthetic copy failure")
                            return real_copy(source, destination)

                        def replace(source, destination):
                            if phase == "commit" and Path(destination).name == target:
                                hit.append(True)
                                raise OSError("synthetic commit failure")
                            return real_replace(source, destination)

                        with (
                            patch("src.backup.service.shutil.copy2", side_effect=copy),
                            patch("src.atomic_io.os.replace", side_effect=replace),
                        ):
                            response = client.post("/backup/import?reinstall_plugins=false", json=document())
                        self.assertEqual(response.status_code, 500)
                        self.assertTrue(hit)
                        for name in DATA_FILES:
                            if name in before:
                                self.assertEqual((root / name).read_bytes(), before[name])
                                self.assertEqual(stat.S_IMODE((root / name).stat().st_mode), 0o600)
                            else:
                                self.assertFalse((root / name).exists())
                            for snapshot in root.glob(name + ".pre-restore-*"):
                                self.assertEqual(snapshot.read_bytes(), before[name])
                        self.assertEqual((root / "unrelated.keep").read_bytes(), b"UNCHANGED")
                        reload.assert_not_called()
                        reinstall.assert_not_called()

    def test_rollback_failure_is_reported_and_does_not_stop_other_compensation(self):
        real_replace = os.replace
        with self.environment() as (root, before, client, reload, reinstall, _):
            failed = []

            def replace(source, destination):
                name = Path(destination).name
                if name == "pages.json":
                    failed.append(True)
                    raise OSError("synthetic restore failure")
                if failed and name == "settings.json":
                    raise OSError("synthetic rollback failure")
                return real_replace(source, destination)

            with patch("src.atomic_io.os.replace", side_effect=replace):
                response = client.post("/backup/import?reinstall_plugins=false", json=document())
            self.assertEqual((root / "config.json").read_bytes(), before["config.json"])
            self.assertNotEqual((root / "settings.json").read_bytes(), before["settings.json"])
            self.assertIn("recovery incomplete", response.json()["detail"].lower())
            self.assertIn("settings.json", response.json()["detail"])
            self.assertIn(".pre-restore-", response.json()["detail"])
            snapshots = list(root.glob("settings.json.pre-restore-*"))
            self.assertEqual(len(snapshots), 1)
            self.assertEqual(snapshots[0].read_bytes(), before["settings.json"])
            reload.assert_not_called()
            reinstall.assert_not_called()

    def test_intervening_writer_is_preserved_and_reported_as_conflict(self):
        real_replace = os.replace
        with self.environment() as (root, before, client, _, _, locks):
            concurrent = b'{"accepted":"concurrent writer"}\n'

            def replace(source, destination):
                if Path(destination).name == "settings.json":
                    with locks["config.json"]:
                        (root / "config.json").write_bytes(concurrent)
                    raise OSError("synthetic restore failure")
                return real_replace(source, destination)

            with patch("src.atomic_io.os.replace", side_effect=replace):
                response = client.post("/backup/import?reinstall_plugins=false", json=document())
            self.assertEqual((root / "config.json").read_bytes(), concurrent)
            self.assertIn("recovery incomplete", response.json()["detail"].lower())
            self.assertIn("changed", response.json()["detail"].lower())
            self.assertEqual(next(root.glob("config.json.pre-restore-*")).read_bytes(), before["config.json"])

    def test_replace_that_lands_then_raises_is_compensated(self):
        real_replace = os.replace
        with self.environment() as (root, before, client, _, _, _):
            failed = []

            def replace(source, destination):
                result = real_replace(source, destination)
                if Path(destination).name == "settings.json" and not failed:
                    failed.append(True)
                    raise OSError("synthetic error after rename")
                return result

            with patch("src.atomic_io.os.replace", side_effect=replace):
                response = client.post("/backup/import?reinstall_plugins=false", json=document())
            for name, data in before.items():
                self.assertEqual((root / name).read_bytes(), data)
            self.assertEqual(response.status_code, 500)
            self.assertIn("recovered", response.json()["detail"].lower())

    def test_identical_content_still_recovers_original_mode(self):
        real_replace = os.replace
        with self.environment() as (root, _, client, _, _, _):
            exact = json.dumps(document()["data"]["config"], indent=2).encode()
            (root / "config.json").write_bytes(exact)
            (root / "config.json").chmod(0o600)

            def replace(source, destination):
                if Path(destination).name == "settings.json":
                    raise OSError("synthetic restore failure")
                return real_replace(source, destination)

            with patch("src.atomic_io.os.replace", side_effect=replace):
                response = client.post("/backup/import?reinstall_plugins=false", json=document())
            self.assertEqual((root / "config.json").read_bytes(), exact)
            self.assertEqual(stat.S_IMODE((root / "config.json").stat().st_mode), 0o600)
            self.assertEqual(response.status_code, 500)

    def test_failed_removal_is_reported_and_other_files_are_recovered(self):
        real_replace, real_unlink = os.replace, Path.unlink
        with self.environment({"config.json"}) as (root, before, client, _, _, _):
            def replace(source, destination):
                if Path(destination).name == "pages.json":
                    raise OSError("synthetic forward failure")
                return real_replace(source, destination)

            def unlink(path, *args, **kwargs):
                if path.name == "settings.json":
                    raise OSError("synthetic removal failure")
                return real_unlink(path, *args, **kwargs)

            with patch("src.atomic_io.os.replace", side_effect=replace), patch.object(Path, "unlink", unlink):
                response = client.post("/backup/import?reinstall_plugins=false", json=document())
            self.assertEqual((root / "config.json").read_bytes(), before["config.json"])
            self.assertTrue((root / "settings.json").exists())
            self.assertIn("recovery incomplete", response.json()["detail"].lower())
            self.assertIn("settings.json", response.json()["detail"])

    def test_snapshot_read_and_serialization_failure_recover_prior_files(self):
        for phase in ("snapshot", "serialize"):
            with self.subTest(phase=phase), self.environment() as (root, before, _, reload, reinstall, _):
                service = BackupService(root)
                backup = document()
                real_read = Path.read_bytes
                if phase == "serialize":
                    backup["data"]["settings"] = {"invalid": object()}

                def read(path):
                    if phase == "snapshot" and path == root / "settings.json":
                        raise OSError("synthetic snapshot failure")
                    return real_read(path)

                with patch.object(Path, "read_bytes", read):
                    with self.assertRaises(Exception):
                        service.import_from_dict(backup, reinstall_plugins=False)
                for name, data in before.items():
                    self.assertEqual((root / name).read_bytes(), data)
                reload.assert_not_called()
                reinstall.assert_not_called()

    def test_legacy_carousels_are_compensated_on_later_failure(self):
        real_replace = os.replace
        for existed in (False, True):
            with self.subTest(existed=existed), self.environment() as (root, before, client, _, _, _):
                old_legacy = b'{"carousels":[]}\r\n'
                if existed:
                    (root / "carousels.json").write_bytes(old_legacy)
                    (root / "carousels.json").chmod(0o600)
                backup = document()
                backup["data"]["collections"] = None
                backup["data"]["carousels"] = {"carousels": [{"name": "imported"}]}

                def replace(source, destination):
                    if Path(destination).name == "schedules.json":
                        raise OSError("synthetic forward failure")
                    return real_replace(source, destination)

                with patch("src.atomic_io.os.replace", side_effect=replace):
                    response = client.post("/backup/import?reinstall_plugins=false", json=backup)
                self.assertEqual(response.status_code, 500)
                for name, data in before.items():
                    self.assertEqual((root / name).read_bytes(), data)
                if existed:
                    self.assertEqual((root / "carousels.json").read_bytes(), old_legacy)
                else:
                    self.assertFalse((root / "carousels.json").exists())

    def test_partial_snapshot_is_not_advertised_when_cleanup_also_fails(self):
        real_unlink = Path.unlink
        with self.environment() as (root, before, client, _, _, _):
            def copy(source, destination):
                Path(destination).write_bytes(b"PARTIAL")
                raise OSError("private synthetic source path should not be public")

            def unlink(path, *args, **kwargs):
                if ".pre-restore-" in path.name:
                    raise OSError("synthetic cleanup failure")
                return real_unlink(path, *args, **kwargs)

            with patch("src.backup.service.shutil.copy2", side_effect=copy), patch.object(Path, "unlink", unlink):
                response = client.post("/backup/import?reinstall_plugins=false", json=document())
            detail = response.json()["detail"]
            self.assertEqual(response.status_code, 500)
            self.assertEqual((root / "config.json").read_bytes(), before["config.json"])
            self.assertNotIn("private synthetic", detail)
            self.assertNotIn(".pre-restore-", detail)

    def test_failed_post_write_read_leaves_uncertain_file_and_recovers_others(self):
        real_read = Path.read_bytes
        with self.environment() as (root, before, client, _, _, _):
            reads = []

            def read(path):
                if path == root / "settings.json":
                    reads.append(True)
                    if len(reads) == 2:
                        raise OSError("synthetic uncertain outcome")
                return real_read(path)

            with patch.object(Path, "read_bytes", read):
                response = client.post("/backup/import?reinstall_plugins=false", json=document())
            self.assertEqual(response.status_code, 500)
            self.assertEqual((root / "config.json").read_bytes(), before["config.json"])
            self.assertNotEqual((root / "settings.json").read_bytes(), before["settings.json"])
            self.assertIn("recovery incomplete", response.json()["detail"].lower())
            self.assertIn("settings.json", response.json()["detail"])
            self.assertEqual(next(root.glob("settings.json.pre-restore-*")).read_bytes(), before["settings.json"])

    def test_recovered_failure_can_be_retried_without_losing_original_snapshots(self):
        real_replace = os.replace
        with self.environment() as (root, before, client, reload, _, _):
            def replace(source, destination):
                if Path(destination).name == "settings.json":
                    raise OSError("synthetic forward failure")
                return real_replace(source, destination)

            with patch("src.atomic_io.os.replace", side_effect=replace):
                failed = client.post("/backup/import?reinstall_plugins=false", json=document())
            snapshots = {path: path.read_bytes() for path in root.glob("*.pre-restore-*")}
            self.assertEqual(failed.status_code, 500)
            for name, content in before.items():
                self.assertEqual((root / name).read_bytes(), content)
            reload.assert_not_called()
            succeeded = client.post("/backup/import?reinstall_plugins=false", json=document())
            self.assertEqual(succeeded.status_code, 200)
            self.assertEqual(succeeded.json()["restored_files"], list(DATA_FILES))
            reload.assert_called_once()
            for name in DATA_FILES:
                self.assertEqual(json.loads((root / name).read_text()), document()["data"][name[:-5]])
            for path, content in snapshots.items():
                self.assertEqual(path.read_bytes(), content)
