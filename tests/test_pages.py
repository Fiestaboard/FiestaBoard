"""Tests for pages module (models, storage, service, API)."""

import json
import os
import tempfile
from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest

from src.displays.service import DisplayResult
from src.pages.models import LineMetadata, Page, PageCreate, PageUpdate, RowConfig
from src.pages.service import DeleteResult, PageService
from src.pages.storage import (
    CURRENT_SCHEMA_VERSION,
    PageStorage,
    _extract_alignment_from_line,
    _migrate_v0_to_v1,
    _migrate_v2_to_v3,
    _rewrite_plugin_id_references,
)


class TestPageModels:
    """Tests for Page and related models."""

    def test_page_single_valid(self):
        """Test valid single-type page."""
        page = Page(name="Weather Page", type="single", display_type="weather")
        assert page.is_valid()
        assert page.type == "single"
        assert page.display_type == "weather"

    def test_page_single_missing_display_type(self):
        """Test single page without display_type is invalid."""
        page = Page(name="Bad Page", type="single")
        errors = page.validate_config()
        assert "display_type" in errors[0].lower()

    def test_page_composite_valid(self):
        """Test valid composite page."""
        page = Page(
            name="Composite Page",
            type="composite",
            rows=[
                RowConfig(source="weather", row_index=0, target_row=0),
                RowConfig(source="datetime", row_index=0, target_row=1),
            ],
        )
        assert page.is_valid()

    def test_page_composite_missing_rows(self):
        """Test composite page without rows is invalid."""
        page = Page(name="Bad Page", type="composite")
        errors = page.validate_config()
        assert "row" in errors[0].lower()

    def test_page_composite_duplicate_targets(self):
        """Test composite page with duplicate target rows is invalid."""
        page = Page(
            name="Bad Page",
            type="composite",
            rows=[
                RowConfig(source="weather", row_index=0, target_row=0),
                RowConfig(source="datetime", row_index=0, target_row=0),  # Duplicate!
            ],
        )
        errors = page.validate_config()
        assert "duplicate" in errors[0].lower()

    def test_page_template_valid(self):
        """Test valid template page."""
        page = Page(name="Template Page", type="template", template=["Line 1", "Line 2", "", "", "", ""])
        assert page.is_valid()

    def test_page_template_missing_template(self):
        """Test template page without template is invalid."""
        page = Page(name="Bad Page", type="template")
        errors = page.validate_config()
        assert "template" in errors[0].lower()

    def test_page_generates_id(self):
        """Test that page auto-generates an ID."""
        page = Page(name="Test", type="single", display_type="weather")
        assert page.id is not None
        assert len(page.id) > 0

    def test_page_duration_defaults(self):
        """Test default duration is 300 seconds."""
        page = Page(name="Test", type="single", display_type="weather")
        assert page.duration_seconds == 300

    def test_row_config_valid(self):
        """Test valid row config."""
        config = RowConfig(source="weather", row_index=0, target_row=5)
        assert config.source == "weather"
        assert config.row_index == 0
        assert config.target_row == 5


