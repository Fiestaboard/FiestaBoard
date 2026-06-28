"""Tests for collections module (models, storage, service, API).

Covers both selection modes:
- ``time`` mode: classic time-sliced carousel rotation. Tests preserve the
  original carousel coverage (cycling, determinism, interval accuracy).
- ``variable`` mode: expression-driven rule evaluation against template
  context. Tests cover order, default fallback, error-on-rule isolation,
  and end-to-end resolution against the real expression evaluator.
"""

import math

import pytest
from pydantic import ValidationError

from src.collections.models import (
    COLLECTION_ID_PREFIX,
    Collection,
    CollectionCreate,
    CollectionUpdate,
    RandomModeConfig,
    TimeModeConfig,
    VariableModeConfig,
    VariableRule,
    extract_collection_uuid,
    is_collection_id,
    make_collection_id,
)
from src.collections.service import CollectionService
from src.collections.storage import (
    CollectionStorage,
    import_legacy_carousels,
)

# =============================================================================
# Model Tests
# =============================================================================


class TestCollectionModels:
    """Tests for Collection and related models."""

    def test_make_collection_id(self):
        cid = make_collection_id()
        assert cid.startswith(COLLECTION_ID_PREFIX)

    def test_is_collection_id_true(self):
        assert is_collection_id("collection:abc-123")

    def test_is_collection_id_false_for_page(self):
        assert not is_collection_id("abc-123")
        assert not is_collection_id("")

    def test_is_collection_id_none(self):
        assert not is_collection_id(None)

    def test_extract_collection_uuid(self):
        assert extract_collection_uuid("collection:abc-123") == "abc-123"

    def test_collection_valid(self):
        c = Collection(name="Test", page_ids=["p1", "p2"])
        assert c.is_valid()
        assert c.validate_config() == []

    def test_collection_empty_pages_invalid(self):
        c = Collection(name="Empty", page_ids=["p1"])
        c.page_ids = []
        errors = c.validate_config()
        assert any("at least one" in e.lower() for e in errors)

    def test_collection_duplicate_pages_invalid(self):
        c = Collection(name="Dup", page_ids=["p1", "p1"])
        errors = c.validate_config()
        assert any("duplicate" in e.lower() for e in errors)

    def test_collection_nested_collection_invalid(self):
        c = Collection(name="Nested", page_ids=["p1", "collection:nested-id"])
        errors = c.validate_config()
        assert any("collection" in e.lower() for e in errors)

    def test_collection_id_prefix(self):
        c = Collection(name="Auto", page_ids=["p1"])
        assert c.id.startswith(COLLECTION_ID_PREFIX)

    def test_default_selection_mode_is_time(self):
        c = Collection(name="Default", page_ids=["p1"])
        assert c.selection_mode == "time"
        assert c.time.interval_seconds == 30
        assert c.variable is None

    def test_time_interval_range(self):
        with pytest.raises(ValidationError):
            Collection(
                name="Too Low",
                page_ids=["p1"],
                time=TimeModeConfig(interval_seconds=1),
            )
        with pytest.raises(ValidationError):
            Collection(
                name="Too High",
                page_ids=["p1"],
                time=TimeModeConfig(interval_seconds=7200),
            )

    # --- Time-mode cycling ---------------------------------------------------

    def test_current_page_index_wraps(self):
        c = Collection(
            name="Cycle",
            page_ids=["a", "b", "c"],
            time=TimeModeConfig(interval_seconds=10),
        )
        assert c.current_page_index_time(0) == 0
        assert c.current_page_index_time(10) == 1
        assert c.current_page_index_time(20) == 2
        assert c.current_page_index_time(30) == 0

    def test_current_page_id_time(self):
        c = Collection(
            name="Cycle",
            page_ids=["a", "b", "c"],
            time=TimeModeConfig(interval_seconds=10),
        )
        assert c.current_page_id_time(0) == "a"
        assert c.current_page_id_time(15) == "b"
        assert c.current_page_id_time(25) == "c"
        assert c.current_page_id_time(35) == "a"

    def test_current_page_id_time_single_page(self):
        c = Collection(name="Single", page_ids=["only"])
        assert c.current_page_id_time(0) == "only"
        assert c.current_page_id_time(999) == "only"

    def test_current_page_id_time_deterministic(self):
        c = Collection(
            name="Det",
            page_ids=["a", "b"],
            time=TimeModeConfig(interval_seconds=5),
        )
        assert c.current_page_id_time(12345.0) == c.current_page_id_time(12345.0)

    def test_transition_exactly_at_boundary(self):
        c = Collection(
            name="Boundary",
            page_ids=["a", "b", "c"],
            time=TimeModeConfig(interval_seconds=10),
        )
        assert c.current_page_id_time(9.999) == "a"
        assert c.current_page_id_time(10.0) == "b"
        assert c.current_page_id_time(10.001) == "b"

    def test_each_page_gets_exact_interval(self):
        c = Collection(
            name="Exact",
            page_ids=["a", "b", "c"],
            time=TimeModeConfig(interval_seconds=15),
        )
        for page_idx in range(3):
            start = page_idx * 15
            end = (page_idx + 1) * 15
            expected = c.page_ids[page_idx]
            assert c.current_page_id_time(float(start)) == expected
            assert c.current_page_id_time(end - 0.001) == expected
            assert c.current_page_id_time(float(end)) != expected

    def test_full_cycle_returns_to_first_page(self):
        pages = ["p1", "p2", "p3", "p4"]
        c = Collection(
            name="FullCycle",
            page_ids=pages,
            time=TimeModeConfig(interval_seconds=20),
        )
        assert c.current_page_id_time(0.0) == "p1"
        assert c.current_page_id_time(80.0) == "p1"

    @pytest.mark.parametrize("interval", [5, 10, 30, 60, 300, 3600])
    def test_various_interval_values(self, interval):
        c = Collection(
            name="Param",
            page_ids=["x", "y"],
            time=TimeModeConfig(interval_seconds=interval),
        )
        assert c.current_page_id_time(0.0) == "x"
        assert c.current_page_id_time(float(interval) - 0.001) == "x"
        assert c.current_page_id_time(float(interval)) == "y"

    # --- Variable-mode validation -------------------------------------------

    def test_variable_mode_requires_variable_block(self):
        with pytest.raises(ValidationError):
            Collection(
                name="MissingVar",
                page_ids=["p1", "p2"],
                selection_mode="variable",
            )

    def test_variable_default_must_be_in_page_ids(self):
        c = Collection(
            name="BadDefault",
            page_ids=["p1", "p2"],
            selection_mode="variable",
            variable=VariableModeConfig(
                default_page_id="not_a_member",
                rules=[],
            ),
        )
        errors = c.validate_config()
        assert any("default_page_id" in e for e in errors)

    def test_variable_rule_targets_must_be_in_page_ids(self):
        c = Collection(
            name="BadRule",
            page_ids=["p1", "p2"],
            selection_mode="variable",
            variable=VariableModeConfig(
                default_page_id="p1",
                rules=[VariableRule(expression="1 > 0", page_id="ghost")],
            ),
        )
        errors = c.validate_config()
        assert any("rule" in e.lower() and "page_id" in e for e in errors)

    # --- Request models ------------------------------------------------------

    def test_collection_create_defaults(self):
        data = CollectionCreate(name="Def", page_ids=["p1"])
        assert data.selection_mode == "time"
        assert data.time.interval_seconds == 30

    def test_collection_update_partial(self):
        data = CollectionUpdate(name="Renamed")
        dumped = data.model_dump(exclude_unset=True)
        assert "name" in dumped
        assert "page_ids" not in dumped
        assert "time" not in dumped
        assert "variable" not in dumped


