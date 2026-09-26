"""An empty snapshot must not be written, and must never evict a real one.

Observed on a real FiestaPi mid-channel-switch. `GET /system/update/status`
listed five snapshots taken in three minutes, two of them **zero bytes**:

    pre-update-20260913T234217.566Z.json   61764 bytes
    pre-update-20260913T234120.463Z.json   61776 bytes
    pre-update-20260913T234016.190Z.json       0 bytes   <-
    pre-update-20260913T234000.955Z.json       0 bytes   <-
    pre-update-20260913T233900.441Z.json   61776 bytes

The empty pair were taken while the box was briefly running an 8.x build
against data a 9.x build had migrated. The forward-compat guard from #1961
did its job and refused to read the future-schema settings, so
``BackupService.export_to_json()`` had nothing to export — and the snapshot
was written anyway.

Two things then go wrong, and the second is the dangerous one:

1. The snapshot is offered in the UI as a restore point that would restore
   nothing.
2. ``_prune_settings_snapshots`` keeps the five *newest* files regardless of
   content, so each empty snapshot evicts a real one. Enough churn and every
   genuine restore point is gone — which is precisely the situation the
   snapshot exists to protect against.

A snapshot that cannot be produced is already a supported outcome:
``_take_settings_snapshot`` returns ``None`` and every caller proceeds. This
makes "produced nothing" take that same path instead of writing the nothing
to disk.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

import src.system.update_service as update_service


@pytest.fixture
def snapshot_dir(tmp_path, monkeypatch):
    d = tmp_path / "update-backups"
    d.mkdir(parents=True)
    monkeypatch.setattr(update_service, "_settings_snapshot_dir", lambda: d)
    return d


def _export(value):
    """Patch what BackupService hands back to the snapshot writer."""

    class _Svc:
        def export_to_json(self):
            return value

    return patch("src.backup.service.get_backup_service", return_value=_Svc())


class TestAnEmptyExportIsNotWritten:
    @pytest.mark.parametrize(
        ("document", "why"),
        [
            ("", "empty string"),
            ("   \n", "whitespace only"),
            ("{}", "an object with nothing in it"),
            ("null", "JSON null"),
        ],
    )
    def test_it_returns_none_instead_of_writing(self, snapshot_dir, document, why):
        with _export(document):
            assert update_service._take_settings_snapshot() is None, (
                f"a snapshot containing {why} was reported as a usable restore point"
            )
        assert list(snapshot_dir.glob("*.json")) == [], f"wrote a snapshot containing {why}"

    def test_the_zero_byte_case_that_was_observed(self, snapshot_dir):
        """The exact shape seen on the Pi: export yields nothing."""
        with _export(""):
            update_service._take_settings_snapshot()
        assert not [p for p in snapshot_dir.glob("*.json") if p.stat().st_size == 0]


class TestARealExportStillWorks:
    """The guard must not cost us the snapshots that matter."""

    def test_a_populated_export_is_written(self, snapshot_dir):
        with _export(json.dumps({"settings": {"a": 1}})):
            meta = update_service._take_settings_snapshot()
        assert meta is not None
        assert meta["bytes"] > 0
        assert len(list(snapshot_dir.glob("*.json"))) == 1

    def test_the_image_metadata_is_still_spliced_in(self, snapshot_dir):
        with _export(json.dumps({"settings": {"a": 1}})):
            meta = update_service._take_settings_snapshot("sha256:abc", "repo:tag")
        doc = json.loads((snapshot_dir / meta["name"]).read_text())
        assert doc["_fiestaupdater"]["previous_digest"] == "sha256:abc"
        assert doc["_fiestaupdater"]["previous_image"] == "repo:tag"


class TestAnEmptyExportNeverEvictsARealSnapshot:
    """The severe half: churn must not erode the restore points."""

    def test_real_snapshots_survive_a_burst_of_empty_ones(self, snapshot_dir):
        good = json.dumps({"settings": {"a": 1}})
        for _ in range(update_service.SETTINGS_SNAPSHOT_RETENTION):
            with _export(good):
                assert update_service._take_settings_snapshot() is not None

        before = {p.name for p in snapshot_dir.glob("*.json")}
        assert len(before) == update_service.SETTINGS_SNAPSHOT_RETENTION

        # The re-assert loop on the Pi produced one of these per recreation.
        for _ in range(10):
            with _export(""):
                update_service._take_settings_snapshot()

        after = {p.name for p in snapshot_dir.glob("*.json")}
        assert after == before, (
            "empty snapshots pruned real ones; after enough channel churn the "
            "user has five restore points that all restore nothing"
        )
