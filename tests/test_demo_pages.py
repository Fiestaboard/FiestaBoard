"""Tests for the plugin demo page feature.

Covers:
- DemoPageSchema parsing from manifest
- Page model demo_plugin_id field
- Schema migration v1 -> v2
- PageService.get_demo_page() and create_demo_page()
- Manifest validation of the demo section
"""

import json
import pytest
import tempfile
import os
from datetime import datetime, timezone
from unittest.mock import patch

from src.plugins.manifest import (
    DemoPageSchema,
    PluginManifest,
    validate_manifest,
)
from src.pages.models import Page, PageCreate, LineMetadata
from src.pages.storage import PageStorage, _migrate_v1_to_v2, CURRENT_SCHEMA_VERSION
from src.pages.service import PageService


# ---------------------------------------------------------------------------
# DemoPageSchema + manifest parsing
# ---------------------------------------------------------------------------

class TestDemoPageSchema:

    def test_parse_demo_from_manifest(self):
        """Manifest with a demo section produces a DemoPageSchema."""
        data = {
            "id": "test_plugin",
            "name": "Test",
            "version": "1.0.0",
            "demo": {
                "name": "Test Demo",
                "template": ["Line 1", "Line 2", "", "", "", ""],
                "device_type": "flagship",
                "line_metadata": [
                    {"alignment": "center", "wrap": False},
                    {"alignment": "left", "wrap": False},
                    {"alignment": "left", "wrap": False},
                    {"alignment": "left", "wrap": False},
                    {"alignment": "left", "wrap": False},
                    {"alignment": "left", "wrap": False},
                ],
                "duration_seconds": 600,
            },
        }
        manifest = PluginManifest.from_dict(data)
        assert manifest.demo is not None
        assert manifest.demo.name == "Test Demo"
        assert manifest.demo.template == ["Line 1", "Line 2", "", "", "", ""]
        assert manifest.demo.device_type == "flagship"
        assert manifest.demo.duration_seconds == 600
        assert len(manifest.demo.line_metadata) == 6

    def test_manifest_without_demo(self):
        """Manifest without a demo section sets demo to None."""
        data = {"id": "test_plugin", "name": "Test", "version": "1.0.0"}
        manifest = PluginManifest.from_dict(data)
        assert manifest.demo is None

    def test_demo_defaults(self):
        """Demo section with minimal fields uses correct defaults."""
        data = {
            "id": "test_plugin",
            "name": "Test",
            "version": "1.0.0",
            "demo": {
                "name": "Minimal Demo",
                "template": ["Hello"],
            },
        }
        manifest = PluginManifest.from_dict(data)
        assert manifest.demo.device_type == "flagship"
        assert manifest.demo.duration_seconds == 300
        assert manifest.demo.line_metadata is None

    def test_demo_note_device_type(self):
        """Demo can target the 'note' device type."""
        data = {
            "id": "test_plugin",
            "name": "Test",
            "version": "1.0.0",
            "demo": {
                "name": "Note Demo",
                "template": ["L1", "L2", "L3"],
                "device_type": "note",
            },
        }
        manifest = PluginManifest.from_dict(data)
        assert manifest.demo.device_type == "note"


# ---------------------------------------------------------------------------
# Manifest validation
# ---------------------------------------------------------------------------

class TestDemoValidation:

    def test_valid_demo_section(self):
        """A well-formed demo section passes validation."""
        data = {
            "id": "test_plugin",
            "name": "Test",
            "version": "1.0.0",
            "demo": {
                "name": "Demo",
                "template": ["{{test_plugin.value}}"],
            },
        }
        is_valid, errors = validate_manifest(data)
        assert is_valid, errors

    def test_demo_missing_name(self):
        """Demo section missing 'name' fails validation."""
        data = {
            "id": "test_plugin",
            "name": "Test",
            "version": "1.0.0",
            "demo": {"template": ["line"]},
        }
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("demo" in e and "name" in e for e in errors)

    def test_demo_missing_template(self):
        """Demo section missing 'template' fails validation."""
        data = {
            "id": "test_plugin",
            "name": "Test",
            "version": "1.0.0",
            "demo": {"name": "Demo"},
        }
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("demo" in e and "template" in e for e in errors)

    def test_demo_invalid_device_type(self):
        """Demo with bad device_type fails validation."""
        data = {
            "id": "test_plugin",
            "name": "Test",
            "version": "1.0.0",
            "demo": {
                "name": "Demo",
                "template": ["line"],
                "device_type": "jumbo",
            },
        }
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("device_type" in e for e in errors)

    def test_demo_not_dict_fails(self):
        """Non-object demo value fails validation."""
        data = {
            "id": "test_plugin",
            "name": "Test",
            "version": "1.0.0",
            "demo": "not an object",
        }
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("demo" in e for e in errors)


# ---------------------------------------------------------------------------
# Page model – demo_plugin_id
# ---------------------------------------------------------------------------

