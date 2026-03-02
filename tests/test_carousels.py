"""Tests for carousels module (models, storage, service, API)."""

import math
import pytest
import tempfile
import os
import time
from datetime import datetime
from unittest.mock import Mock, patch

from src.carousels.models import (
    Carousel,
    CarouselCreate,
    CarouselUpdate,
    make_carousel_id,
    is_carousel_id,
    extract_carousel_uuid,
    CAROUSEL_ID_PREFIX,
)
from src.carousels.storage import CarouselStorage
from src.carousels.service import CarouselService


# =============================================================================
# Model Tests
# =============================================================================


class TestCarouselModels:
    """Tests for Carousel and related models."""

    def test_make_carousel_id(self):
        """IDs start with the carousel prefix."""
        cid = make_carousel_id()
        assert cid.startswith(CAROUSEL_ID_PREFIX)

    def test_is_carousel_id_true(self):
        """is_carousel_id returns True for carousel IDs."""
        assert is_carousel_id("carousel:abc-123")

    def test_is_carousel_id_false_for_page(self):
        """is_carousel_id returns False for regular page IDs."""
        assert not is_carousel_id("abc-123")
        assert not is_carousel_id("")

    def test_is_carousel_id_none(self):
        """is_carousel_id handles None gracefully."""
        assert not is_carousel_id(None)

    def test_extract_carousel_uuid(self):
        """extract_carousel_uuid strips the prefix."""
        assert extract_carousel_uuid("carousel:abc-123") == "abc-123"

    def test_carousel_valid(self):
        """A carousel with distinct pages is valid."""
        c = Carousel(name="Test", page_ids=["p1", "p2"], interval_seconds=30)
        assert c.is_valid()
        assert c.validate_config() == []

    def test_carousel_empty_pages_invalid(self):
        """A carousel with no page_ids is invalid."""
        c = Carousel(name="Empty", page_ids=["p1"])
        c.page_ids = []
        errors = c.validate_config()
        assert any("at least one" in e.lower() for e in errors)

    def test_carousel_duplicate_pages_invalid(self):
        """A carousel with duplicate page IDs is invalid."""
        c = Carousel(name="Dup", page_ids=["p1", "p1"])
        errors = c.validate_config()
        assert any("duplicate" in e.lower() for e in errors)

    def test_carousel_nested_carousel_invalid(self):
        """A carousel containing another carousel ID is invalid."""
        c = Carousel(name="Nested", page_ids=["p1", "carousel:nested-id"])
        errors = c.validate_config()
        assert any("carousel" in e.lower() for e in errors)

    def test_carousel_id_prefix(self):
        """Auto-generated carousel IDs have the correct prefix."""
        c = Carousel(name="Auto", page_ids=["p1"])
        assert c.id.startswith(CAROUSEL_ID_PREFIX)

    def test_carousel_interval_defaults(self):
        """Default interval is 30 seconds."""
        c = Carousel(name="Defaults", page_ids=["p1"])
        assert c.interval_seconds == 30

    def test_carousel_interval_range(self):
        """interval_seconds must be between 5 and 3600."""
        with pytest.raises(Exception):
            Carousel(name="Too Low", page_ids=["p1"], interval_seconds=1)
        with pytest.raises(Exception):
            Carousel(name="Too High", page_ids=["p1"], interval_seconds=7200)

    # --- Cycling Logic -------------------------------------------------------

    def test_current_page_index_wraps(self):
        """current_page_index wraps around the page list."""
        c = Carousel(name="Cycle", page_ids=["a", "b", "c"], interval_seconds=10)
        assert c.current_page_index(0) == 0   # t=0  → index 0
        assert c.current_page_index(10) == 1  # t=10 → index 1
        assert c.current_page_index(20) == 2  # t=20 → index 2
        assert c.current_page_index(30) == 0  # wraps

    def test_current_page_id(self):
        """current_page_id returns the correct page at each interval."""
        c = Carousel(name="Cycle", page_ids=["a", "b", "c"], interval_seconds=10)
        assert c.current_page_id(0) == "a"
        assert c.current_page_id(15) == "b"
        assert c.current_page_id(25) == "c"
        assert c.current_page_id(35) == "a"

    def test_current_page_id_single_page(self):
        """A single-page carousel always returns the same page."""
        c = Carousel(name="Single", page_ids=["only"], interval_seconds=10)
        assert c.current_page_id(0) == "only"
        assert c.current_page_id(999) == "only"

    def test_current_page_id_deterministic(self):
        """Same timestamp always yields same result (stateless)."""
        c = Carousel(name="Det", page_ids=["a", "b"], interval_seconds=5)
        result1 = c.current_page_id(12345.0)
        result2 = c.current_page_id(12345.0)
        assert result1 == result2

    # --- Interval Timing Accuracy --------------------------------------------

    def test_transition_exactly_at_boundary(self):
        """Page changes exactly at the interval boundary, not before or after."""
        c = Carousel(name="Boundary", page_ids=["a", "b", "c"], interval_seconds=10)
        # Just before the boundary: still on the previous page
        assert c.current_page_id(9.999) == "a"
        # Exactly at the boundary: transitions to next page
        assert c.current_page_id(10.0) == "b"
        # Just after the boundary
        assert c.current_page_id(10.001) == "b"

    def test_each_page_gets_exact_interval(self):
        """Every page is displayed for exactly interval_seconds."""
        c = Carousel(name="Exact", page_ids=["a", "b", "c"], interval_seconds=15)
        for page_idx in range(3):
            start = page_idx * 15
            end = (page_idx + 1) * 15
            expected = c.page_ids[page_idx]
            # Page is shown at the start of its interval
            assert c.current_page_id(float(start)) == expected
            # Page is shown just before its interval ends
            assert c.current_page_id(end - 0.001) == expected
            # Page transitions away exactly at end
            assert c.current_page_id(float(end)) != expected

    def test_full_cycle_returns_to_first_page(self):
        """After one full cycle, the carousel returns to the first page."""
        pages = ["p1", "p2", "p3", "p4"]
        c = Carousel(name="FullCycle", page_ids=pages, interval_seconds=20)
        cycle_duration = 20 * len(pages)  # 80 seconds
        assert c.current_page_id(0.0) == "p1"
        assert c.current_page_id(float(cycle_duration)) == "p1"

    def test_timing_across_many_cycles(self):
        """Interval timing remains accurate over many cycles."""
        c = Carousel(name="LongRun", page_ids=["a", "b"], interval_seconds=10)
        for cycle in range(100):
            offset = cycle * 20  # full cycle = 20s
            assert c.current_page_id(float(offset)) == "a"
            assert c.current_page_id(float(offset + 10)) == "b"

    @pytest.mark.parametrize("interval", [5, 10, 30, 60, 300, 3600])
    def test_various_interval_values(self, interval):
        """Transitions are accurate for various allowed interval_seconds values."""
        c = Carousel(name="Param", page_ids=["x", "y"], interval_seconds=interval)
        assert c.current_page_id(0.0) == "x"
        assert c.current_page_id(float(interval) - 0.001) == "x"
        assert c.current_page_id(float(interval)) == "y"
        assert c.current_page_id(float(2 * interval) - 0.001) == "y"
        assert c.current_page_id(float(2 * interval)) == "x"

    def test_mid_interval_stays_on_same_page(self):
        """Querying at any point within an interval returns the same page."""
        c = Carousel(name="Mid", page_ids=["a", "b", "c"], interval_seconds=30)
        # All queries within the first 30-second window should return "a"
        for offset_ms in range(0, 30000, 500):
            ts = offset_ms / 1000.0
            assert c.current_page_id(ts) == "a", f"Expected 'a' at t={ts}"

    # --- Request Models ------------------------------------------------------

    def test_carousel_create_model(self):
        """CarouselCreate validates correctly."""
        data = CarouselCreate(name="New", page_ids=["p1", "p2"], interval_seconds=60)
        assert data.name == "New"
        assert data.interval_seconds == 60

    def test_carousel_create_defaults(self):
        """CarouselCreate default interval is 30."""
        data = CarouselCreate(name="Def", page_ids=["p1"])
        assert data.interval_seconds == 30

    def test_carousel_update_partial(self):
        """CarouselUpdate allows partial updates."""
        data = CarouselUpdate(name="Renamed")
        dumped = data.model_dump(exclude_unset=True)
        assert "name" in dumped
        assert "page_ids" not in dumped
        assert "interval_seconds" not in dumped