# =============================================================================
# Model Tests — Random mode
# =============================================================================


class TestCollectionRandomMode:
    """Random selection: stateless shuffle-bag with no back-to-back repeats."""

    def _make(self, page_ids, interval=10):
        return Collection(
            name="Rand",
            page_ids=list(page_ids),
            selection_mode="random",
            random=RandomModeConfig(interval_seconds=interval),
        )

    def test_random_mode_requires_random_block(self):
        with pytest.raises(ValidationError):
            Collection(
                name="MissingRandom",
                page_ids=["p1", "p2"],
                selection_mode="random",
            )

    def test_random_mode_valid(self):
        c = self._make(["a", "b", "c"])
        assert c.is_valid()
        assert c.validate_config() == []
        assert c.selection_mode == "random"
        assert c.random is not None
        assert c.random.interval_seconds == 10

    def test_random_interval_range(self):
        with pytest.raises(ValidationError):
            RandomModeConfig(interval_seconds=1)
        with pytest.raises(ValidationError):
            RandomModeConfig(interval_seconds=7200)

    def test_random_default_interval(self):
        assert RandomModeConfig().interval_seconds == 30

    def test_random_single_page_always_first(self):
        c = self._make(["only"])
        for ts in [0.0, 5.0, 33.0, 999.0]:
            assert c.current_page_index_random(ts) == 0
            assert c.current_page_id_random(ts) == "only"

    def test_random_stable_within_window(self):
        c = self._make(["a", "b", "c"], interval=10)
        # Any timestamp inside one 10s window resolves to the same page.
        idx = c.current_page_index_random(0.0)
        for ts in [0.0, 0.1, 5.0, 9.0, 9.999]:
            assert c.current_page_index_random(ts) == idx

    def test_random_deterministic_and_restart_safe(self):
        # Two independent instances (e.g. before/after a restart) with the same
        # config must produce the identical sequence — proves statelessness.
        c1 = self._make(["a", "b", "c", "d"], interval=10)
        c2 = self._make(["a", "b", "c", "d"], interval=10)
        for bucket in range(50):
            ts = bucket * 10.0 + 1.0
            assert c1.current_page_id_random(ts) == c2.current_page_id_random(ts)

    @pytest.mark.parametrize("n", [2, 3, 4, 5, 7])
    def test_random_no_back_to_back_repeats(self, n):
        pages = [f"p{i}" for i in range(n)]
        c = self._make(pages, interval=10)
        prev = None
        for bucket in range(500):
            ts = bucket * 10.0 + 0.5
            cur = c.current_page_id_random(ts)
            assert cur in pages
            if prev is not None:
                assert cur != prev, f"repeat at bucket {bucket} for n={n}"
            prev = cur

    @pytest.mark.parametrize("n", [2, 3, 4, 5])
    def test_random_eventually_shows_every_page(self, n):
        pages = [f"p{i}" for i in range(n)]
        c = self._make(pages, interval=10)
        seen = {c.current_page_id_random(bucket * 10.0 + 0.5) for bucket in range(200)}
        assert seen == set(pages)

    def test_random_shuffle_bag_no_repeat_within_round(self):
        # A full "round" of n windows should show every page exactly once.
        pages = ["a", "b", "c", "d"]
        c = self._make(pages, interval=10)
        n = len(pages)
        # round 0 spans buckets 0..n-1
        round0 = [c.current_page_id_random(bucket * 10.0 + 0.5) for bucket in range(n)]
        assert sorted(round0) == sorted(pages)


