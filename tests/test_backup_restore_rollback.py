"""A restore must not overwrite a file it could not back up (Phase 2, Task 10d).

``_write_json_with_backup`` copied the live file aside, and when that copy
raised ``OSError`` it logged a warning and **fell through to overwrite the
live file anyway**. ``import_from_dict`` then returned
``{"status": "success", "pre_restore_backup_suffix": ...}`` — advertising a
rollback copy that might not exist, or exist truncated. The user's only
escape hatch from a bad restore was reported as present when it was not.

Two defects, both pinned here:
  (a) the copy failure is not propagated — the overwrite happens regardless;
  (b) the suffix is emitted unconditionally rather than derived from copies
      that actually succeeded.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.backup.service import BACKUP_FILE_MARKER, BACKUP_SCHEMA_VERSION, BackupError, BackupService


def _backup_doc(data: dict) -> dict:
    return {
        BACKUP_FILE_MARKER: True,
        "schema_version": BACKUP_SCHEMA_VERSION,
        "data": data,
    }


class TestBackupCopyFailureAbortsTheRestore:
    def test_live_file_is_not_overwritten_when_its_backup_copy_fails(self, tmp_path: Path):
        (tmp_path / "config.json").write_text(json.dumps({"marker": "OLD"}))
        service = BackupService(data_dir=tmp_path)

        with (
            patch("src.backup.service._reload_services", return_value=[]),
            patch("src.backup.service.shutil.copy2", side_effect=OSError(28, "No space left on device")),
            pytest.raises(BackupError),
        ):
            service.import_from_dict(_backup_doc({"config": {"marker": "NEW"}}), reinstall_plugins=False)

        assert json.loads((tmp_path / "config.json").read_text()) == {"marker": "OLD"}

    def test_a_partial_backup_copy_is_removed_rather_than_left_behind(self, tmp_path: Path):
        """A truncated rollback copy is worse than none: it looks usable."""
        (tmp_path / "config.json").write_text(json.dumps({"marker": "OLD"}))
        service = BackupService(data_dir=tmp_path)

        def half_copy(src, dst, *args, **kwargs):
            Path(dst).write_text('{"marker": "OL')  # truncated
            raise OSError(28, "No space left on device")

        with (
            patch("src.backup.service._reload_services", return_value=[]),
            patch("src.backup.service.shutil.copy2", side_effect=half_copy),
            pytest.raises(BackupError),
        ):
            service.import_from_dict(_backup_doc({"config": {"marker": "NEW"}}), reinstall_plugins=False)

        assert list(tmp_path.glob("config.json.pre-restore-*")) == []


class TestSuffixReflectsRealCopies:
    def test_no_suffix_is_advertised_when_nothing_was_backed_up(self, tmp_path: Path):
        """A restore into an empty data dir overwrites nothing, so there is no
        rollback copy to point the user at."""
        service = BackupService(data_dir=tmp_path)

        with patch("src.backup.service._reload_services", return_value=[]):
            result = service.import_from_dict(_backup_doc({"config": {"marker": "NEW"}}), reinstall_plugins=False)

        assert result["restored_files"] == ["config.json"]
        assert result["pre_restore_backup_suffix"] == ""
        assert result["pre_restore_backup_files"] == []

    def test_suffix_and_file_list_name_only_files_actually_copied(self, tmp_path: Path):
        (tmp_path / "config.json").write_text(json.dumps({"marker": "OLD"}))
        service = BackupService(data_dir=tmp_path)

        with patch("src.backup.service._reload_services", return_value=[]):
            result = service.import_from_dict(
                _backup_doc({"config": {"marker": "NEW"}, "pages": {"pages": []}}),
                reinstall_plugins=False,
            )

        # pages.json did not exist, so it has no rollback copy; config.json does.
        assert result["pre_restore_backup_files"] == ["config.json"]
        suffix = result["pre_restore_backup_suffix"]
        assert (tmp_path / f"config.json{suffix}").exists()
        assert not (tmp_path / f"pages.json{suffix}").exists()


class TestEndpointMapping:
    """A refused write is a server failure, not a bad backup file."""

    def test_import_endpoint_reports_5xx_when_the_pre_restore_copy_fails(self, tmp_path: Path):
        from fastapi.testclient import TestClient

        from src.api_server import app

        (tmp_path / "config.json").write_text(json.dumps({"marker": "OLD"}))
        service = BackupService(data_dir=tmp_path)

        with (
            patch("src.backup.get_backup_service", return_value=service),
            patch("src.backup.service._reload_services", return_value=[]),
            patch("src.backup.service.shutil.copy2", side_effect=OSError(28, "No space left on device")),
        ):
            response = TestClient(app).post(
                "/backup/import",
                params={"reinstall_plugins": "false"},
                json=_backup_doc({"config": {"marker": "NEW"}}),
            )

        # 400 would blame the operator's backup file for a full disk.
        assert response.status_code == 500
        assert "not overwritten" in response.json()["detail"]
        assert json.loads((tmp_path / "config.json").read_text()) == {"marker": "OLD"}

    def test_a_genuinely_bad_backup_file_is_still_a_400(self, tmp_path: Path):
        from fastapi.testclient import TestClient

        from src.api_server import app

        with patch("src.backup.get_backup_service", return_value=BackupService(data_dir=tmp_path)):
            response = TestClient(app).post("/backup/import", json={"not": "a backup"})

        assert response.status_code == 400