# =============================================================================
# Storage Tests
# =============================================================================


class TestCarouselStorage:
    """Tests for CarouselStorage JSON persistence."""

    @pytest.fixture
    def storage(self, tmp_path):
        path = tmp_path / "carousels.json"
        return CarouselStorage(str(path))

    def test_initially_empty(self, storage):
        assert storage.count() == 0
        assert storage.list_all() == []

    def test_create_and_get(self, storage):
        c = Carousel(name="Test", page_ids=["p1", "p2"], interval_seconds=10)
        created = storage.create(c)
        assert storage.count() == 1
        fetched = storage.get(created.id)
        assert fetched is not None
        assert fetched.name == "Test"

    def test_create_duplicate_id_raises(self, storage):
        c = Carousel(name="A", page_ids=["p1"])
        storage.create(c)
        with pytest.raises(ValueError, match="already exists"):
            storage.create(c)

    def test_create_invalid_raises(self, storage):
        c = Carousel(name="Bad", page_ids=["p1", "p1"])
        with pytest.raises(ValueError, match="duplicate"):
            storage.create(c)

    def test_update(self, storage):
        c = Carousel(name="Original", page_ids=["p1"])
        created = storage.create(c)
        updated = storage.update(created.id, {"name": "Renamed"})
        assert updated is not None
        assert updated.name == "Renamed"
        assert updated.updated_at is not None

    def test_update_nonexistent_returns_none(self, storage):
        assert storage.update("nonexistent", {"name": "X"}) is None

    def test_update_invalid_raises(self, storage):
        c = Carousel(name="A", page_ids=["p1"])
        created = storage.create(c)
        with pytest.raises(ValueError, match="duplicate"):
            storage.update(created.id, {"page_ids": ["p1", "p1"]})

    def test_delete(self, storage):
        c = Carousel(name="Del", page_ids=["p1"])
        created = storage.create(c)
        assert storage.delete(created.id) is True
        assert storage.count() == 0

    def test_delete_nonexistent(self, storage):
        assert storage.delete("nonexistent") is False

    def test_exists(self, storage):
        c = Carousel(name="Ex", page_ids=["p1"])
        created = storage.create(c)
        assert storage.exists(created.id) is True
        assert storage.exists("nonexistent") is False

    def test_list_all_sorted_by_name(self, storage):
        storage.create(Carousel(name="Zebra", page_ids=["p1"]))
        storage.create(Carousel(name="Alpha", page_ids=["p2"]))
        result = storage.list_all()
        assert [c.name for c in result] == ["Alpha", "Zebra"]

    def test_persistence_survives_reload(self, tmp_path):
        """Data persists across storage instances."""
        path = tmp_path / "carousels.json"
        s1 = CarouselStorage(str(path))
        c = Carousel(name="Persist", page_ids=["p1"], interval_seconds=15)
        created = s1.create(c)

        s2 = CarouselStorage(str(path))
        fetched = s2.get(created.id)
        assert fetched is not None
        assert fetched.name == "Persist"
        assert fetched.interval_seconds == 15

    def test_datetime_serialization(self, tmp_path):
        """Datetime fields round-trip through JSON correctly."""
        path = tmp_path / "carousels.json"
        s1 = CarouselStorage(str(path))
        c = Carousel(name="DT", page_ids=["p1"])
        created = s1.create(c)
        updated = s1.update(created.id, {"name": "DT2"})

        s2 = CarouselStorage(str(path))
        fetched = s2.get(created.id)
        assert fetched.created_at is not None
        assert fetched.updated_at is not None