# =============================================================================
# Storage Tests
# =============================================================================


class TestCollectionStorage:
    """Tests for CollectionStorage JSON persistence + schema versioning."""

    @pytest.fixture
    def storage(self, tmp_path):
        path = tmp_path / "collections.json"
        return CollectionStorage(str(path))

    def test_initially_empty(self, storage):
        assert storage.count() == 0
        assert storage.list_all() == []

    def test_create_and_get(self, storage):
        c = Collection(
            name="Test",
            page_ids=["p1", "p2"],
            time=TimeModeConfig(interval_seconds=10),
        )
        created = storage.create(c)
        fetched = storage.get(created.id)
        assert fetched is not None
        assert fetched.name == "Test"
        assert fetched.time.interval_seconds == 10

    def test_create_duplicate_id_raises(self, storage):
        c = Collection(name="A", page_ids=["p1"])
        storage.create(c)
        with pytest.raises(ValueError, match="already exists"):
            storage.create(c)

    def test_create_invalid_raises(self, storage):
        c = Collection(name="Bad", page_ids=["p1", "p1"])
        with pytest.raises(ValueError, match="duplicate"):
            storage.create(c)

    def test_update(self, storage):
        created = storage.create(Collection(name="Original", page_ids=["p1"]))
        updated = storage.update(created.id, {"name": "Renamed"})
        assert updated is not None
        assert updated.name == "Renamed"
        assert updated.updated_at is not None

    def test_update_nonexistent_returns_none(self, storage):
        assert storage.update("nonexistent", {"name": "X"}) is None

    def test_delete(self, storage):
        created = storage.create(Collection(name="Del", page_ids=["p1"]))
        deleted = storage.delete(created.id)
        assert deleted is True
        assert storage.count() == 0

    def test_list_all_sorted_by_name(self, storage):
        storage.create(Collection(name="Zebra", page_ids=["p1"]))
        storage.create(Collection(name="Alpha", page_ids=["p2"]))
        assert [c.name for c in storage.list_all()] == ["Alpha", "Zebra"]

    def test_persistence_survives_reload(self, tmp_path):
        path = tmp_path / "collections.json"
        s1 = CollectionStorage(str(path))
        created = s1.create(
            Collection(
                name="Persist",
                page_ids=["p1"],
                time=TimeModeConfig(interval_seconds=15),
            )
        )

        s2 = CollectionStorage(str(path))
        fetched = s2.get(created.id)
        assert fetched is not None
        assert fetched.name == "Persist"
        assert fetched.time.interval_seconds == 15

    def test_variable_mode_round_trip(self, tmp_path):
        path = tmp_path / "collections.json"
        s1 = CollectionStorage(str(path))
        created = s1.create(
            Collection(
                name="Var",
                page_ids=["hot", "cold"],
                selection_mode="variable",
                variable=VariableModeConfig(
                    rules=[VariableRule(expression="weather.temp > 70", page_id="hot")],
                    default_page_id="cold",
                    poll_seconds=5,
                ),
            )
        )

        s2 = CollectionStorage(str(path))
        fetched = s2.get(created.id)
        assert fetched is not None
        assert fetched.selection_mode == "variable"
        assert fetched.variable is not None
        assert fetched.variable.default_page_id == "cold"
        assert fetched.variable.poll_seconds == 5
        assert len(fetched.variable.rules) == 1
        assert fetched.variable.rules[0].expression == "weather.temp > 70"

    def test_random_mode_round_trip(self, tmp_path):
        path = tmp_path / "collections.json"
        s1 = CollectionStorage(str(path))
        created = s1.create(
            Collection(
                name="Rand",
                page_ids=["a", "b", "c"],
                selection_mode="random",
                random=RandomModeConfig(interval_seconds=45),
            )
        )

        s2 = CollectionStorage(str(path))
        fetched = s2.get(created.id)
        assert fetched is not None
        assert fetched.selection_mode == "random"
        assert fetched.random is not None
        assert fetched.random.interval_seconds == 45

    def test_schema_version_written(self, tmp_path):
        path = tmp_path / "collections.json"
        s = CollectionStorage(str(path))
        s.create(Collection(name="V", page_ids=["p1"]))
        import json

        with open(path) as f:
            data = json.load(f)
        assert data["schema_version"] == 1

    def test_migration_save_preserves_unparseable_entries(self, tmp_path):
        """Regression for #1313 (mirrors #1305): an entry that fails Pydantic
        validation during the post-migration save must NOT be silently dropped
        from the file."""
        import json

        path = tmp_path / "collections.json"
        # No schema_version => triggers v0 -> CURRENT migration, which resaves.
        data = {
            "collections": [
                {"id": "collection:good", "name": "Good", "page_ids": ["p1", "p2"]},
                {"id": "collection:bad", "broken_field": True},  # no name => invalid
            ],
        }
        path.write_text(json.dumps(data))

        storage = CollectionStorage(str(path))
        assert storage.get("collection:good") is not None
        assert storage.get("collection:bad") is None  # not in the in-memory cache

        on_disk = json.loads(path.read_text())
        on_disk_ids = {e["id"] for e in on_disk["collections"] if isinstance(e, dict) and "id" in e}
        assert "collection:bad" in on_disk_ids, "migration save silently dropped the invalid entry"
        assert "collection:good" in on_disk_ids

    def test_post_load_save_preserves_unparseable_entries(self, tmp_path):
        """An ordinary save (create/update/delete) after a load that encountered
        an unparseable entry must also preserve that entry on disk."""
        import json

        path = tmp_path / "collections.json"
        data = {
            "schema_version": 1,  # already current; no migration
            "collections": [
                {"id": "collection:good", "name": "Good", "page_ids": ["p1"]},
                {"id": "collection:bad", "broken_field": True},  # fails validation
            ],
        }
        path.write_text(json.dumps(data))

        storage = CollectionStorage(str(path))
        storage.create(Collection(name="New", page_ids=["p3"]))  # triggers a normal save

        on_disk = json.loads(path.read_text())
        on_disk_ids = {e["id"] for e in on_disk["collections"] if isinstance(e, dict) and "id" in e}
        assert "collection:bad" in on_disk_ids, "subsequent save dropped the unparseable entry"
        assert "collection:good" in on_disk_ids

    def test_save_is_atomic_on_mid_write_crash(self, tmp_path, monkeypatch):
        """Regression for #1313 (mirrors #1304): a crash inside _save() must not
        corrupt the existing file. The atomic tmp + os.replace pattern keeps the
        on-disk file intact until the rename succeeds, so reload still finds the
        original data."""
        import json

        from src.collections import storage as storage_module

        path = tmp_path / "collections.json"
        storage = CollectionStorage(str(path))
        storage.create(Collection(name="KeepMe", page_ids=["p1"]))
        assert storage.count() == 1
        original_bytes = path.read_bytes()

        real_dump = json.dump

        def crashing_dump(obj, fh, *args, **kwargs):
            fh.write('{"collections": [{"id": "abc"')
            fh.flush()
            raise OSError("Simulated crash mid-write")

        monkeypatch.setattr(storage_module.json, "dump", crashing_dump)
        with pytest.raises(OSError):
            storage._save()
        monkeypatch.setattr(storage_module.json, "dump", real_dump)

        # The original file must be byte-identical — the crash should have hit a
        # .tmp file that never got renamed over the real one.
        assert path.read_bytes() == original_bytes

        reloaded = CollectionStorage(str(path))
        assert reloaded.count() == 1
        assert reloaded.list_all()[0].name == "KeepMe"