class TestPageDemoField:

    def test_page_has_demo_plugin_id(self):
        page = Page(
            name="Test",
            type="template",
            template=["L1"],
            demo_plugin_id="weather",
        )
        assert page.demo_plugin_id == "weather"
        assert page.is_valid()

    def test_page_demo_plugin_id_defaults_none(self):
        page = Page(name="Test", type="template", template=["L1"])
        assert page.demo_plugin_id is None

    def test_page_create_includes_demo_plugin_id(self):
        pc = PageCreate(
            name="Demo",
            type="template",
            template=["L1"],
            demo_plugin_id="weather",
        )
        assert pc.demo_plugin_id == "weather"

    def test_page_serialization_includes_demo_plugin_id(self):
        page = Page(
            name="Test",
            type="template",
            template=["L1"],
            demo_plugin_id="stocks",
        )
        data = page.model_dump()
        assert data["demo_plugin_id"] == "stocks"


# ---------------------------------------------------------------------------
# Schema migration v1 -> v2
# ---------------------------------------------------------------------------

class TestSchemaMigrationV1ToV2:

    def test_adds_demo_plugin_id(self):
        pages = [
            {"id": "1", "name": "A", "type": "template", "template": ["X"]},
            {"id": "2", "name": "B", "type": "single", "display_type": "weather"},
        ]
        count = _migrate_v1_to_v2(pages)
        assert count == 2
        assert pages[0]["demo_plugin_id"] is None
        assert pages[1]["demo_plugin_id"] is None

    def test_idempotent(self):
        pages = [
            {"id": "1", "name": "A", "type": "template", "template": ["X"], "demo_plugin_id": None},
        ]
        count = _migrate_v1_to_v2(pages)
        assert count == 0

    def test_preserves_existing_value(self):
        pages = [
            {"id": "1", "name": "A", "type": "template", "template": ["X"], "demo_plugin_id": "weather"},
        ]
        count = _migrate_v1_to_v2(pages)
        assert count == 0
        assert pages[0]["demo_plugin_id"] == "weather"

    def test_current_schema_version(self):
        assert CURRENT_SCHEMA_VERSION == 2


# ---------------------------------------------------------------------------
# PageService – demo page operations
# ---------------------------------------------------------------------------

class TestPageServiceDemo:

    @pytest.fixture
    def temp_storage_file(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.fixture
    def service(self, temp_storage_file):
        storage = PageStorage(storage_file=temp_storage_file)
        return PageService(storage=storage)

    def _demo_schema(self, name="Test Demo"):
        return DemoPageSchema(
            name=name,
            template=["Line 1", "{{test.var}}", "", "", "", ""],
            device_type="flagship",
            line_metadata=[
                {"alignment": "center", "wrap": False},
                {"alignment": "left", "wrap": False},
                {"alignment": "left", "wrap": False},
                {"alignment": "left", "wrap": False},
                {"alignment": "left", "wrap": False},
                {"alignment": "left", "wrap": False},
            ],
            duration_seconds=300,
        )

    def test_get_demo_page_none_when_empty(self, service):
        assert service.get_demo_page("test_plugin") is None

    def test_create_demo_page(self, service):
        page, recreated = service.create_demo_page("test_plugin", self._demo_schema())
        assert not recreated
        assert page.demo_plugin_id == "test_plugin"
        assert page.name == "Test Demo"
        assert page.type == "template"
        assert page.device_type == "flagship"
        assert page.template == ["Line 1", "{{test.var}}", "", "", "", ""]
        assert len(page.line_metadata) == 6
        assert page.line_metadata[0].alignment == "center"

    def test_get_demo_page_after_create(self, service):
        page, _ = service.create_demo_page("test_plugin", self._demo_schema())
        found = service.get_demo_page("test_plugin")
        assert found is not None
        assert found.id == page.id

    def test_recreate_demo_page(self, service):
        page1, _ = service.create_demo_page("test_plugin", self._demo_schema())
        page2, recreated = service.create_demo_page("test_plugin", self._demo_schema("Refreshed"))
        assert recreated
        assert page2.id != page1.id
        assert page2.name == "Refreshed"
        assert service.get_demo_page("test_plugin").id == page2.id

    def test_demo_page_singleton_per_plugin(self, service):
        service.create_demo_page("plugin_a", self._demo_schema("Demo A"))
        service.create_demo_page("plugin_b", self._demo_schema("Demo B"))

        assert service.get_demo_page("plugin_a").name == "Demo A"
        assert service.get_demo_page("plugin_b").name == "Demo B"
        assert service.get_demo_page("plugin_c") is None

    def test_demo_page_persists_to_storage(self, temp_storage_file):
        storage1 = PageStorage(storage_file=temp_storage_file)
        svc1 = PageService(storage=storage1)
        page, _ = svc1.create_demo_page("test_plugin", self._demo_schema())

        storage2 = PageStorage(storage_file=temp_storage_file)
        svc2 = PageService(storage=storage2)
        found = svc2.get_demo_page("test_plugin")
        assert found is not None
        assert found.id == page.id
        assert found.demo_plugin_id == "test_plugin"
