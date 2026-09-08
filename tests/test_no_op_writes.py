"""Writes that change nothing (Pi audit, P8).

Two findings, both counted rather than timed:

* ``ConfigManager`` called ``_save_internal()`` unconditionally after the
  defaults merge, so every restart fsynced and renamed config.json — with an
  md5 identical to the one already on disk. The same shape applies to any PUT
  that stores the value already stored.
* The pre-init snapshot ``ConfigManager`` writes on a version change had no
  retention at all, unlike the pre-update snapshots it shares a directory and
  a filename shape with. 58 files / 1.3 MB observed on a live instance.

Size this honestly: it is tens of fsyncs per boot, not per hour. Nothing in
this codebase writes on a timer — 92 s of the real display loop performs zero
atomic writes and zero fsyncs — so this is not why an SD card dies. It is
still a write with no upside, which is the one class worth removing outright.

The non-vacuity half is what makes these tests worth having: a save that
skips too much is a lost setting, so every "does not write" test here has a
"still writes when it must" twin.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.atomic_io import write_json_atomic


@pytest.fixture
def fsyncs(monkeypatch):
    """Count every fsync the process performs."""
    counted: list[int] = []
    real = os.fsync

    def counting(fd):
        counted.append(fd)
        return real(fd)

    monkeypatch.setattr(os, "fsync", counting)
    return counted


# ---------------------------------------------------------------------------
# The primitive
# ---------------------------------------------------------------------------


def test_if_changed_skips_a_byte_identical_rewrite(tmp_path, fsyncs):
    target = tmp_path / "x.json"
    write_json_atomic(target, {"a": 1})
    fsyncs.clear()

    wrote = write_json_atomic(target, {"a": 1}, if_changed=True)

    assert wrote is False
    assert fsyncs == []
    assert json.loads(target.read_text()) == {"a": 1}


def test_if_changed_still_writes_a_real_change(tmp_path, fsyncs):
    target = tmp_path / "x.json"
    write_json_atomic(target, {"a": 1})
    fsyncs.clear()

    wrote = write_json_atomic(target, {"a": 2}, if_changed=True)

    assert wrote is True
    assert len(fsyncs) == 1
    assert json.loads(target.read_text()) == {"a": 2}


def test_if_changed_writes_when_the_target_does_not_exist(tmp_path):
    target = tmp_path / "nested" / "x.json"

    assert write_json_atomic(target, {"a": 1}, if_changed=True) is True
    assert json.loads(target.read_text()) == {"a": 1}


def test_if_changed_writes_when_the_target_cannot_be_read(tmp_path, monkeypatch):
    """The failure mode must be a needless write, never a skipped one."""
    target = tmp_path / "x.json"
    write_json_atomic(target, {"a": 1})

    def unreadable(*_args, **_kwargs):
        raise OSError("nope")

    monkeypatch.setattr(Path, "read_text", unreadable)

    assert write_json_atomic(target, {"a": 1}, if_changed=True) is True


def test_the_default_is_still_an_unconditional_write(tmp_path, fsyncs):
    target = tmp_path / "x.json"
    write_json_atomic(target, {"a": 1})
    fsyncs.clear()

    assert write_json_atomic(target, {"a": 1}) is True
    assert len(fsyncs) == 1


# ---------------------------------------------------------------------------
# ConfigManager boot
# ---------------------------------------------------------------------------


def _fresh_manager(config_path: Path):
    from src.config_manager import ConfigManager

    ConfigManager._instance = None
    return ConfigManager(config_path=str(config_path))


def test_a_restart_against_an_unchanged_config_does_not_rewrite_it(tmp_path, fsyncs):
    config_path = tmp_path / "config.json"
    _fresh_manager(config_path)
    before = config_path.read_bytes()
    fsyncs.clear()

    _fresh_manager(config_path)

    assert fsyncs == [], "the defaults merge rewrote a config it did not change"
    assert config_path.read_bytes() == before


def test_a_restart_that_does_change_the_config_still_writes_it(tmp_path, fsyncs):
    """Non-vacuity: a config missing a default key must still be filled in."""
    config_path = tmp_path / "config.json"
    _fresh_manager(config_path)
    stored = json.loads(config_path.read_text())
    stored.pop("general", None)
    config_path.write_text(json.dumps(stored, indent=2))
    fsyncs.clear()

    _fresh_manager(config_path)

    assert len(fsyncs) >= 1
    assert "general" in json.loads(config_path.read_text())


def test_a_no_op_save_still_bumps_the_config_generation(tmp_path):
    """Generation-keyed caches must not start trusting the disk write.

    ``config_generation`` says "what this process reads has moved". Tying it
    to whether the bytes on disk changed would let a render short-circuit keep
    serving a value the config manager no longer holds.
    """
    manager = _fresh_manager(tmp_path / "config.json")
    before = manager.config_generation

    manager._save_internal()

    assert manager.config_generation == before + 1


# ---------------------------------------------------------------------------
# JsonStore
# ---------------------------------------------------------------------------


def test_storing_the_value_already_stored_does_not_fsync(tmp_path, fsyncs):
    from src.storage.json_store import JsonStore

    store = JsonStore(tmp_path / "probe.json", current_schema_version=1)
    store.save({"a": 1})
    fsyncs.clear()

    store.save({"a": 1})

    assert fsyncs == []


def test_storing_a_new_value_still_fsyncs(tmp_path, fsyncs):
    from src.storage.json_store import JsonStore

    store = JsonStore(tmp_path / "probe.json", current_schema_version=1)
    store.save({"a": 1})
    fsyncs.clear()

    store.save({"a": 2})

    assert len(fsyncs) == 1
    assert json.loads((tmp_path / "probe.json").read_text())["a"] == 2


def test_a_skipped_save_still_updates_the_store_s_own_view(tmp_path):
    from src.storage.json_store import JsonStore

    path = tmp_path / "probe.json"
    store = JsonStore(path, current_schema_version=1)
    store.save({"a": 1})
    payload = {"a": 1}

    store.save(payload)

    assert store._data is payload


# ---------------------------------------------------------------------------
# Snapshot retention
# ---------------------------------------------------------------------------


def test_boot_snapshots_are_pruned_to_the_retention_limit(tmp_path):
    from src.system.update_service import SETTINGS_SNAPSHOT_RETENTION, prune_snapshot_dir

    for i in range(12):
        (tmp_path / f"pre-update-2026010{i % 10}T00000{i % 10}.000Z.json").write_text("{}")
    made = len(list(tmp_path.glob("pre-update-*.json")))

    deleted = prune_snapshot_dir(tmp_path)

    assert made > SETTINGS_SNAPSHOT_RETENTION
    assert deleted == made - SETTINGS_SNAPSHOT_RETENTION
    assert len(list(tmp_path.glob("pre-update-*.json"))) == SETTINGS_SNAPSHOT_RETENTION


def test_pruning_keeps_the_newest_snapshots(tmp_path):
    from src.system.update_service import prune_snapshot_dir

    names = [f"pre-update-2026010{i}T000000.000Z.json" for i in range(1, 8)]
    for name in names:
        (tmp_path / name).write_text("{}")

    prune_snapshot_dir(tmp_path)

    assert sorted(p.name for p in tmp_path.glob("pre-update-*.json")) == sorted(names[-5:])


def test_pruning_ignores_files_that_are_not_snapshots(tmp_path):
    from src.system.update_service import prune_snapshot_dir

    for i in range(1, 8):
        (tmp_path / f"pre-update-2026010{i}T000000.000Z.json").write_text("{}")
    (tmp_path / "pages.json").write_text("{}")
    (tmp_path / "pre-update-not-a-timestamp.json").write_text("{}")

    prune_snapshot_dir(tmp_path)

    assert (tmp_path / "pages.json").exists()
    assert (tmp_path / "pre-update-not-a-timestamp.json").exists()