# =============================================================================
# Service Tests
# =============================================================================


class TestCarouselService:
    """Tests for CarouselService CRUD and resolution."""

    @pytest.fixture
    def service(self, tmp_path):
        path = tmp_path / "carousels.json"
        storage = CarouselStorage(str(path))
        return CarouselService(storage)

    def test_list_empty(self, service):
        assert service.list_carousels() == []

    def test_create_carousel(self, service):
        data = CarouselCreate(name="Svc", page_ids=["p1", "p2"])
        created = service.create_carousel(data)
        assert created.name == "Svc"
        assert created.id.startswith(CAROUSEL_ID_PREFIX)
        assert len(service.list_carousels()) == 1

    def test_get_carousel(self, service):
        data = CarouselCreate(name="Get", page_ids=["p1"])
        created = service.create_carousel(data)
        fetched = service.get_carousel(created.id)
        assert fetched is not None
        assert fetched.name == "Get"

    def test_get_nonexistent(self, service):
        assert service.get_carousel("carousel:nonexistent") is None

    def test_update_carousel(self, service):
        created = service.create_carousel(CarouselCreate(name="Old", page_ids=["p1"]))
        updated = service.update_carousel(created.id, CarouselUpdate(name="New"))
        assert updated is not None
        assert updated.name == "New"

    def test_delete_carousel(self, service):
        created = service.create_carousel(CarouselCreate(name="Del", page_ids=["p1"]))
        assert service.delete_carousel(created.id) is True
        assert service.list_carousels() == []

    # --- Page Resolution -----------------------------------------------------

    def test_resolve_page_id_regular(self, service):
        """Regular page IDs pass through unchanged."""
        assert service.resolve_page_id("regular-page-id") == "regular-page-id"

    def test_resolve_page_id_carousel(self, service):
        """Carousel ID resolves to one of its pages."""
        created = service.create_carousel(
            CarouselCreate(name="Resolve", page_ids=["p1", "p2", "p3"], interval_seconds=10)
        )
        resolved = service.resolve_page_id(created.id)
        assert resolved in ["p1", "p2", "p3"]

    def test_resolve_page_id_nonexistent_carousel(self, service):
        """Non-existent carousel returns None."""
        assert service.resolve_page_id("carousel:nonexistent") is None

    def test_resolve_page_id_specific_time(self, service):
        """resolve_page_id at a known timestamp is deterministic."""
        created = service.create_carousel(
            CarouselCreate(name="Fixed", page_ids=["a", "b", "c"], interval_seconds=10)
        )
        assert service.resolve_page_id(created.id, now_unix=0.0) == "a"
        assert service.resolve_page_id(created.id, now_unix=10.0) == "b"
        assert service.resolve_page_id(created.id, now_unix=20.0) == "c"
        assert service.resolve_page_id(created.id, now_unix=30.0) == "a"

    # --- seconds_until_next_page ---------------------------------------------

    def test_seconds_until_next_page_regular(self, service):
        """Non-carousel IDs return None."""
        assert service.seconds_until_next_page("page-id") is None

    def test_seconds_until_next_page_single(self, service):
        """Single-page carousels return None (no cycling)."""
        created = service.create_carousel(
            CarouselCreate(name="One", page_ids=["p1"], interval_seconds=10)
        )
        assert service.seconds_until_next_page(created.id) is None

    def test_seconds_until_next_page_multi(self, service):
        """Multi-page carousel returns a positive value."""
        created = service.create_carousel(
            CarouselCreate(name="Multi", page_ids=["a", "b"], interval_seconds=10)
        )
        secs = service.seconds_until_next_page(created.id)
        assert secs is not None
        assert 1 <= secs <= 10

    def test_seconds_until_next_page_fixed_time(self, service):
        """At a known time, seconds_until_next_page is predictable."""
        created = service.create_carousel(
            CarouselCreate(name="Fixed", page_ids=["a", "b"], interval_seconds=10)
        )
        secs = service.seconds_until_next_page(created.id, now_unix=3.0)
        assert secs == 7  # 10 - 3 = 7

    # --- Interval Timing Accuracy (Service) ----------------------------------

    def test_seconds_until_next_page_fractional_timestamp(self, service):
        """Fractional timestamps produce correct ceiling of remaining seconds."""
        created = service.create_carousel(
            CarouselCreate(name="Frac", page_ids=["a", "b"], interval_seconds=10)
        )
        # At t=3.5, remaining is 6.5s -> should ceil to 7
        assert service.seconds_until_next_page(created.id, now_unix=3.5) == 7
        # At t=3.9, remaining is 6.1s -> should ceil to 7
        assert service.seconds_until_next_page(created.id, now_unix=3.9) == 7
        # At t=4.0, remaining is exactly 6.0s -> 6
        assert service.seconds_until_next_page(created.id, now_unix=4.0) == 6

    def test_seconds_until_next_page_at_boundary(self, service):
        """At exact interval boundary, a full interval remains."""
        created = service.create_carousel(
            CarouselCreate(name="Boundary", page_ids=["a", "b"], interval_seconds=10)
        )
        # At exactly t=10 (boundary), the next page is at t=20: 10 seconds away
        assert service.seconds_until_next_page(created.id, now_unix=10.0) == 10

    def test_seconds_until_next_page_just_before_boundary(self, service):
        """Just before a transition, minimum of 1 second is returned."""
        created = service.create_carousel(
            CarouselCreate(name="JustBefore", page_ids=["a", "b"], interval_seconds=10)
        )
        # At t=9.999, remaining is 0.001s -> ceil to 1, max(1,1) = 1
        assert service.seconds_until_next_page(created.id, now_unix=9.999) == 1

    def test_seconds_until_next_page_never_zero(self, service):
        """seconds_until_next_page never returns 0 due to max(1, ...) guard."""
        created = service.create_carousel(
            CarouselCreate(name="NonZero", page_ids=["a", "b"], interval_seconds=10)
        )
        for ts in [0.0, 5.0, 9.9, 9.999, 10.0, 15.5]:
            secs = service.seconds_until_next_page(created.id, now_unix=ts)
            assert secs >= 1, f"Expected >= 1 at t={ts}, got {secs}"

    def test_seconds_until_next_page_decreases_within_interval(self, service):
        """Remaining seconds monotonically decreases within a single interval."""
        created = service.create_carousel(
            CarouselCreate(name="Monotonic", page_ids=["a", "b"], interval_seconds=10)
        )
        prev = service.seconds_until_next_page(created.id, now_unix=0.0)
        for t in range(1, 10):
            curr = service.seconds_until_next_page(created.id, now_unix=float(t))
            assert curr <= prev, f"Expected {curr} <= {prev} at t={t}"
            prev = curr

    @pytest.mark.parametrize("interval", [5, 10, 30, 60, 300])
    def test_seconds_until_next_page_various_intervals(self, service, interval):
        """seconds_until_next_page is consistent for various interval values."""
        created = service.create_carousel(
            CarouselCreate(name=f"Int{interval}", page_ids=["a", "b"], interval_seconds=interval)
        )
        # At start of interval, full interval remains
        assert service.seconds_until_next_page(created.id, now_unix=0.0) == interval
        # At midpoint
        mid = interval / 2.0
        expected = math.ceil(interval - mid)
        secs = service.seconds_until_next_page(created.id, now_unix=mid)
        assert secs == expected

    def test_resolve_page_changes_after_interval(self, service):
        """resolve_page_id returns different pages after interval_seconds elapses."""
        created = service.create_carousel(
            CarouselCreate(name="Resolve", page_ids=["a", "b", "c"], interval_seconds=10)
        )
        page_at_0 = service.resolve_page_id(created.id, now_unix=0.0)
        page_at_10 = service.resolve_page_id(created.id, now_unix=10.0)
        page_at_20 = service.resolve_page_id(created.id, now_unix=20.0)
        assert page_at_0 == "a"
        assert page_at_10 == "b"
        assert page_at_20 == "c"
        # Same page within an interval
        assert service.resolve_page_id(created.id, now_unix=5.0) == "a"
        assert service.resolve_page_id(created.id, now_unix=9.999) == "a"