# =============================================================================
# Legacy carousels.json migration
# =============================================================================


class TestLegacyCarouselImport:
    """Verify the one-shot import of an existing carousels.json file."""

    def test_import_legacy_carousels_helper(self):
        legacy = [
            {
                "id": "carousel:abc-123",
                "name": "Morning",
                "page_ids": ["p1", "p2"],
                "interval_seconds": 45,
            }
        ]
        converted = import_legacy_carousels(legacy)
        assert len(converted) == 1
        assert converted[0]["id"] == "collection:abc-123"
        assert converted[0]["selection_mode"] == "time"
        assert converted[0]["time"] == {"interval_seconds": 45}
        assert "interval_seconds" not in converted[0]

    def test_first_run_import_moves_legacy_file(self, tmp_path):
        """If carousels.json exists but collections.json does not, import once."""
        import json

        legacy_path = tmp_path / "carousels.json"
        collections_path = tmp_path / "collections.json"
        legacy_path.write_text(
            json.dumps(
                {
                    "carousels": [
                        {
                            "id": "carousel:zzz",
                            "name": "Legacy",
                            "page_ids": ["p1", "p2"],
                            "interval_seconds": 20,
                        }
                    ]
                }
            )
        )

        storage = CollectionStorage(str(collections_path))

        assert storage.count() == 1
        record = storage.get("collection:zzz")
        assert record is not None
        assert record.name == "Legacy"
        assert record.selection_mode == "time"
        assert record.time.interval_seconds == 20

        assert not legacy_path.exists()
        assert (tmp_path / "carousels.json.pre-collections-backup").exists()
        assert collections_path.exists()

    def test_legacy_import_preserves_unparseable_entries(self, tmp_path):
        """Regression for #1313: a legacy carousel that fails to convert/validate
        must still be round-tripped into collections.json, not silently dropped."""
        import json

        legacy_path = tmp_path / "carousels.json"
        collections_path = tmp_path / "collections.json"
        legacy_path.write_text(
            json.dumps(
                {
                    "carousels": [
                        {"id": "carousel:good", "name": "Good", "page_ids": ["p1"], "interval_seconds": 20},
                        {"id": "carousel:bad", "interval_seconds": 30},  # no name => invalid
                    ]
                }
            )
        )

        storage = CollectionStorage(str(collections_path))
        assert storage.get("collection:good") is not None
        assert storage.get("collection:bad") is None

        on_disk = json.loads(collections_path.read_text())
        on_disk_ids = {e["id"] for e in on_disk["collections"] if isinstance(e, dict) and "id" in e}
        assert "collection:bad" in on_disk_ids, "legacy import silently dropped the invalid carousel"
        assert "collection:good" in on_disk_ids


