"""Tests for schedule storage."""

import builtins
import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.schedules.models import DEFAULT_BOARD_ID, ScheduleEntry
from src.schedules.storage import ScheduleStorage


@pytest.fixture
def temp_storage_file():
    """Create a temporary storage file."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        temp_path = f.name
    yield temp_path
    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def storage(temp_storage_file):
    """Create a storage instance with temporary file."""
    return ScheduleStorage(storage_file=temp_storage_file)


@pytest.fixture
def sample_schedule():
    """Create a sample schedule entry."""
    return ScheduleEntry(
        id="test-schedule-1",
        page_id="page-123",
        start_time="09:00",
        end_time="17:00",
        day_pattern="weekdays",
        enabled=True,
    )


class TestScheduleStorage:
    """Test schedule storage operations."""

    def test_init_creates_empty_storage(self, temp_storage_file):
        """Test that init creates empty storage if file doesn't exist."""
        storage = ScheduleStorage(storage_file=temp_storage_file)

        assert storage.count() == 0
        assert storage.list_all() == []
        assert storage.get_default_page_id() is None

    def test_create_schedule(self, storage, sample_schedule):
        """Test creating a schedule entry."""
        created = storage.create(sample_schedule)

        assert created.id == sample_schedule.id
        assert created.page_id == sample_schedule.page_id
        assert storage.count() == 1

    def test_create_duplicate_id_raises_error(self, storage, sample_schedule):
        """Test that creating duplicate ID raises error."""
        storage.create(sample_schedule)

        with pytest.raises(ValueError, match="already exists"):
            storage.create(sample_schedule)

    def test_get_schedule(self, storage, sample_schedule):
        """Test retrieving a schedule by ID."""
        storage.create(sample_schedule)

        retrieved = storage.get(sample_schedule.id)
        assert retrieved is not None
        assert retrieved.id == sample_schedule.id
        assert retrieved.page_id == sample_schedule.page_id

    def test_get_nonexistent_schedule(self, storage):
        """Test retrieving non-existent schedule returns None."""
        result = storage.get("nonexistent-id")
        assert result is None

    def test_list_all_schedules(self, storage):
        """Test listing all schedules."""
        # Create multiple schedules
        schedule1 = ScheduleEntry(
            page_id="page-1", start_time="09:00", end_time="12:00", day_pattern="all", enabled=True
        )
        schedule2 = ScheduleEntry(
            page_id="page-2", start_time="12:00", end_time="17:00", day_pattern="all", enabled=True
        )

        storage.create(schedule1)
        storage.create(schedule2)

        schedules = storage.list_all()
        assert len(schedules) == 2
        assert any(s.id == schedule1.id for s in schedules)
        assert any(s.id == schedule2.id for s in schedules)

    def test_list_all_sorted_by_created_at(self, storage):
        """Test that list_all returns schedules sorted by created_at."""
        # Create schedules with slight time differences
        schedule1 = ScheduleEntry(
            page_id="page-1", start_time="09:00", end_time="12:00", day_pattern="all", enabled=True
        )
        storage.create(schedule1)

        schedule2 = ScheduleEntry(
            page_id="page-2", start_time="12:00", end_time="17:00", day_pattern="all", enabled=True
        )
        storage.create(schedule2)

        schedules = storage.list_all()
        assert schedules[0].id == schedule1.id
        assert schedules[1].id == schedule2.id

    def test_update_schedule(self, storage, sample_schedule):
        """Test updating a schedule entry."""
        storage.create(sample_schedule)

        updates = {"start_time": "10:00", "end_time": "18:00", "enabled": False}

        updated = storage.update(sample_schedule.id, updates)

        assert updated is not None
        assert updated.start_time == "10:00"
        assert updated.end_time == "18:00"
        assert updated.enabled is False
        assert updated.updated_at is not None

    def test_update_nonexistent_schedule(self, storage):
        """Test updating non-existent schedule returns None."""
        result = storage.update("nonexistent-id", {"enabled": False})
        assert result is None

    def test_update_preserves_unchanged_fields(self, storage, sample_schedule):
        """Test that update preserves fields not in updates dict."""
        storage.create(sample_schedule)

        updates = {"enabled": False}
        updated = storage.update(sample_schedule.id, updates)

        assert updated.page_id == sample_schedule.page_id
        assert updated.start_time == sample_schedule.start_time
        assert updated.end_time == sample_schedule.end_time
        assert updated.enabled is False

    def test_delete_schedule(self, storage, sample_schedule):
        """Test deleting a schedule entry."""
        storage.create(sample_schedule)
        assert storage.count() == 1

        result = storage.delete(sample_schedule.id)
        assert result is True
        assert storage.count() == 0

    def test_delete_nonexistent_schedule(self, storage):
        """Test deleting non-existent schedule returns False."""
        result = storage.delete("nonexistent-id")
        assert result is False

    def test_exists(self, storage, sample_schedule):
        """Test checking if schedule exists."""
        assert storage.exists(sample_schedule.id) is False

        storage.create(sample_schedule)
        assert storage.exists(sample_schedule.id) is True

        storage.delete(sample_schedule.id)
        assert storage.exists(sample_schedule.id) is False

    def test_count(self, storage):
        """Test counting schedules."""
        assert storage.count() == 0

        schedule1 = ScheduleEntry(
            page_id="page-1", start_time="09:00", end_time="12:00", day_pattern="all", enabled=True
        )
        storage.create(schedule1)
        assert storage.count() == 1

        schedule2 = ScheduleEntry(
            page_id="page-2", start_time="12:00", end_time="17:00", day_pattern="all", enabled=True
        )
        storage.create(schedule2)
        assert storage.count() == 2

    def test_set_default_page_id(self, storage):
        """Test setting default page ID."""
        storage.set_default_page_id("page-default")
        assert storage.get_default_page_id() == "page-default"

    def test_get_default_page_id_initial_none(self, storage):
        """Test that default page ID is initially None."""
        assert storage.get_default_page_id() is None

    def test_set_default_page_id_to_none(self, storage):
        """Test clearing default page ID."""
        storage.set_default_page_id("page-default")
        assert storage.get_default_page_id() == "page-default"

        storage.set_default_page_id(None)
        assert storage.get_default_page_id() is None

    def test_persistence_survives_reload(self, temp_storage_file, sample_schedule):
        """Test that data persists across storage instances."""
        # Create and save schedule
        storage1 = ScheduleStorage(storage_file=temp_storage_file)
        storage1.create(sample_schedule)
        storage1.set_default_page_id("page-default")

        # Create new storage instance (simulates restart)
        storage2 = ScheduleStorage(storage_file=temp_storage_file)

        # Verify data persisted
        assert storage2.count() == 1
        retrieved = storage2.get(sample_schedule.id)
        assert retrieved is not None
        assert retrieved.page_id == sample_schedule.page_id
        assert storage2.get_default_page_id() == "page-default"

    def test_handles_corrupted_json_file(self, temp_storage_file):
        """Test that storage handles corrupted JSON gracefully."""
        # Write invalid JSON to file
        with open(temp_storage_file, "w") as f:
            f.write("{ invalid json }")

        # Should load with empty data instead of crashing
        storage = ScheduleStorage(storage_file=temp_storage_file)
        assert storage.count() == 0
        assert storage.get_default_page_id() is None

    def test_datetime_serialization(self, storage, sample_schedule):
        """Test that datetime fields are properly serialized/deserialized."""
        storage.create(sample_schedule)

        # Update to set updated_at
        storage.update(sample_schedule.id, {"enabled": False})

        # Reload from file
        storage2 = ScheduleStorage(storage_file=storage.storage_file)
        retrieved = storage2.get(sample_schedule.id)

        assert isinstance(retrieved.created_at, datetime)
        assert isinstance(retrieved.updated_at, datetime)

    # ── New coverage gap tests ────────────────────────────────────────────────

    def test_init_default_path_uses_data_directory(self):
        """Default constructor should resolve storage_file to data/schedules.json."""
        storage = ScheduleStorage()
        assert storage.storage_file.name == "schedules.json"
        assert storage.storage_file.parent.name == "data"

    def test_init_fresh_when_file_absent(self, tmp_path):
        """Storage initialises to empty state when the file does not exist yet."""
        storage = ScheduleStorage(storage_file=str(tmp_path / "nonexistent.json"))
        assert storage.count() == 0
        assert storage.get_default_page_id() is None

    def test_list_all_wildcard_returns_all_boards(self, temp_storage_file):
        """list_all('*') returns schedules from every board_id."""
        storage = ScheduleStorage(storage_file=temp_storage_file)
        s1 = ScheduleEntry(
            board_id="board-a",
            page_id="p1",
            start_time="09:00",
            end_time="12:00",
            day_pattern="all",
            enabled=True,
        )
        s2 = ScheduleEntry(
            board_id="board-b",
            page_id="p2",
            start_time="12:00",
            end_time="17:00",
            day_pattern="all",
            enabled=True,
        )
        storage.create(s1)
        storage.create(s2)

        assert len(storage.list_all(board_id="board-a")) == 1
        assert len(storage.list_all(board_id="*")) == 2

    def test_create_raises_on_invalid_config(self, storage):
        """create() raises ValueError when validate_config() finds errors."""
        # day_pattern=custom with custom_days=None passes Pydantic but fails validate_config
        invalid = ScheduleEntry(
            page_id="p1",
            start_time="09:00",
            end_time="17:00",
            day_pattern="custom",
            custom_days=None,
            enabled=True,
        )
        with pytest.raises(ValueError, match="Invalid schedule configuration"):
            storage.create(invalid)

    def test_update_raises_on_invalid_config(self, storage, sample_schedule):
        """update() raises ValueError when the resulting state fails validate_config()."""
        storage.create(sample_schedule)
        # Switching to custom pattern without custom_days makes config invalid
        with pytest.raises(ValueError, match="Invalid schedule configuration"):
            storage.update(sample_schedule.id, {"day_pattern": "custom"})

    def test_load_backfills_missing_board_id(self, temp_storage_file):
        """Schedules stored without board_id are assigned DEFAULT_BOARD_ID on load."""
        data = {
            "schedules": [
                {
                    "id": "legacy-id",
                    "page_id": "p1",
                    "start_time": "09:00",
                    "end_time": "17:00",
                    "day_pattern": "all",
                    "enabled": True,
                    "created_at": "2024-01-01T00:00:00+00:00",
                    "updated_at": None,
                    # board_id intentionally absent
                }
            ],
            "default_page_id": None,
            "default_page_by_board": {},
        }
        with open(temp_storage_file, "w") as f:
            json.dump(data, f)

        storage = ScheduleStorage(storage_file=temp_storage_file)
        assert storage.count() == 1
        assert storage.get("legacy-id").board_id == DEFAULT_BOARD_ID

    def test_load_skips_corrupt_schedule_entry(self, temp_storage_file):
        """A malformed entry in the JSON file is skipped; valid entries still load."""
        data = {
            "schedules": [
                {
                    "id": "good-id",
                    "page_id": "p1",
                    "start_time": "09:00",
                    "end_time": "17:00",
                    "day_pattern": "all",
                    "enabled": True,
                    "created_at": "2024-01-01T00:00:00+00:00",
                },
                {"id": "bad-id", "broken_field": True},  # Missing required fields
            ],
            "default_page_id": None,
            "default_page_by_board": {},
        }
        with open(temp_storage_file, "w") as f:
            json.dump(data, f)

        storage = ScheduleStorage(storage_file=temp_storage_file)
        assert storage.count() == 1
        assert storage.get("good-id") is not None
        assert storage.get("bad-id") is None

    def test_save_raises_on_io_error(self, storage, monkeypatch):
        """_save() propagates IOError when the file cannot be written."""
        original_open = builtins.open

        def failing_open(path, mode="r", **kwargs):
            if "w" in str(mode):
                raise OSError("disk full")
            return original_open(path, mode, **kwargs)

        monkeypatch.setattr(builtins, "open", failing_open)

        new_schedule = ScheduleEntry(
            page_id="p2",
            start_time="18:00",
            end_time="22:00",
            day_pattern="all",
            enabled=True,
        )
        with pytest.raises(IOError):
            storage.create(new_schedule)
