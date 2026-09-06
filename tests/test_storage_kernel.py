"""Storage kernel tests (#1848, absorbing #1759).

Three sections:

1. Kernel unit tests — ``src.atomic_io.write_json_atomic`` /
   ``write_text_atomic`` and ``src.storage.json_store.JsonStore`` (locking,
   load/save/mutate, schema-migration running, backup-before-first-migration,
   crash atomicity).

2. Golden on-disk format pins — each store loads a committed fixture, saves
   it back, and the file must be byte-identical. Written BEFORE the stores
   were rebuilt on the kernel; they passed on the old open-coded stores and
   must keep passing identically afterwards. The fixtures under
   ``tests/golden/storage/`` were produced by the pre-kernel code.

3. Concurrent-writer tests — added per-store as each store adopts the
   kernel; each reproduces the interleaving that used to lose an update or
   blow up on the shared process-scoped staging file.
"""

import json
import shutil
import stat
import threading
from pathlib import Path

import pytest

GOLDEN = Path(__file__).parent / "golden" / "storage"


# ═══════════════════════════════════════════════════════════════════════════
# 1. Kernel unit tests
# ═══════════════════════════════════════════════════════════════════════════


class TestWriteJsonAtomic:
    def test_writes_indent2_json(self, tmp_path):
        from src.atomic_io import write_json_atomic

        target = tmp_path / "x.json"
        write_json_atomic(target, {"a": 1})
        assert target.read_text() == json.dumps({"a": 1}, indent=2)

    def test_crash_mid_serialize_leaves_target_intact_and_no_staging_leak(self, tmp_path, monkeypatch):
        from src import atomic_io

        target = tmp_path / "x.json"
        atomic_io.write_json_atomic(target, {"a": 1})
        original = target.read_bytes()

        def crashing_dump(obj, fh, *args, **kwargs):
            fh.write('{"a": ')
            fh.flush()
            raise OSError("simulated crash mid-write")

        monkeypatch.setattr(atomic_io.json, "dump", crashing_dump)
        with pytest.raises(OSError):
            atomic_io.write_json_atomic(target, {"a": 2})

        assert target.read_bytes() == original
        assert not list(tmp_path.glob("x.json*.tmp")), "partial staging file leaked"

    def test_orphaned_staging_file_from_a_crashed_writer_never_corrupts_target(self, tmp_path):
        from src.atomic_io import staging_path, write_json_atomic

        target = tmp_path / "x.json"
        write_json_atomic(target, {"a": 1})
        staging_path(target).write_text("{ truncated by a SIGKILLed writer")

        write_json_atomic(target, {"a": 2})
        assert json.loads(target.read_text()) == {"a": 2}

    def test_private_mode_creates_owner_only_file(self, tmp_path):
        from src.atomic_io import write_json_atomic

        target = tmp_path / "secrets.json"
        write_json_atomic(target, {"key": "test_key_123"}, private=True)
        mode = stat.S_IMODE(target.stat().st_mode)
        assert mode & (stat.S_IRWXG | stat.S_IRWXO) == 0, f"file is group/world accessible: {mode:o}"

    def test_write_text_atomic_replaces_content_atomically(self, tmp_path):
        from src.atomic_io import write_text_atomic

        target = tmp_path / "snap.json"
        write_text_atomic(target, '{"doc": 1}')
        assert target.read_text() == '{"doc": 1}'
        assert not list(tmp_path.glob("snap.json*.tmp"))


class TestJsonStoreBasics:
    def _store(self, path, **kw):
        from src.storage.json_store import JsonStore

        return JsonStore(path, **kw)

    def test_bare_filename_resolves_into_the_data_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FIESTABOARD_DATA_DIR", str(tmp_path))
        store = self._store("things.json")
        assert store.path == tmp_path / "things.json"

    def test_explicit_path_wins_over_data_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FIESTABOARD_DATA_DIR", str(tmp_path / "elsewhere"))
        explicit = tmp_path / "here" / "things.json"
        store = self._store(explicit)
        assert store.path == explicit

    def test_load_returns_none_when_file_missing(self, tmp_path):
        store = self._store(tmp_path / "missing.json")
        assert store.load() is None

    def test_save_then_load_round_trips(self, tmp_path):
        store = self._store(tmp_path / "x.json")
        store.save({"k": "v"})
        assert store.load() == {"k": "v"}

    def test_save_stamps_schema_version_on_versioned_dict_payloads(self, tmp_path):
        store = self._store(tmp_path / "x.json", current_schema_version=3)
        store.save({"items": []})
        assert json.loads((tmp_path / "x.json").read_text())["schema_version"] == 3

    def test_save_does_not_invent_schema_version_on_unversioned_stores(self, tmp_path):
        store = self._store(tmp_path / "x.json")
        store.save({"items": []})
        assert "schema_version" not in json.loads((tmp_path / "x.json").read_text())

    def test_lock_is_reentrant_and_shared_with_composers(self, tmp_path):
        store = self._store(tmp_path / "x.json")
        with store.lock:
            with store.lock:  # re-entrant
                store.save({"k": 1})
        assert store.load() == {"k": 1}