# =============================================================================
# Service Tests — Time mode
# =============================================================================


class TestCollectionServiceTimeMode:
    """Tests for CollectionService CRUD and time-mode resolution."""

    @pytest.fixture
    def service(self, tmp_path):
        storage = CollectionStorage(str(tmp_path / "collections.json"))
        return CollectionService(storage)

    def test_list_empty(self, service):
        assert service.list_collections() == []

    def test_create_collection(self, service):
        data = CollectionCreate(name="Svc", page_ids=["p1", "p2"])
        created = service.create_collection(data)
        assert created.name == "Svc"
        assert created.id.startswith(COLLECTION_ID_PREFIX)
        assert len(service.list_collections()) == 1

    def test_get_collection(self, service):
        data = CollectionCreate(name="Get", page_ids=["p1"])
        created = service.create_collection(data)
        fetched = service.get_collection(created.id)
        assert fetched is not None
        assert fetched.name == "Get"

    def test_get_nonexistent(self, service):
        assert service.get_collection("collection:nonexistent") is None

    def test_update_collection(self, service):
        created = service.create_collection(CollectionCreate(name="Old", page_ids=["p1"]))
        updated = service.update_collection(created.id, CollectionUpdate(name="New"))
        assert updated is not None
        assert updated.name == "New"

    def test_delete_collection(self, service):
        created = service.create_collection(CollectionCreate(name="Del", page_ids=["p1"]))
        assert service.delete_collection(created.id) is True
        assert service.list_collections() == []

    def test_resolve_page_id_regular(self, service):
        assert service.resolve_page_id("regular-page-id") == "regular-page-id"

    def test_resolve_page_id_nonexistent_collection(self, service):
        assert service.resolve_page_id("collection:nonexistent") is None

    def test_resolve_page_id_specific_time(self, service):
        created = service.create_collection(
            CollectionCreate(
                name="Fixed",
                page_ids=["a", "b", "c"],
                time=TimeModeConfig(interval_seconds=10),
            )
        )
        assert service.resolve_page_id(created.id, now_unix=0.0) == "a"
        assert service.resolve_page_id(created.id, now_unix=10.0) == "b"
        assert service.resolve_page_id(created.id, now_unix=20.0) == "c"
        assert service.resolve_page_id(created.id, now_unix=30.0) == "a"

    def test_seconds_until_next_check_regular(self, service):
        assert service.seconds_until_next_check("page-id") is None

    def test_seconds_until_next_check_single(self, service):
        created = service.create_collection(CollectionCreate(name="One", page_ids=["p1"]))
        assert service.seconds_until_next_check(created.id) is None

    def test_seconds_until_next_check_multi_time(self, service):
        created = service.create_collection(
            CollectionCreate(
                name="Multi",
                page_ids=["a", "b"],
                time=TimeModeConfig(interval_seconds=10),
            )
        )
        secs = service.seconds_until_next_check(created.id, now_unix=3.0)
        assert secs == 7

    def test_seconds_until_next_check_fractional(self, service):
        created = service.create_collection(
            CollectionCreate(
                name="Frac",
                page_ids=["a", "b"],
                time=TimeModeConfig(interval_seconds=10),
            )
        )
        assert service.seconds_until_next_check(created.id, now_unix=3.5) == 7
        assert service.seconds_until_next_check(created.id, now_unix=3.9) == 7
        assert service.seconds_until_next_check(created.id, now_unix=4.0) == 6

    def test_seconds_until_next_check_never_zero(self, service):
        created = service.create_collection(
            CollectionCreate(
                name="NonZero",
                page_ids=["a", "b"],
                time=TimeModeConfig(interval_seconds=10),
            )
        )
        for ts in [0.0, 5.0, 9.9, 9.999, 10.0, 15.5]:
            secs = service.seconds_until_next_check(created.id, now_unix=ts)
            assert secs >= 1

    @pytest.mark.parametrize("interval", [5, 10, 30, 60, 300])
    def test_seconds_until_next_check_various_intervals(self, service, interval):
        created = service.create_collection(
            CollectionCreate(
                name=f"Int{interval}",
                page_ids=["a", "b"],
                time=TimeModeConfig(interval_seconds=interval),
            )
        )
        assert service.seconds_until_next_check(created.id, now_unix=0.0) == interval
        mid = interval / 2.0
        expected = math.ceil(interval - mid)
        assert service.seconds_until_next_check(created.id, now_unix=mid) == expected