class TestPageStorage:
    """Tests for PageStorage."""

    @pytest.fixture
    def temp_storage_file(self):
        """Create a temporary storage file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"pages": []}')
            yield f.name
        os.unlink(f.name)

    @pytest.fixture
    def storage(self, temp_storage_file):
        """Create a storage instance with temp file."""
        return PageStorage(storage_file=temp_storage_file)

    def test_create_page(self, storage):
        """Test creating a page."""
        page = Page(name="Test", type="single", display_type="weather")
        created = storage.create(page)

        assert created.id == page.id
        assert created.name == "Test"
        assert storage.count() == 1

    def test_create_duplicate_id_raises(self, storage):
        """Test creating page with duplicate ID raises."""
        page = Page(name="Test", type="single", display_type="weather")
        storage.create(page)

        with pytest.raises(ValueError, match="already exists"):
            storage.create(page)

    def test_get_page(self, storage):
        """Test getting a page by ID."""
        page = Page(name="Test", type="single", display_type="weather")
        storage.create(page)

        retrieved = storage.get(page.id)
        assert retrieved is not None
        assert retrieved.name == "Test"

    def test_get_nonexistent_returns_none(self, storage):
        """Test getting nonexistent page returns None."""
        result = storage.get("nonexistent")
        assert result is None

    def test_list_all(self, storage):
        """Test listing all pages."""
        page1 = Page(name="Page 1", type="single", display_type="weather")
        page2 = Page(name="Page 2", type="single", display_type="datetime")
        storage.create(page1)
        storage.create(page2)

        pages = storage.list_all()
        assert len(pages) == 2

    def test_list_all_alphabetical_order(self, storage):
        """Test that list_all returns pages sorted alphabetically by name."""
        page_z = Page(name="Zebra Page", type="single", display_type="weather")
        page_a = Page(name="Alpha Page", type="single", display_type="datetime")
        page_m = Page(name="Middle Page", type="template", template=["Hi", "", "", "", "", ""])
        storage.create(page_z)
        storage.create(page_a)
        storage.create(page_m)

        pages = storage.list_all()
        names = [p.name for p in pages]
        assert names == ["Alpha Page", "Middle Page", "Zebra Page"]

    def test_list_all_alphabetical_case_insensitive(self, storage):
        """Test that list_all sorts case-insensitively."""
        page_upper = Page(name="Bravo", type="single", display_type="weather")
        page_lower = Page(name="alpha", type="single", display_type="datetime")
        page_mixed = Page(name="Charlie", type="single", display_type="weather")
        storage.create(page_upper)
        storage.create(page_lower)
        storage.create(page_mixed)

        pages = storage.list_all()
        names = [p.name for p in pages]
        assert names == ["alpha", "Bravo", "Charlie"]

    def test_update_page(self, storage):
        """Test updating a page."""
        page = Page(name="Original", type="single", display_type="weather")
        storage.create(page)

        updated = storage.update(page.id, {"name": "Updated"})
        assert updated.name == "Updated"
        assert updated.updated_at is not None

    def test_update_nonexistent_returns_none(self, storage):
        """Test updating nonexistent page returns None."""
        result = storage.update("nonexistent", {"name": "Test"})
        assert result is None

    def test_update_can_clear_transition_strategy(self, storage):
        """Explicit None must clear a nullable transition override (issue #1306)."""
        page = storage.create(
            Page(
                name="P",
                type="template",
                template=["hi", "", "", "", "", ""],
                transition_strategy="column",
                transition_interval_ms=120,
                transition_step_size=2,
            )
        )
        assert page.transition_strategy == "column"

        updated = storage.update(
            page.id,
            {
                "transition_strategy": None,
                "transition_interval_ms": None,
                "transition_step_size": None,
            },
        )
        assert updated.transition_strategy is None
        assert updated.transition_interval_ms is None
        assert updated.transition_step_size is None

    def test_update_can_clear_line_metadata(self, storage):
        """Explicit None must clear nullable line_metadata (issue #1306)."""
        page = storage.create(
            Page(
                name="P",
                type="template",
                template=["hi", "", "", "", "", ""],
                line_metadata=[
                    LineMetadata(alignment="center", wrap=False),
                    LineMetadata(),
                    LineMetadata(),
                    LineMetadata(),
                    LineMetadata(),
                    LineMetadata(),
                ],
            )
        )
        assert page.line_metadata is not None

        updated = storage.update(page.id, {"line_metadata": None})
        assert updated.line_metadata is None

    def test_update_does_not_clear_demo_plugin_id(self, storage):
        """demo_plugin_id is internally managed, not clearable via update().

        It's nullable on Page but absent from PageUpdate (set only at page
        creation), so it is intentionally excluded from ``nullable_fields`` —
        an explicit None update must be ignored rather than clear the tag.
        """
        page = storage.create(
            Page(
                name="P",
                type="single",
                display_type="weather",
                demo_plugin_id="weather",
            )
        )
        assert page.demo_plugin_id == "weather"

        updated = storage.update(page.id, {"demo_plugin_id": None})
        assert updated.demo_plugin_id == "weather"

    def test_update_ignores_none_for_non_nullable_fields(self, storage):
        """None for required/non-nullable fields must not overwrite the value."""
        page = storage.create(Page(name="Original", type="single", display_type="weather"))

        # `name` is required (min_length=1) — explicit None must be ignored,
        # not blow up validation. This is the existing protective behaviour
        # the `nullable_fields` allowset preserves.
        updated = storage.update(page.id, {"name": None})
        assert updated.name == "Original"

    def test_delete_page(self, storage):
        """Test deleting a page."""
        page = Page(name="Test", type="single", display_type="weather")
        storage.create(page)

        result = storage.delete(page.id)
        assert result is True
        assert storage.get(page.id) is None

    def test_delete_nonexistent_returns_false(self, storage):
        """Test deleting nonexistent page returns False."""
        result = storage.delete("nonexistent")
        assert result is False

    def test_persistence(self, temp_storage_file):
        """Test that pages persist across storage instances."""
        # Create first storage and add page
        storage1 = PageStorage(storage_file=temp_storage_file)
        page = Page(name="Persistent", type="single", display_type="weather")
        storage1.create(page)

        # Create second storage and verify page exists
        storage2 = PageStorage(storage_file=temp_storage_file)
        retrieved = storage2.get(page.id)

        assert retrieved is not None
        assert retrieved.name == "Persistent"


class TestLineMetadataModel:
    """Tests for LineMetadata model."""

    def test_default_values(self):
        meta = LineMetadata()
        assert meta.alignment == "left"
        assert meta.wrap is False

    def test_explicit_values(self):
        meta = LineMetadata(alignment="center", wrap=True)
        assert meta.alignment == "center"
        assert meta.wrap is True

    def test_round_trip(self):
        meta = LineMetadata(alignment="right", wrap=True)
        dumped = meta.model_dump()
        restored = LineMetadata(**dumped)
        assert restored.alignment == "right"
        assert restored.wrap is True

    def test_page_with_line_metadata(self):
        page = Page(
            name="Test",
            type="template",
            template=["HELLO", "WORLD", "", "", "", ""],
            line_metadata=[
                LineMetadata(alignment="center", wrap=False),
                LineMetadata(alignment="right", wrap=True),
                LineMetadata(),
                LineMetadata(),
                LineMetadata(),
                LineMetadata(),
            ],
        )
        assert page.is_valid()
        assert page.line_metadata[0].alignment == "center"
        assert page.line_metadata[1].wrap is True


class TestExtractAlignmentFromLine:
    """Tests for the storage-level prefix extractor used by migration."""

    def test_no_prefix(self):
        align, wrap, content = _extract_alignment_from_line("Hello")
        assert align == "left"
        assert wrap is False
        assert content == "Hello"

    def test_center(self):
        align, _wrap, content = _extract_alignment_from_line("{center}Hello")
        assert align == "center"
        assert content == "Hello"

    def test_wrap_and_right(self):
        align, wrap, content = _extract_alignment_from_line("{wrap}{right}Hello")
        assert align == "right"
        assert wrap is True
        assert content == "Hello"

    def test_wrap_only(self):
        align, wrap, content = _extract_alignment_from_line("{wrap}Hello")
        assert align == "left"
        assert wrap is True
        assert content == "Hello"

    def test_case_insensitive(self):
        align, _wrap, content = _extract_alignment_from_line("{CENTER}Hello")
        assert align == "center"
        assert content == "Hello"


class TestMigrateV0ToV1:
    """Tests for v0->v1 migration logic."""

    def test_template_page_gets_metadata(self):
        pages = [
            {
                "id": "1",
                "type": "template",
                "template": ["{center}HELLO", "{wrap}{right}WORLD", "PLAIN"],
            }
        ]
        count = _migrate_v0_to_v1(pages)
        assert count == 1
        assert pages[0]["template"] == ["HELLO", "WORLD", "PLAIN"]
        assert pages[0]["line_metadata"] == [
            {"alignment": "center", "wrap": False},
            {"alignment": "right", "wrap": True},
            {"alignment": "left", "wrap": False},
        ]

    def test_non_template_page_skipped(self):
        pages = [{"id": "1", "type": "single", "display_type": "weather"}]
        count = _migrate_v0_to_v1(pages)
        assert count == 0
        assert "line_metadata" not in pages[0]

    def test_already_migrated_skipped(self):
        pages = [
            {
                "id": "1",
                "type": "template",
                "template": ["HELLO"],
                "line_metadata": [{"alignment": "left", "wrap": False}],
            }
        ]
        count = _migrate_v0_to_v1(pages)
        assert count == 0

    def test_empty_template(self):
        pages = [{"id": "1", "type": "template", "template": []}]
        count = _migrate_v0_to_v1(pages)
        assert count == 0


class TestSchemaVersioning:
    """Tests for PageStorage schema versioning and migration."""

    @pytest.fixture
    def temp_storage_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            yield f.name
        os.unlink(f.name)
        backup = f.name + ".v0_backup"
        if os.path.exists(backup):
            os.unlink(backup)

    def test_new_file_gets_schema_version(self, temp_storage_file):
        """A fresh storage file written by _save() should contain schema_version."""
        storage = PageStorage(storage_file=temp_storage_file)
        page = Page(name="Test", type="single", display_type="weather")
        storage.create(page)

        with open(temp_storage_file) as f:
            data = json.load(f)
        assert data["schema_version"] == CURRENT_SCHEMA_VERSION

    def test_v0_file_is_migrated(self, temp_storage_file):
        """A v0 file (no schema_version) gets migrated on load."""
        with open(temp_storage_file, "w") as f:
            json.dump(
                {
                    "pages": [
                        {
                            "id": "p1",
                            "name": "My Page",
                            "type": "template",
                            "device_type": "flagship",
                            "template": [
                                "{center}HELLO",
                                "{wrap}WORLD",
                                "",
                                "",
                                "",
                                "",
                            ],
                            "duration_seconds": 300,
                            "created_at": datetime.now(UTC).isoformat(),
                        }
                    ]
                },
                f,
            )

        storage = PageStorage(storage_file=temp_storage_file)
        page = storage.get("p1")
        assert page is not None
        assert page.template == ["HELLO", "WORLD", "", "", "", ""]
        assert page.line_metadata is not None
        assert page.line_metadata[0].alignment == "center"
        assert page.line_metadata[0].wrap is False
        assert page.line_metadata[1].alignment == "left"
        assert page.line_metadata[1].wrap is True

        # File should now contain schema_version
        with open(temp_storage_file) as f:
            data = json.load(f)
        assert data["schema_version"] == CURRENT_SCHEMA_VERSION

    def test_v0_backup_created(self, temp_storage_file):
        """Migration creates a .v0_backup file."""
        with open(temp_storage_file, "w") as f:
            json.dump(
                {
                    "pages": [
                        {
                            "id": "p1",
                            "name": "My Page",
                            "type": "template",
                            "device_type": "flagship",
                            "template": ["{right}ABC", "", "", "", "", ""],
                            "duration_seconds": 300,
                            "created_at": datetime.now(UTC).isoformat(),
                        }
                    ]
                },
                f,
            )

        PageStorage(storage_file=temp_storage_file)
        backup_path = temp_storage_file + ".v0_backup"
        assert os.path.exists(backup_path)

    def test_already_current_version_no_migration(self, temp_storage_file):
        """A file at CURRENT_SCHEMA_VERSION should not be migrated."""
        with open(temp_storage_file, "w") as f:
            json.dump(
                {
                    "schema_version": CURRENT_SCHEMA_VERSION,
                    "pages": [
                        {
                            "id": "p1",
                            "name": "My Page",
                            "type": "template",
                            "device_type": "flagship",
                            "template": ["HELLO", "", "", "", "", ""],
                            "line_metadata": [
                                {"alignment": "center", "wrap": False},
                                {"alignment": "left", "wrap": False},
                                {"alignment": "left", "wrap": False},
                                {"alignment": "left", "wrap": False},
                                {"alignment": "left", "wrap": False},
                                {"alignment": "left", "wrap": False},
                            ],
                            "duration_seconds": 300,
                            "created_at": datetime.now(UTC).isoformat(),
                        }
                    ],
                },
                f,
            )

        storage = PageStorage(storage_file=temp_storage_file)
        page = storage.get("p1")
        assert page.template == ["HELLO", "", "", "", "", ""]
        assert page.line_metadata[0].alignment == "center"


class TestMigrateV2ToV3:
    """Tests for v2->v3 plugin id rename migration."""

    def test_template_variable_references_rewritten(self):
        pages = [
            {
                "id": "1",
                "type": "template",
                "template": [
                    "{{baywheels.station_name}}",
                    "E:{{baywheels.electric_bikes}} C:{{baywheels.classic_bikes}}",
                    "{{baywheels.stations.0.electric_bikes}}",
                    "no vars here",
                ],
            }
        ]
        count = _migrate_v2_to_v3(pages)
        assert count == 1
        assert pages[0]["template"] == [
            "{{lyft_bike_share.station_name}}",
            "E:{{lyft_bike_share.electric_bikes}} C:{{lyft_bike_share.classic_bikes}}",
            "{{lyft_bike_share.stations.0.electric_bikes}}",
            "no vars here",
        ]

    def test_formula_references_rewritten(self):
        pages = [
            {
                "id": "1",
                "type": "template",
                "template": [
                    "{{= IF(baywheels.electric_bikes > 0, baywheels.electric_bikes, 'NO') }}",
                ],
            }
        ]
        count = _migrate_v2_to_v3(pages)
        assert count == 1
        assert pages[0]["template"] == [
            "{{= IF(lyft_bike_share.electric_bikes > 0, lyft_bike_share.electric_bikes, 'NO') }}",
        ]

    def test_single_page_display_type_rewritten(self):
        pages = [{"id": "1", "type": "single", "display_type": "baywheels"}]
        count = _migrate_v2_to_v3(pages)
        assert count == 1
        assert pages[0]["display_type"] == "lyft_bike_share"

    def test_composite_row_source_rewritten(self):
        pages = [
            {
                "id": "1",
                "type": "composite",
                "rows": [
                    {"source": "baywheels", "row_index": 0, "target_row": 0},
                    {"source": "weather", "row_index": 0, "target_row": 1},
                ],
            }
        ]
        count = _migrate_v2_to_v3(pages)
        assert count == 1
        assert pages[0]["rows"][0]["source"] == "lyft_bike_share"
        assert pages[0]["rows"][1]["source"] == "weather"

    def test_demo_plugin_id_rewritten(self):
        pages = [
            {
                "id": "1",
                "type": "single",
                "display_type": "lyft_bike_share",
                "demo_plugin_id": "baywheels",
            }
        ]
        count = _migrate_v2_to_v3(pages)
        assert count == 1
        assert pages[0]["demo_plugin_id"] == "lyft_bike_share"

    def test_unrelated_pages_not_modified(self):
        pages = [
            {
                "id": "1",
                "type": "template",
                "template": ["{{weather.temperature}}", "static text"],
            },
            {
                "id": "2",
                "type": "single",
                "display_type": "weather",
            },
        ]
        count = _migrate_v2_to_v3(pages)
        assert count == 0
        assert pages[0]["template"] == ["{{weather.temperature}}", "static text"]
        assert pages[1]["display_type"] == "weather"

    def test_does_not_match_id_suffix(self):
        """An identifier that merely *ends* with an old id must not be rewritten."""
        pages = [
            {
                "id": "1",
                "type": "template",
                "template": ["{{mybaywheels.foo}}", "{{baywheelsx.foo}}"],
            }
        ]
        count = _migrate_v2_to_v3(pages)
        assert count == 0
        assert pages[0]["template"] == ["{{mybaywheels.foo}}", "{{baywheelsx.foo}}"]

    def test_idempotent(self):
        pages = [
            {
                "id": "1",
                "type": "template",
                "template": ["{{lyft_bike_share.station_name}}"],
            }
        ]
        count = _migrate_v2_to_v3(pages)
        assert count == 0

    def test_rewrite_helper_returns_count(self):
        out, n = _rewrite_plugin_id_references("{{baywheels.x}} and {{baywheels.y}} but not {{weather.t}}")
        assert n == 2
        assert out == "{{lyft_bike_share.x}} and {{lyft_bike_share.y}} but not {{weather.t}}"

    def test_rewrite_helper_empty_input(self):
        assert _rewrite_plugin_id_references("") == ("", 0)
        assert _rewrite_plugin_id_references("no dots no rename") == ("no dots no rename", 0)


class TestPageStorageV2ToV3Integration:
    """End-to-end test that a v2 pages file is migrated on load."""

    @pytest.fixture
    def temp_storage_file(self):
        import glob

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            yield f.name
        os.unlink(f.name)
        # Migration may create per-source-version backup files (.vN_backup)
        # alongside the storage file; sweep them all so the suite stays tidy
        # as CURRENT_SCHEMA_VERSION grows.
        for backup in glob.glob(f.name + ".v*_backup"):
            os.unlink(backup)

    def test_v2_file_migrated_to_v3(self, temp_storage_file):
        with open(temp_storage_file, "w") as f:
            json.dump(
                {
                    "schema_version": 2,
                    "pages": [
                        {
                            "id": "p1",
                            "name": "Bikes",
                            "type": "template",
                            "device_type": "flagship",
                            "template": [
                                "{{baywheels.station_name}}",
                                "E:{{baywheels.electric_bikes}}",
                                "",
                                "",
                                "",
                                "",
                            ],
                            "line_metadata": [{"alignment": "center", "wrap": False}] * 6,
                            "duration_seconds": 300,
                            "demo_plugin_id": None,
                            "created_at": datetime.now(UTC).isoformat(),
                        }
                    ],
                },
                f,
            )

        storage = PageStorage(storage_file=temp_storage_file)
        page = storage.get("p1")
        assert page is not None
        assert page.template[0] == "{{lyft_bike_share.station_name}}"
        assert page.template[1] == "E:{{lyft_bike_share.electric_bikes}}"

        with open(temp_storage_file) as f:
            data = json.load(f)
        assert data["schema_version"] == CURRENT_SCHEMA_VERSION


class TestPageService:
    """Tests for PageService."""

    @pytest.fixture
    def temp_storage_file(self):
        """Create a temporary storage file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"pages": []}')
            yield f.name
        os.unlink(f.name)

    @pytest.fixture
    def service(self, temp_storage_file):
        """Create a page service with temp storage."""
        storage = PageStorage(storage_file=temp_storage_file)
        return PageService(storage=storage)

    def test_create_page(self, service):
        """Test creating a page via service."""
        data = PageCreate(name="Test", type="single", display_type="weather")
        page = service.create_page(data)

        assert page.name == "Test"
        assert page.type == "single"

    def test_list_pages(self, service):
        """Test listing pages via service."""
        service.create_page(PageCreate(name="Page 1", type="single", display_type="weather"))
        service.create_page(PageCreate(name="Page 2", type="single", display_type="datetime"))

        pages = service.list_pages()
        assert len(pages) == 2

    def test_update_page(self, service):
        """Test updating a page via service."""
        page = service.create_page(PageCreate(name="Original", type="single", display_type="weather"))

        updated = service.update_page(page.id, PageUpdate(name="Updated"))
        assert updated.name == "Updated"

    def test_delete_page(self, service):
        """Test deleting a page via service (when multiple pages exist)."""
        # Create two pages so we're not deleting the last one
        page1 = service.create_page(PageCreate(name="Page 1", type="single", display_type="weather"))
        page2 = service.create_page(PageCreate(name="Page 2", type="single", display_type="datetime"))

        result = service.delete_page(page1.id)
        assert result.deleted is True
        assert result.default_page_created is False
        assert result.new_page_id is None
        assert service.get_page(page1.id) is None
        # page2 should still exist
        assert service.get_page(page2.id) is not None

    def test_delete_last_page_creates_default(self, service):
        """Test deleting the last page creates a default welcome page."""
        # Create a single page
        page = service.create_page(PageCreate(name="Only Page", type="single", display_type="weather"))

        # Delete it - should create a default page
        result = service.delete_page(page.id)

        assert result.deleted is True
        assert result.default_page_created is True
        assert result.new_page_id is not None

        # Original page should be gone
        assert service.get_page(page.id) is None

        # Default page should exist
        default_page = service.get_page(result.new_page_id)
        assert default_page is not None
        assert default_page.name == "Welcome"
        assert default_page.type == "template"
        assert default_page.template is not None

        # There should be exactly 1 page
        pages = service.list_pages()
        assert len(pages) == 1

    def test_delete_last_note_page_creates_note_default(self, service):
        """Deleting the last note-board page should create a note-sized default.

        Regression test for issue #1307: ``_create_default_page`` used to
        hardcode the 6-line flagship template, producing a structurally
        invalid page on note (3x15) boards.
        """
        note_page = service.storage.create(
            Page(name="only", type="template", device_type="note", template=["a", "b", "c"])
        )

        result = service.delete_page(note_page.id)
        assert result.default_page_created is True

        new_page = service.get_page(result.new_page_id)
        assert new_page is not None
        assert new_page.device_type == "note"
        assert len(new_page.template) == 3

    def test_delete_nonexistent_page(self, service):
        """Test deleting a page that doesn't exist."""
        result = service.delete_page("nonexistent-id")
        assert result.deleted is False
        assert result.default_page_created is False

    @patch("src.pages.service.get_display_service")
    def test_render_single_page(self, mock_get_display, service):
        """Test rendering a single-source page."""
        mock_display_service = Mock()
        mock_display_service.get_display.return_value = DisplayResult(
            display_type="weather", formatted="Sunny, 72F\nSan Francisco", raw={"temp": 72}, available=True
        )
        mock_get_display.return_value = mock_display_service

        page = service.create_page(PageCreate(name="Weather", type="single", display_type="weather"))
        result = service.render_page(page)

        assert result.available is True
        assert "Sunny" in result.formatted

    @patch("src.pages.service.get_display_service")
    def test_render_composite_page(self, mock_get_display, service):
        """Test rendering a composite page."""
        mock_display_service = Mock()

        def mock_get_display_fn(display_type, board=None):
            if display_type == "weather":
                return DisplayResult(
                    display_type="weather", formatted="Sunny Line 1\nSunny Line 2", raw={}, available=True
                )
            if display_type == "datetime":
                return DisplayResult(
                    display_type="datetime", formatted="Monday Dec 25\n10:30 AM", raw={}, available=True
                )
            return DisplayResult(display_type=display_type, formatted="", raw={}, available=False)

        mock_display_service.get_display.side_effect = mock_get_display_fn
        mock_get_display.return_value = mock_display_service

        page = service.create_page(
            PageCreate(
                name="Composite",
                type="composite",
                rows=[
                    RowConfig(source="weather", row_index=0, target_row=0),
                    RowConfig(source="datetime", row_index=0, target_row=2),
                ],
            )
        )
        result = service.render_page(page)

        assert result.available is True
        lines = result.formatted.split("\n")
        assert "Sunny" in lines[0]
        assert "Monday" in lines[2]

    def test_render_template_page(self, service):
        """Test rendering a template page."""
        page = service.create_page(
            PageCreate(name="Template", type="template", template=["Hello World", "Line 2", "", "", "", ""])
        )
        result = service.render_page(page)

        assert result.available is True
        assert "Hello World" in result.formatted

    @patch("src.pages.service.get_display_service")
    def test_preview_page_uses_cache(self, mock_get_display, service):
        """Test that preview_page uses cache on subsequent calls."""
        mock_display_service = Mock()
        mock_display_service.get_display.return_value = DisplayResult(
            display_type="weather", formatted="Sunny, 72F", raw={"temp": 72}, available=True
        )
        mock_get_display.return_value = mock_display_service

        page = service.create_page(PageCreate(name="Weather", type="single", display_type="weather"))

        # First call should render
        result1 = service.preview_page(page.id)
        assert result1.available is True
        assert mock_display_service.get_display.call_count == 1

        # Second call should use cache (no additional render)
        result2 = service.preview_page(page.id)
        assert result2.available is True
        assert result2.formatted == result1.formatted
        assert mock_display_service.get_display.call_count == 1  # Still 1!

    @patch("src.pages.service.get_display_service")
    def test_preview_page_force_refresh(self, mock_get_display, service):
        """Test that force_refresh bypasses cache."""
        mock_display_service = Mock()
        mock_display_service.get_display.return_value = DisplayResult(
            display_type="weather", formatted="Sunny, 72F", raw={"temp": 72}, available=True
        )
        mock_get_display.return_value = mock_display_service

        page = service.create_page(PageCreate(name="Weather", type="single", display_type="weather"))

        # First call
        result1 = service.preview_page(page.id)
        assert result1.available is True
        assert mock_display_service.get_display.call_count == 1

        # Second call with force_refresh=True should render again
        result2 = service.preview_page(page.id, force_refresh=True)
        assert result2.available is True
        assert mock_display_service.get_display.call_count == 2  # Rendered again!

    @patch("src.pages.service.get_display_service")
    def test_update_page_invalidates_cache(self, mock_get_display, service):
        """Test that updating a page invalidates its cache."""
        mock_display_service = Mock()
        mock_display_service.get_display.return_value = DisplayResult(
            display_type="weather", formatted="Sunny, 72F", raw={"temp": 72}, available=True
        )
        mock_get_display.return_value = mock_display_service

        page = service.create_page(PageCreate(name="Weather", type="single", display_type="weather"))

        # First preview - should cache
        service.preview_page(page.id)
        assert mock_display_service.get_display.call_count == 1

        # Second preview - should use cache
        service.preview_page(page.id)
        assert mock_display_service.get_display.call_count == 1

        # Update the page
        service.update_page(page.id, PageUpdate(name="Updated Weather"))

        # Third preview - should re-render (cache was invalidated)
        service.preview_page(page.id)
        assert mock_display_service.get_display.call_count == 2

    def test_get_cache_stats(self, service):
        """Test getting cache statistics."""
        stats = service.get_cache_stats()

        assert "cache_size" in stats
        assert "cached_pages" in stats
        assert "ttl_seconds" in stats
        assert stats["cache_size"] == 0
        assert stats["cached_pages"] == []

    @patch("src.pages.service.get_display_service")
    def test_cache_stats_after_preview(self, mock_get_display, service):
        """Test cache statistics after previewing pages."""
        mock_display_service = Mock()
        mock_display_service.get_display.return_value = DisplayResult(
            display_type="weather", formatted="Sunny, 72F", raw={"temp": 72}, available=True
        )
        mock_get_display.return_value = mock_display_service

        page1 = service.create_page(PageCreate(name="Weather", type="single", display_type="weather"))
        page2 = service.create_page(PageCreate(name="Datetime", type="single", display_type="datetime"))

        # Preview both pages
        service.preview_page(page1.id)
        service.preview_page(page2.id)

        stats = service.get_cache_stats()
        assert stats["cache_size"] == 2
        assert page1.id in stats["cached_pages"]
        assert page2.id in stats["cached_pages"]

    @patch("src.plugins.registry.get_plugin_registry")
    @patch("src.pages.service.get_template_engine")
    def test_preview_pages_batch_shares_context(self, mock_get_engine, mock_get_registry, service):
        """Test that batch preview builds template context once per device type."""
        mock_engine = Mock()
        mock_engine.render_lines.return_value = "Hello World\n\n\n\n\n"
        mock_get_engine.return_value = mock_engine

        mock_registry = Mock()
        mock_registry.build_template_contexts_for.return_value = {"flagship": {"weather": {"temp": 72}}}
        mock_get_registry.return_value = mock_registry

        # Create multiple template pages (all default to the flagship device)
        page1 = service.create_page(PageCreate(name="Page 1", type="template", template=["Hello", "", "", "", "", ""]))
        page2 = service.create_page(PageCreate(name="Page 2", type="template", template=["World", "", "", "", "", ""]))
        page3 = service.create_page(PageCreate(name="Page 3", type="template", template=["Test", "", "", "", "", ""]))

        # Batch preview all three
        results = service.preview_pages_batch([page1.id, page2.id, page3.id])

        assert len(results) == 3
        assert all(r is not None and r.available for r in results.values())

        # Context fan-out happens once for the single (flagship) device type,
        # not once per page.
        assert mock_registry.build_template_contexts_for.call_count == 1
        boards_arg = mock_registry.build_template_contexts_for.call_args.args[0]
        assert set(boards_arg) == {"flagship"}
        # But render_lines should be called three times (once per page)
        assert mock_engine.render_lines.call_count == 3

    @patch("src.pages.service.get_template_engine")
    def test_preview_pages_batch_uses_cache(self, mock_get_engine, service):
        """Test that batch preview uses cache for already-cached pages."""
        mock_engine = Mock()
        mock_engine._build_context.return_value = {}
        mock_engine.render_lines.return_value = "Rendered\n\n\n\n\n"
        mock_get_engine.return_value = mock_engine

        page1 = service.create_page(PageCreate(name="Page 1", type="template", template=["Hello", "", "", "", "", ""]))
        page2 = service.create_page(PageCreate(name="Page 2", type="template", template=["World", "", "", "", "", ""]))

        # Preview page1 first to populate cache
        service.preview_pages_batch([page1.id])
        assert mock_engine.render_lines.call_count == 1

        # Batch preview both - page1 should use cache, only page2 renders
        mock_engine.render_lines.reset_mock()
        mock_engine._build_context.reset_mock()
        results = service.preview_pages_batch([page1.id, page2.id])

        assert len(results) == 2
        assert mock_engine.render_lines.call_count == 1  # Only page2 rendered

    def test_preview_pages_batch_nonexistent_page(self, service):
        """Test that batch preview handles nonexistent pages."""
        results = service.preview_pages_batch(["nonexistent-id"])
        assert results["nonexistent-id"] is None


class TestPagesAPIEndpoints:
    """Tests for pages API endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        from fastapi.testclient import TestClient

        from src.api_server import app

        return TestClient(app)

    @pytest.fixture
    def mock_page_service(self):
        """Mock the page service."""
        with patch("src.api_server.get_page_service") as mock:
            mock_service = Mock()
            mock.return_value = mock_service
            yield mock_service

    def test_list_pages(self, client, mock_page_service):
        """Test GET /pages."""
        mock_page_service.list_pages.return_value = [
            Page(id="1", name="Page 1", type="single", display_type="weather"),
            Page(id="2", name="Page 2", type="single", display_type="datetime"),
        ]

        response = client.get("/pages")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["pages"]) == 2

    def test_create_page(self, client, mock_page_service):
        """Test POST /pages."""
        mock_page_service.create_page.return_value = Page(
            id="new-id", name="New Page", type="single", display_type="weather"
        )

        response = client.post("/pages", json={"name": "New Page", "type": "single", "display_type": "weather"})

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["page"]["name"] == "New Page"

    def test_get_page(self, client, mock_page_service):
        """Test GET /pages/{id}."""
        mock_page_service.get_page.return_value = Page(
            id="test-id", name="Test Page", type="single", display_type="weather"
        )

        response = client.get("/pages/test-id")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Page"

    def test_get_page_not_found(self, client, mock_page_service):
        """Test GET /pages/{id} with nonexistent ID."""
        mock_page_service.get_page.return_value = None

        response = client.get("/pages/nonexistent")

        assert response.status_code == 404

    def test_update_page(self, client, mock_page_service):
        """Test PUT /pages/{id}."""
        mock_page_service.update_page.return_value = Page(
            id="test-id", name="Updated Page", type="single", display_type="weather"
        )

        response = client.put("/pages/test-id", json={"name": "Updated Page"})

        assert response.status_code == 200
        data = response.json()
        assert data["page"]["name"] == "Updated Page"

    def test_delete_page(self, client, mock_page_service):
        """Test DELETE /pages/{id}."""
        mock_page_service.delete_page.return_value = DeleteResult(deleted=True)

        response = client.delete("/pages/test-id")

        assert response.status_code == 200
        data = response.json()
        assert "deleted" in data["message"]
        assert data["default_page_created"] is False

    def test_delete_last_page_creates_default(self, client, mock_page_service):
        """Test DELETE /pages/{id} when it's the last page."""
        mock_page_service.delete_page.return_value = DeleteResult(
            deleted=True, default_page_created=True, new_page_id="new-default-id"
        )

        response = client.delete("/pages/test-id")

        assert response.status_code == 200
        data = response.json()
        assert data["default_page_created"] is True
        assert data["new_page_id"] == "new-default-id"
        assert "welcome" in data["message"].lower()

    def test_delete_page_not_found(self, client, mock_page_service):
        """Test DELETE /pages/{id} with nonexistent ID."""
        mock_page_service.delete_page.return_value = DeleteResult(deleted=False)

        response = client.delete("/pages/nonexistent-id")

        assert response.status_code == 404

    def test_preview_page(self, client, mock_page_service):
        """Test POST /pages/{id}/preview."""
        mock_page_service.preview_page.return_value = DisplayResult(
            display_type="page:single", formatted="Preview Content\nLine 2", raw={"page_id": "test-id"}, available=True
        )

        response = client.post("/pages/test-id/preview")

        assert response.status_code == 200
        data = response.json()
        assert data["page_id"] == "test-id"
        assert "Preview Content" in data["message"]

    @patch("src.api_server.get_settings_service")
    def test_current_display_template_page(self, mock_settings, client, mock_page_service):
        """Test GET /pages/current-display returns raw template for template pages."""
        mock_svc = Mock()
        mock_svc.is_schedule_enabled.return_value = False
        mock_svc.get_active_page_id.return_value = "template-id"
        mock_settings.return_value = mock_svc

        mock_page_service.get_page.return_value = Page(
            id="template-id",
            name="My Template",
            type="template",
            device_type="flagship",
            template=["{{weather.temp}}", "Line 2", "", "", "", ""],
            line_metadata=[
                LineMetadata(alignment="center", wrap=False),
                LineMetadata(alignment="left", wrap=True),
                LineMetadata(alignment="left", wrap=False),
                LineMetadata(alignment="left", wrap=False),
                LineMetadata(alignment="left", wrap=False),
                LineMetadata(alignment="left", wrap=False),
            ],
        )

        response = client.get("/pages/current-display")

        assert response.status_code == 200
        data = response.json()
        assert data["page_id"] == "template-id"
        assert data["page_name"] == "My Template"
        assert data["page_type"] == "template"
        assert data["device_type"] == "flagship"
        assert data["template"] == ["{{weather.temp}}", "Line 2", "", "", "", ""]
        assert data["line_metadata"][0]["alignment"] == "center"
        assert data["line_metadata"][1]["wrap"] is True

    @patch("src.api_server.get_settings_service")
    def test_current_display_single_page(self, mock_settings, client, mock_page_service):
        """Test GET /pages/current-display returns rendered lines for non-template pages."""
        mock_svc = Mock()
        mock_svc.is_schedule_enabled.return_value = False
        mock_svc.get_active_page_id.return_value = "single-id"
        mock_settings.return_value = mock_svc

        mock_page_service.get_page.return_value = Page(
            id="single-id",
            name="Weather Page",
            type="single",
            display_type="weather",
        )
        mock_page_service.preview_page.return_value = DisplayResult(
            display_type="page:single",
            formatted="72°F Sunny\nHumidity 45%",
            raw={},
            available=True,
        )

        response = client.get("/pages/current-display")

        assert response.status_code == 200
        data = response.json()
        assert data["page_id"] == "single-id"
        assert data["page_name"] == "Weather Page"
        assert data["page_type"] == "single"
        assert data["template"] == ["72°F Sunny", "Humidity 45%"]
        assert data["line_metadata"] is None

    @patch("src.api_server.get_settings_service")
    def test_current_display_no_active_page(self, mock_settings, client, mock_page_service):
        """Test GET /pages/current-display returns 404 when no active page."""
        mock_svc = Mock()
        mock_svc.is_schedule_enabled.return_value = False
        mock_svc.get_active_page_id.return_value = None
        mock_settings.return_value = mock_svc

        response = client.get("/pages/current-display")

        assert response.status_code == 404

    @patch("src.api_server.get_collection_service")
    @patch("src.api_server.get_settings_service")
    def test_current_display_collection_resolved(self, mock_settings, mock_collection, client, mock_page_service):
        """Test GET /pages/current-display resolves collection to underlying page."""
        mock_svc = Mock()
        mock_svc.is_schedule_enabled.return_value = False
        mock_svc.get_active_page_id.return_value = "collection:abc"
        mock_settings.return_value = mock_svc

        mock_collection_svc = Mock()
        mock_collection_svc.resolve_page_id.return_value = "resolved-page-id"
        mock_collection.return_value = mock_collection_svc

        mock_page_service.get_page.return_value = Page(
            id="resolved-page-id",
            name="Resolved Page",
            type="template",
            device_type="flagship",
            template=["Hello", "World", "", "", "", ""],
        )

        response = client.get("/pages/current-display")

        assert response.status_code == 200
        data = response.json()
        assert data["page_id"] == "resolved-page-id"
        assert data["page_name"] == "Resolved Page"
        assert data["template"] == ["Hello", "World", "", "", "", ""]


class TestPageShare:
    """Unit tests for src/pages/share.py encode/decode logic."""

    def _make_template_page(self, **kwargs):
        defaults = {
            "name": "Morning Brief",
            "type": "template",
            "device_type": "flagship",
            "template": ["{{date_time.time}}", "{{weather.temperature}}°", "", "", "", ""],
            "line_metadata": [
                LineMetadata(alignment="center"),
                LineMetadata(alignment="left"),
                LineMetadata(),
                LineMetadata(),
                LineMetadata(),
                LineMetadata(),
            ],
            "duration_seconds": 60,
        }
        defaults.update(kwargs)
        return Page(**defaults)

    def test_encode_returns_string(self):
        from src.pages.share import encode_page

        page = self._make_template_page()
        s = encode_page(page)
        assert isinstance(s, str)
        assert len(s) > 0

    def test_round_trip_template_page(self):
        from src.pages.share import decode_page, encode_page

        page = self._make_template_page()
        s = encode_page(page)
        decoded = decode_page(s)

        assert decoded["name"] == page.name
        assert decoded["type"] == page.type
        assert decoded["device_type"] == page.device_type
        assert decoded["template"] == page.template
        assert decoded["duration_seconds"] == page.duration_seconds

    def test_round_trip_single_page(self):
        from src.pages.share import decode_page, encode_page

        page = Page(name="Weather", type="single", device_type="flagship", display_type="weather")
        decoded = decode_page(encode_page(page))
        assert decoded["name"] == "Weather"
        assert decoded["display_type"] == "weather"

    def test_round_trip_note_page(self):
        from src.pages.share import decode_page, encode_page

        page = Page(name="Note", type="template", device_type="note", template=["a", "b", "c"])
        decoded = decode_page(encode_page(page))
        assert decoded["device_type"] == "note"

    def test_excluded_fields_not_in_share_string(self):
        from src.pages.share import decode_page, encode_page

        page = self._make_template_page()
        decoded = decode_page(encode_page(page))
        assert "id" not in decoded
        assert "created_at" not in decoded
        assert "updated_at" not in decoded
        assert "demo_plugin_id" not in decoded

    def test_decode_malformed_base64_raises(self):
        from src.pages.share import decode_page

        with pytest.raises(ValueError, match="Invalid share string"):
            decode_page("not-valid-base64!!!")

    def test_decode_valid_base64_bad_json_raises(self):
        import base64

        from src.pages.share import decode_page

        bad = base64.urlsafe_b64encode(b"not json at all").decode().rstrip("=")
        with pytest.raises(ValueError, match="Invalid share string"):
            decode_page(bad)

    def test_decode_missing_version_raises(self):
        import base64

        from src.pages.share import decode_page

        payload = base64.urlsafe_b64encode(json.dumps({"page": {}}).encode()).decode().rstrip("=")
        with pytest.raises(ValueError, match="Invalid share string"):
            decode_page(payload)

    def test_decode_future_version_raises(self):
        import base64

        from src.pages.share import decode_page

        payload = base64.urlsafe_b64encode(json.dumps({"v": 999, "page": {}}).encode()).decode().rstrip("=")
        with pytest.raises(ValueError, match="requires FiestaBoard"):
            decode_page(payload)

    def test_decode_version_zero_raises(self):
        import base64

        from src.pages.share import decode_page

        payload = base64.urlsafe_b64encode(json.dumps({"v": 0, "page": {}}).encode()).decode().rstrip("=")
        with pytest.raises(ValueError):
            decode_page(payload)

    def test_share_string_url_safe(self):
        from src.pages.share import encode_page

        page = self._make_template_page()
        s = encode_page(page)
        # Must not contain +, /, or = (URL-unsafe characters)
        assert "+" not in s
        assert "/" not in s
        assert "=" not in s


class TestPageShareAPIEndpoints:
    """Tests for GET /pages/{id}/share, POST /pages/import/preview, POST /pages/import."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from src.api_server import app

        return TestClient(app)

    @pytest.fixture
    def mock_page_service(self):
        with patch("src.api_server.get_page_service") as mock:
            mock_service = Mock()
            mock.return_value = mock_service
            yield mock_service

    def _sample_page(self):
        return Page(
            id="abc-123",
            name="Test Page",
            type="template",
            device_type="flagship",
            template=["Hello", "World", "", "", "", ""],
        )

    def test_get_share_string(self, client, mock_page_service):
        mock_page_service.get_page.return_value = self._sample_page()
        response = client.get("/pages/abc-123/share")
        assert response.status_code == 200
        data = response.json()
        assert "share_string" in data
        assert isinstance(data["share_string"], str)
        assert len(data["share_string"]) > 0

    def test_get_share_string_not_found(self, client, mock_page_service):
        mock_page_service.get_page.return_value = None
        response = client.get("/pages/nonexistent/share")
        assert response.status_code == 404

    def test_get_share_string_content(self, client, mock_page_service):
        """Share string decodes back to the original page's content fields."""
        from src.pages.share import decode_page

        mock_page_service.get_page.return_value = self._sample_page()
        response = client.get("/pages/abc-123/share")
        decoded = decode_page(response.json()["share_string"])
        assert decoded["name"] == "Test Page"
        assert decoded["template"] == ["Hello", "World", "", "", "", ""]

    def test_import_page_success(self, client, mock_page_service):
        from src.pages.share import encode_page

        share_string = encode_page(self._sample_page())
        mock_page_service.create_page.return_value = Page(
            id="new-id",
            name="Test Page",
            type="template",
            device_type="flagship",
            template=["Hello", "World", "", "", "", ""],
        )
        response = client.post("/pages/import", json={"share_string": share_string})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["page"]["name"] == "Test Page"
        mock_page_service.create_page.assert_called_once()

    def test_import_page_creates_new_id(self, client, mock_page_service):
        """Import should always create a new page, never reuse the original id."""
        from src.pages.share import encode_page

        share_string = encode_page(self._sample_page())
        mock_page_service.create_page.return_value = Page(
            id="brand-new-id",
            name="Test Page",
            type="template",
            device_type="flagship",
            template=["Hello", "World", "", "", "", ""],
        )
        client.post("/pages/import", json={"share_string": share_string})
        # The PageCreate passed to create_page must not carry the original id
        call_args = mock_page_service.create_page.call_args[0][0]
        assert not hasattr(call_args, "id") or getattr(call_args, "id", None) is None

    def test_import_page_invalid_share_string(self, client, mock_page_service):
        response = client.post("/pages/import", json={"share_string": "this-is-not-valid"})
        assert response.status_code == 422

    def test_import_preview_success(self, client, mock_page_service):
        from src.pages.share import encode_page

        share_string = encode_page(self._sample_page())
        response = client.post("/pages/import/preview", json={"share_string": share_string})
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Page"
        assert data["type"] == "template"
        mock_page_service.create_page.assert_not_called()

    def test_import_preview_invalid_share_string(self, client, mock_page_service):
        response = client.post("/pages/import/preview", json={"share_string": "garbage"})
        assert response.status_code == 422

    def test_import_future_version_share_string(self, client, mock_page_service):
        import base64

        payload = base64.urlsafe_b64encode(json.dumps({"v": 999, "page": {"name": "x"}}).encode()).decode().rstrip("=")
        response = client.post("/pages/import", json={"share_string": payload})
        assert response.status_code == 422
        assert "FiestaBoard" in response.json()["detail"]