# =============================================================================
# API Endpoint Tests
# =============================================================================


class TestCarouselAPI:
    """Tests for carousel REST API endpoints."""

    @pytest.fixture
    def client(self, tmp_path):
        """Create a test client with isolated storage."""
        # Reset singletons
        import src.carousels.service as cs_mod
        import src.pages.service as ps_mod

        page_storage_file = str(tmp_path / "pages.json")
        carousel_storage_file = str(tmp_path / "carousels.json")

        from src.pages.storage import PageStorage
        from src.pages.service import PageService

        page_storage = PageStorage(page_storage_file)
        page_service = PageService(page_storage)

        carousel_storage = CarouselStorage(carousel_storage_file)
        carousel_service = CarouselService(carousel_storage)

        old_ps = ps_mod._page_service
        old_cs = cs_mod._carousel_service
        ps_mod._page_service = page_service
        cs_mod._carousel_service = carousel_service

        from fastapi.testclient import TestClient
        from src.api_server import app

        yield TestClient(app), page_service, carousel_service

        ps_mod._page_service = old_ps
        cs_mod._carousel_service = old_cs

    def _create_pages(self, page_service, count=3):
        """Helper: create test pages and return their IDs."""
        from src.pages.models import PageCreate
        ids = []
        for i in range(count):
            p = page_service.create_page(PageCreate(
                name=f"Page {i+1}",
                type="template",
                template=[f"Content {i+1}"],
            ))
            ids.append(p.id)
        return ids

    def test_list_carousels_empty(self, client):
        c, _, _ = client
        resp = c.get("/carousels")
        assert resp.status_code == 200
        data = resp.json()
        assert data["carousels"] == []
        assert data["total"] == 0

    def test_create_carousel(self, client):
        c, ps, _ = client
        page_ids = self._create_pages(ps, 2)
        resp = c.post("/carousels", json={
            "name": "API Carousel",
            "page_ids": page_ids,
            "interval_seconds": 15,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["carousel"]["name"] == "API Carousel"
        assert data["carousel"]["id"].startswith(CAROUSEL_ID_PREFIX)

    def test_create_carousel_invalid_page(self, client):
        c, _, _ = client
        resp = c.post("/carousels", json={
            "name": "Bad",
            "page_ids": ["nonexistent-page-id"],
        })
        assert resp.status_code == 400

    def test_get_carousel(self, client):
        c, ps, cs = client
        page_ids = self._create_pages(ps, 2)
        created = cs.create_carousel(
            CarouselCreate(name="Fetch", page_ids=page_ids)
        )
        resp = c.get(f"/carousels/{created.id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Fetch"

    def test_get_carousel_not_found(self, client):
        c, _, _ = client
        resp = c.get("/carousels/carousel:nonexistent")
        assert resp.status_code == 404

    def test_update_carousel(self, client):
        c, ps, cs = client
        page_ids = self._create_pages(ps, 2)
        created = cs.create_carousel(
            CarouselCreate(name="Before", page_ids=page_ids)
        )
        resp = c.put(f"/carousels/{created.id}", json={"name": "After"})
        assert resp.status_code == 200
        assert resp.json()["carousel"]["name"] == "After"

    def test_update_carousel_not_found(self, client):
        c, _, _ = client
        resp = c.put("/carousels/carousel:nonexistent", json={"name": "X"})
        assert resp.status_code == 404

    def test_update_carousel_invalid_page(self, client):
        c, ps, cs = client
        page_ids = self._create_pages(ps, 1)
        created = cs.create_carousel(
            CarouselCreate(name="UpdBad", page_ids=page_ids)
        )
        resp = c.put(f"/carousels/{created.id}", json={
            "page_ids": ["nonexistent"]
        })
        assert resp.status_code == 400

    def test_delete_carousel(self, client):
        c, ps, cs = client
        page_ids = self._create_pages(ps, 1)
        created = cs.create_carousel(
            CarouselCreate(name="Del", page_ids=page_ids)
        )
        resp = c.delete(f"/carousels/{created.id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
        assert cs.list_carousels() == []

    def test_delete_carousel_not_found(self, client):
        c, _, _ = client
        resp = c.delete("/carousels/carousel:nonexistent")
        assert resp.status_code == 404

    def test_list_carousels_after_create(self, client):
        c, ps, cs = client
        page_ids = self._create_pages(ps, 2)
        cs.create_carousel(CarouselCreate(name="C1", page_ids=page_ids))
        cs.create_carousel(CarouselCreate(name="C2", page_ids=page_ids))
        resp = c.get("/carousels")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        names = [c["name"] for c in data["carousels"]]
        assert "C1" in names
        assert "C2" in names