# =============================================================================
# Service Tests — Variable mode
# =============================================================================


class TestCollectionServiceVariableMode:
    """Verify expression-driven page selection."""

    @pytest.fixture
    def service(self, tmp_path):
        storage = CollectionStorage(str(tmp_path / "collections.json"))
        return CollectionService(storage)

    def _make_variable_collection(
        self, service, rules, default_page_id, page_ids=("hot", "cold", "mild"), poll_seconds=10
    ):
        return service.create_collection(
            CollectionCreate(
                name="Var",
                page_ids=list(page_ids),
                selection_mode="variable",
                variable=VariableModeConfig(
                    rules=[VariableRule(expression=e, page_id=p) for (e, p) in rules],
                    default_page_id=default_page_id,
                    poll_seconds=poll_seconds,
                ),
            )
        )

    def test_first_truthy_rule_wins(self, service):
        c = self._make_variable_collection(
            service,
            rules=[
                ("weather.temp > 80", "hot"),
                ("weather.temp < 50", "cold"),
            ],
            default_page_id="mild",
        )
        ctx = {"weather": {"temp": 90}}
        assert service.resolve_page_id(c.id, context=ctx) == "hot"

        ctx = {"weather": {"temp": 40}}
        assert service.resolve_page_id(c.id, context=ctx) == "cold"

    def test_order_matters_for_overlap(self, service):
        # Both rules match at temp=85 but the FIRST rule wins.
        c = self._make_variable_collection(
            service,
            rules=[
                ("weather.temp > 80", "hot"),
                ("weather.temp > 50", "mild"),
            ],
            default_page_id="cold",
        )
        ctx = {"weather": {"temp": 85}}
        assert service.resolve_page_id(c.id, context=ctx) == "hot"

    def test_falls_back_to_default_when_no_match(self, service):
        c = self._make_variable_collection(
            service,
            rules=[
                ("weather.temp > 80", "hot"),
                ("weather.temp < 50", "cold"),
            ],
            default_page_id="mild",
        )
        ctx = {"weather": {"temp": 65}}
        assert service.resolve_page_id(c.id, context=ctx) == "mild"

    def test_rule_with_error_is_skipped(self, service):
        # First rule references an unknown source — should error and be skipped.
        # Second rule is valid and wins.
        c = self._make_variable_collection(
            service,
            rules=[
                ("UNKNOWN_FN(weather.temp)", "hot"),
                ("weather.temp > 0", "mild"),
            ],
            default_page_id="cold",
        )
        ctx = {"weather": {"temp": 10}}
        assert service.resolve_page_id(c.id, context=ctx) == "mild"

    def test_all_rules_error_returns_default(self, service):
        c = self._make_variable_collection(
            service,
            rules=[
                ("UNKNOWN_FN(x)", "hot"),
                ("ANOTHER_UNKNOWN(y)", "cold"),
            ],
            default_page_id="mild",
        )
        assert service.resolve_page_id(c.id, context={}) == "mild"

    def test_empty_rules_returns_default(self, service):
        c = self._make_variable_collection(
            service,
            rules=[],
            default_page_id="hot",
        )
        assert service.resolve_page_id(c.id, context={}) == "hot"

    def test_seconds_until_next_check_uses_poll_seconds(self, service):
        c = self._make_variable_collection(
            service,
            rules=[("weather.temp > 80", "hot")],
            default_page_id="cold",
            poll_seconds=15,
        )
        assert service.seconds_until_next_check(c.id) == 15