class TestJsonStoreMigrations:
    def _versioned_store(self, path, migrations, version=2):
        from src.storage.json_store import JsonStore

        return JsonStore(path, current_schema_version=version, migrations=migrations)

    def test_pending_migrations_run_in_order_and_version_bumps_once(self, tmp_path):
        calls = []

        def m1(data):
            calls.append(1)
            data["a"] = True
            return 1

        def m2(data):
            calls.append(2)
            data["b"] = True
            return 1

        path = tmp_path / "x.json"
        path.write_text(json.dumps({"schema_version": 0, "items": []}))
        store = self._versioned_store(path, [(1, m1), (2, m2)])

        data = store.load()
        assert calls == [1, 2]
        assert data["a"] and data["b"]
        assert data["schema_version"] == 2
        assert store.migrated is True

    def test_migrations_at_current_version_do_not_run(self, tmp_path):
        def boom(data):
            raise AssertionError("migration ran on an up-to-date file")

        path = tmp_path / "x.json"
        path.write_text(json.dumps({"schema_version": 2, "items": []}))
        store = self._versioned_store(path, [(1, boom), (2, boom)])
        store.load()
        assert store.migrated is False

    def test_only_migrations_newer_than_file_version_run(self, tmp_path):
        calls = []
        path = tmp_path / "x.json"
        path.write_text(json.dumps({"schema_version": 1}))
        store = self._versioned_store(path, [(1, lambda d: calls.append(1)), (2, lambda d: calls.append(2) or 0)])
        store.load()
        assert calls == [2]

    def test_backup_written_before_first_migration_and_only_once(self, tmp_path):
        path = tmp_path / "x.json"
        original = json.dumps({"schema_version": 0, "items": ["keep"]})
        path.write_text(original)
        store = self._versioned_store(path, [(1, lambda d: 0), (2, lambda d: 0)])
        store.load()

        backup = tmp_path / "x.json.v0_backup"
        assert backup.exists(), "no pre-migration backup written"
        assert backup.read_text() == original, "backup must hold the PRE-migration bytes"

        # A second store at the same version must not overwrite the backup.
        backup_bytes = backup.read_bytes()
        path.write_text(json.dumps({"schema_version": 0, "items": ["changed"]}))
        self._versioned_store(path, [(1, lambda d: 0), (2, lambda d: 0)]).load()
        assert backup.read_bytes() == backup_bytes

    def test_load_does_not_write_migrated_data_itself(self, tmp_path):
        """The domain owns the resave (pages re-serializes via its models);
        the kernel only flags that one is needed."""
        path = tmp_path / "x.json"
        original = json.dumps({"schema_version": 0})
        path.write_text(original)
        store = self._versioned_store(path, [(1, lambda d: 0), (2, lambda d: 0)])
        store.load()
        assert path.read_text() == original


class TestJsonStoreMutate:
    def test_mutate_is_a_locked_read_modify_write(self, tmp_path):
        from src.storage.json_store import JsonStore

        store = JsonStore(tmp_path / "x.json")
        store.save({"n": 0})

        import time

        def bump(data):
            n = data.get("n", 0)
            time.sleep(0.001)  # widen the stale-read window
            data["n"] = n + 1
            return data["n"]

        threads = [threading.Thread(target=lambda: [store.mutate(bump) for _ in range(25)]) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert store.load() == {"n": 100}, "concurrent mutate() lost updates"

    def test_mutate_on_missing_file_starts_from_empty_dict(self, tmp_path):
        from src.storage.json_store import JsonStore

        store = JsonStore(tmp_path / "x.json")
        result = store.mutate(lambda d: d.setdefault("created", True))
        assert result is True
        assert json.loads((tmp_path / "x.json").read_text()) == {"created": True}

    def test_concurrent_saves_never_collide_on_the_staging_file(self, tmp_path):
        """Two same-process threads saving at once share one PID-scoped
        staging name; without the store lock the second rename dies ENOENT."""
        from src.storage.json_store import JsonStore

        store = JsonStore(tmp_path / "x.json")
        errors = []

        def save_many(tag):
            try:
                for i in range(50):
                    store.save({"tag": tag, "i": i})
            except Exception as exc:  # pragma: no cover - the failure we assert against
                errors.append(exc)

        threads = [threading.Thread(target=save_many, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert not list(tmp_path.glob("x.json*.tmp"))


# ═══════════════════════════════════════════════════════════════════════════
# 2. Golden on-disk format pins (written before the kernel rework)
# ═══════════════════════════════════════════════════════════════════════════


def _pin(tmp_path, fixture_name):
    src = GOLDEN / fixture_name
    dst = tmp_path / fixture_name
    shutil.copyfile(src, dst)
    return dst, src.read_bytes()


class TestGoldenOnDiskFormat:
    """Load a committed fixture, save it back, byte-identical. Pins the
    on-disk format across the kernel rework — any drift is a regression."""

    def test_pages_json_round_trips_byte_identical(self, tmp_path):
        from src.pages.storage import PageStorage

        path, golden = _pin(tmp_path, "pages.json")
        PageStorage(storage_file=str(path))._save()
        assert path.read_bytes() == golden

    def test_schedules_json_round_trips_byte_identical(self, tmp_path):
        from src.schedules.storage import ScheduleStorage

        path, golden = _pin(tmp_path, "schedules.json")
        ScheduleStorage(storage_file=str(path))._save()
        assert path.read_bytes() == golden

    def test_collections_json_round_trips_byte_identical(self, tmp_path):
        from src.collections.storage import CollectionStorage

        path, golden = _pin(tmp_path, "collections.json")
        CollectionStorage(storage_file=str(path))._save()
        assert path.read_bytes() == golden

    def test_panels_json_round_trips_byte_identical(self, tmp_path):
        from src.panels.storage import PanelStorage

        path, golden = _pin(tmp_path, "panels.json")
        PanelStorage(storage_file=str(path))._save()
        assert path.read_bytes() == golden

    def test_settings_json_round_trips_byte_identical(self, tmp_path):
        from src.settings.service import SettingsService

        path, golden = _pin(tmp_path, "settings.json")
        SettingsService(settings_file=str(path))._save_to_file()
        assert path.read_bytes() == golden
