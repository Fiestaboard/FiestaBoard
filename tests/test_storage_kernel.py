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

import contextlib
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


class TestJsonStoreRefusesAFutureSchema:
    """A file written by a NEWER build must not be read as if it were ours.

    Downgrading is now a supported path (the beta release channel), and a
    downgrade lands an older binary on a data directory a newer one already
    migrated. Before this guard every store took the same shape:

        if file_version >= CURRENT_SCHEMA_VERSION: skip migrations

    so a v3 file loaded into a v2 build fell straight through and was read
    as v2 — and the first ``save()`` then stamped ``schema_version: 2`` back
    onto v3-shaped content, destroying the evidence. Silent misreading, then
    silent corruption.

    Loud refusal is the contract: ``load()`` already documents that read
    errors propagate and the domain store decides whether a broken file is
    fatal.
    """

    def _store(self, path, version=2):
        from src.storage.json_store import JsonStore

        return JsonStore(path, current_schema_version=version, label="widgets")

    def test_load_refuses_a_file_from_a_newer_build(self, tmp_path):
        from src.storage.json_store import SchemaTooNewError

        path = tmp_path / "x.json"
        path.write_text(json.dumps({"schema_version": 3, "items": ["from the future"]}))

        with pytest.raises(SchemaTooNewError) as excinfo:
            self._store(path, version=2).load()

        message = str(excinfo.value)
        assert "widgets" in message, "the error must name which store refused"
        assert "3" in message and "2" in message, "the error must name both versions"

    def test_the_refused_file_is_left_exactly_as_it_was(self, tmp_path):
        """The newer file is the user's only copy of that data."""
        from src.storage.json_store import SchemaTooNewError

        path = tmp_path / "x.json"
        original = json.dumps({"schema_version": 3, "items": ["from the future"]})
        path.write_text(original)

        with contextlib.suppress(SchemaTooNewError):
            self._store(path, version=2).load()

        assert path.read_text() == original
        assert not list(tmp_path.glob("*_backup")), "a refused load must not take a migration backup"

    def test_a_refused_store_will_not_overwrite_the_newer_file(self, tmp_path):
        """The dangerous move is the SAVE after the failed load, not the load."""
        from src.storage.json_store import SchemaTooNewError

        path = tmp_path / "x.json"
        original = json.dumps({"schema_version": 3, "items": ["from the future"]})
        path.write_text(original)
        store = self._store(path, version=2)

        with contextlib.suppress(SchemaTooNewError):
            store.load()
        with pytest.raises(SchemaTooNewError):
            store.save({"items": []})

        assert path.read_text() == original

    def test_an_equal_version_still_loads(self, tmp_path):
        """The guard must fire on strictly-newer only, never on equal."""
        path = tmp_path / "x.json"
        path.write_text(json.dumps({"schema_version": 2, "items": ["ours"]}))
        assert self._store(path, version=2).load()["items"] == ["ours"]

    def test_an_unversioned_store_reads_anything(self, tmp_path):
        """current_schema_version=0 disables versioning entirely."""
        path = tmp_path / "x.json"
        path.write_text(json.dumps({"schema_version": 99, "items": ["ok"]}))
        assert self._store(path, version=0).load()["items"] == ["ok"]


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


# ═══════════════════════════════════════════════════════════════════════════
# 3. Concurrent writers
# ═══════════════════════════════════════════════════════════════════════════


def _force_write_overlap(monkeypatch):
    """Patch ``json.dump`` so two concurrent saves are forced to overlap.

    Both writers rendezvous on a barrier inside the serialisation step; with
    no store lock they then race the shared PID-scoped staging file (second
    ``os.replace`` dies ENOENT, or one write lands on the already-renamed
    inode). With the store lock the second writer never reaches ``json.dump``
    until the first is done, the barrier times out, and both proceed serially.
    """
    barrier = threading.Barrier(2, timeout=0.3)
    real_dump = json.dump

    def overlapping_dump(obj, fh, *args, **kwargs):
        with contextlib.suppress(threading.BrokenBarrierError):
            barrier.wait()
        return real_dump(obj, fh, *args, **kwargs)

    monkeypatch.setattr(json, "dump", overlapping_dump)