# =============================================================================
# Service Tests — Random mode
# =============================================================================


class TestCollectionServiceRandomMode:
    """Verify random-mode resolution and timing through the service layer."""

    @pytest.fixture
    def service(self, tmp_path):
        storage = CollectionStorage(str(tmp_path / "collections.json"))
        return CollectionService(storage)

    def _make_random_collection(self, service, page_ids=("a", "b", "c"), interval=10):
        return service.create_collection(
            CollectionCreate(
                name="Rand",
                page_ids=list(page_ids),
                selection_mode="random",
                random=RandomModeConfig(interval_seconds=interval),
            )
        )

    def test_resolve_page_id_random_returns_member(self, service):
        c = self._make_random_collection(service)
        page = service.resolve_page_id(c.id, now_unix=5.0)
        assert page in c.page_ids

    def test_resolve_page_id_random_stable_within_window(self, service):
        c = self._make_random_collection(service, interval=10)
        first = service.resolve_page_id(c.id, now_unix=0.0)
        assert service.resolve_page_id(c.id, now_unix=9.999) == first

    def test_resolve_page_id_random_no_back_to_back_repeats(self, service):
        c = self._make_random_collection(service, page_ids=("a", "b", "c", "d"), interval=10)
        prev = None
        for bucket in range(100):
            cur = service.resolve_page_id(c.id, now_unix=bucket * 10.0 + 0.5)
            if prev is not None:
                assert cur != prev
            prev = cur

    def test_seconds_until_next_check_random(self, service):
        c = self._make_random_collection(service, page_ids=("a", "b"), interval=10)
        assert service.seconds_until_next_check(c.id, now_unix=3.0) == 7
        assert service.seconds_until_next_check(c.id, now_unix=0.0) == 10

    def test_seconds_until_next_check_random_single_page(self, service):
        c = self._make_random_collection(service, page_ids=("only",), interval=10)
        assert service.seconds_until_next_check(c.id) is None