def _run_pair(fn_a, fn_b):
    """Run two callables on two threads; return the exceptions they raised."""
    errors = []

    def wrap(fn):
        try:
            fn()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=wrap, args=(f,)) for f in (fn_a, fn_b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return errors


class TestConcurrentWriters:
    def test_pages_two_threads_updating_disjoint_pages_both_survive(self, tmp_path, monkeypatch):
        from src.pages.models import Page
        from src.pages.storage import PageStorage

        storage = PageStorage(storage_file=str(tmp_path / "pages.json"))
        for pid in ("p1", "p2"):
            storage.create(Page(id=pid, name=pid.upper(), type="template", template=["x", "", "", "", "", ""]))

        _force_write_overlap(monkeypatch)
        errors = _run_pair(
            lambda: storage.update("p1", {"name": "First Updated"}),
            lambda: storage.update("p2", {"name": "Second Updated"}),
        )
        monkeypatch.undo()

        assert errors == []
        reloaded = PageStorage(storage_file=str(tmp_path / "pages.json"))
        assert reloaded.get("p1").name == "First Updated"
        assert reloaded.get("p2").name == "Second Updated"

    def test_schedules_two_threads_updating_disjoint_schedules_both_survive(self, tmp_path, monkeypatch):
        from src.schedules.models import ScheduleEntry
        from src.schedules.storage import ScheduleStorage

        storage = ScheduleStorage(storage_file=str(tmp_path / "schedules.json"))
        for sid in ("s1", "s2"):
            storage.create(ScheduleEntry(id=sid, page_id="p1", start_time="08:00", end_time="10:00", day_pattern="all"))

        _force_write_overlap(monkeypatch)
        errors = _run_pair(
            lambda: storage.update("s1", {"start_time": "09:00"}),
            lambda: storage.update("s2", {"start_time": "11:00"}),
        )
        monkeypatch.undo()

        assert errors == []
        reloaded = ScheduleStorage(storage_file=str(tmp_path / "schedules.json"))
        assert reloaded.get("s1").start_time == "09:00"
        assert reloaded.get("s2").start_time == "11:00"

    def test_collections_two_threads_updating_disjoint_collections_both_survive(self, tmp_path, monkeypatch):
        from src.collections.models import Collection
        from src.collections.storage import CollectionStorage

        storage = CollectionStorage(storage_file=str(tmp_path / "collections.json"))
        for cid in ("collection:c1", "collection:c2"):
            storage.create(Collection(id=cid, name=cid[-2:], page_ids=["p1"]))

        _force_write_overlap(monkeypatch)
        errors = _run_pair(
            lambda: storage.update("collection:c1", {"name": "First Updated"}),
            lambda: storage.update("collection:c2", {"name": "Second Updated"}),
        )
        monkeypatch.undo()

        assert errors == []
        reloaded = CollectionStorage(storage_file=str(tmp_path / "collections.json"))
        assert reloaded.get("collection:c1").name == "First Updated"
        assert reloaded.get("collection:c2").name == "Second Updated"

    def test_panels_two_threads_updating_disjoint_panels_both_survive(self, tmp_path, monkeypatch):
        from src.panels.models import Panel
        from src.panels.storage import PanelStorage

        storage = PanelStorage(storage_file=str(tmp_path / "panels.json"))
        for pid in ("panel-1", "panel-2"):
            storage.create(Panel(id=pid, name=pid, board_id="board-1"))

        _force_write_overlap(monkeypatch)
        errors = _run_pair(
            lambda: storage.update("panel-1", {"name": "First Updated"}),
            lambda: storage.update("panel-2", {"name": "Second Updated"}),
        )
        monkeypatch.undo()

        assert errors == []
        reloaded = PanelStorage(storage_file=str(tmp_path / "panels.json"))
        assert reloaded.get("panel-1").name == "First Updated"
        assert reloaded.get("panel-2").name == "Second Updated"

    def test_settings_two_concurrent_puts_to_different_sections_both_survive(self, tmp_path, monkeypatch):
        """The #1848 headline bug: SettingsService rewrites ALL sections from
        memory on every mutation with no lock, so a PUT whose save is paused
        mid-serialisation gets lapped by a second PUT — the slow writer then
        finishes onto the already-renamed inode and overwrites the fast
        writer's section with its own stale snapshot (its rename dies ENOENT,
        which ``_save_to_file`` swallows, so nobody even notices). The
        interleaving is forced deterministically: writer A blocks inside
        ``json.dump`` until writer B's whole PUT has completed (with a
        timeout so the post-fix lock, which makes B wait for A, cannot
        deadlock). Written before the fix — the pre-fix failure is recorded
        verbatim in .fail-first-1848.txt."""
        from src.settings.service import SettingsService

        path = tmp_path / "settings.json"
        svc = SettingsService(settings_file=str(path))
        svc._save_to_file()

        a_in_dump = threading.Event()
        b_done = threading.Event()
        real_dump = json.dump
        first_call = threading.Event()

        def sequenced_dump(obj, fh, *args, **kwargs):
            if not first_call.is_set():
                first_call.set()
                a_in_dump.set()
                b_done.wait(timeout=0.5)  # times out post-fix (B waits on the lock)
            return real_dump(obj, fh, *args, **kwargs)

        monkeypatch.setattr(json, "dump", sequenced_dump)

        def writer_a():
            svc.update_display_settings({"reduce_motion": True})

        def writer_b():
            a_in_dump.wait(timeout=1.0)
            svc.update_location_settings({"latitude": 40.7128, "longitude": -74.0060})
            b_done.set()

        errors = _run_pair(writer_a, writer_b)
        monkeypatch.undo()

        assert errors == []
        on_disk = json.loads(path.read_text())
        assert on_disk["display"]["reduce_motion"] is True, "display PUT lost"
        assert on_disk["location"]["latitude"] == 40.7128, "location PUT lost"

    @pytest.mark.parametrize(
        "mutate",
        [
            pytest.param(lambda svc: svc.set_active_page_id("page-1"), id="set_active_page_id"),
            pytest.param(lambda svc: svc.set_schedule_enabled(True), id="set_schedule_enabled"),
        ],
    )
    def test_per_board_setters_hold_the_store_lock_for_the_whole_body(self, tmp_path, monkeypatch, mutate):
        """The two per-board setters mutate+save under the JsonStore RLock.

        Both carried a second, private ``_per_board_write_lock`` described in
        the source as a "stopgap until #1848 gives SettingsService real
        thread-safety across every mutator". #1848 landed and put ``@_locked``
        on both, so the store RLock is held from the first line of the body
        through ``_save_to_file`` — which is what the private lock was for.

        This pins that claim rather than arguing it: with the body paused on
        its way into ``_save_to_file``, no other thread can take the store
        lock. It passes with the private lock present and must keep passing
        with it gone; it fails if ``@_locked`` is ever dropped from either
        setter.

        (The obvious alternative — parameterising the timing race in
        ``test_settings_two_concurrent_puts_to_different_sections_both_survive``
        onto this pair — cannot discriminate: ``_save_to_file`` is itself
        ``@_locked``, so that interleaving is already impossible with or
        without the setter locks.)
        """
        from src.settings.service import SettingsService

        svc = SettingsService(settings_file=str(tmp_path / "settings.json"))

        inside_body = threading.Event()
        may_finish = threading.Event()
        # Bound to the class *after* @_locked, so this hook runs before
        # _save_to_file's own lock acquisition: whatever holds the store lock
        # at this point was taken by the setter, not by the save.
        decorated_save = SettingsService._save_to_file

        def paused_save(self):
            inside_body.set()
            may_finish.wait(timeout=2.0)
            return decorated_save(self)

        monkeypatch.setattr(SettingsService, "_save_to_file", paused_save)

        errors: list[Exception] = []

        def writer():
            try:
                mutate(svc)
            except Exception as exc:  # pragma: no cover - surfaced by the assert
                errors.append(exc)

        thread = threading.Thread(target=writer)
        thread.start()
        try:
            assert inside_body.wait(timeout=2.0), "setter never reached _save_to_file"
            acquired = svc._store.lock.acquire(blocking=False)
            if acquired:
                svc._store.lock.release()
        finally:
            may_finish.set()
            thread.join(timeout=5.0)

        assert not thread.is_alive()
        assert errors == []
        assert not acquired, "another thread took the store lock mid-mutation: the setter body is not serialised"
