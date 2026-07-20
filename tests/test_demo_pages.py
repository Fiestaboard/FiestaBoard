"""Tests for the plugin demo page feature.

Covers:
- DemoPageSchema parsing from manifest
- Page model demo_plugin_id field
- Schema migration v1 -> v2
- PageService.get_demo_page() and create_demo_page()
- Manifest validation of the demo section
- POST /plugins/{plugin_id}/demo-page endpoint device_type resolution
"""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.pages.models import Page, PageCreate
from src.pages.service import PageService
from src.pages.storage import CURRENT_SCHEMA_VERSION, PageStorage, _migrate_v1_to_v2
from src.plugins.manifest import (
    DemoPageSchema,
    PluginManifest,
    validate_manifest,
)

# ---------------------------------------------------------------------------
# DemoPageSchema + manifest parsing
# ---------------------------------------------------------------------------


class TestDemoPageSchema:
    def test_parse_old_format_from_manifest(self):
        """Old flat demo format is normalised to a dict keyed by device_type."""
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
        assert isinstance(manifest.demo, dict)
        assert "flagship" in manifest.demo
        schema = manifest.demo["flagship"]
        assert schema.name == "Test Demo"
        assert schema.template == ["Line 1", "Line 2", "", "", "", ""]
        assert schema.device_type == "flagship"
        assert schema.duration_seconds == 600
        assert len(schema.line_metadata) == 6

    def test_parse_old_format_note_device_type(self):
        """Old flat demo format with device_type=note is stored under 'note' key."""
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
        assert "note" in manifest.demo
        assert manifest.demo["note"].device_type == "note"

    def test_parse_new_format_single_device(self):
        """New keyed format with one device type parses correctly."""
        data = {
            "id": "test_plugin",
            "name": "Test",
            "version": "1.0.0",
            "demo": {
                "flagship": {
                    "name": "Flagship Demo",
                    "template": ["L1", "L2", "", "", "", ""],
                    "duration_seconds": 120,
                }
            },
        }
        manifest = PluginManifest.from_dict(data)
        assert manifest.demo is not None
        assert "flagship" in manifest.demo
        assert "note" not in manifest.demo
        schema = manifest.demo["flagship"]
        assert schema.name == "Flagship Demo"
        assert schema.device_type == "flagship"
        assert schema.duration_seconds == 120

    def test_parse_new_format_both_devices(self):
        """New keyed format with both device types parses both schemas."""
        data = {
            "id": "test_plugin",
            "name": "Test",
            "version": "1.0.0",
            "demo": {
                "flagship": {
                    "name": "Flagship Demo",
                    "template": ["L1", "L2", "", "", "", ""],
                },
                "note": {
                    "name": "Note Demo",
                    "template": ["L1", "L2", "L3"],
                },
            },
        }
        manifest = PluginManifest.from_dict(data)
        assert "flagship" in manifest.demo
        assert "note" in manifest.demo
        assert manifest.demo["flagship"].name == "Flagship Demo"
        assert manifest.demo["note"].name == "Note Demo"
        assert manifest.demo["note"].device_type == "note"

    def test_manifest_without_demo(self):
        """Manifest without a demo section sets demo to None."""
        data = {"id": "test_plugin", "name": "Test", "version": "1.0.0"}
        manifest = PluginManifest.from_dict(data)
        assert manifest.demo is None

    def test_demo_old_format_defaults(self):
        """Old flat demo with minimal fields uses correct defaults."""
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
        schema = manifest.demo["flagship"]
        assert schema.device_type == "flagship"
        assert schema.duration_seconds == 300
        assert schema.line_metadata is None

    def test_demo_new_format_defaults(self):
        """New keyed format with minimal fields uses correct defaults."""
        data = {
            "id": "test_plugin",
            "name": "Test",
            "version": "1.0.0",
            "demo": {
                "note": {
                    "name": "Note Demo",
                    "template": ["L1", "L2", "L3"],
                }
            },
        }
        manifest = PluginManifest.from_dict(data)
        schema = manifest.demo["note"]
        assert schema.device_type == "note"
        assert schema.duration_seconds == 300
        assert schema.line_metadata is None


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

    def test_new_format_valid_both_devices(self):
        """New keyed format with both device types passes validation."""
        data = {
            "id": "test_plugin",
            "name": "Test",
            "version": "1.0.0",
            "demo": {
                "flagship": {"name": "Flagship", "template": ["L1"]},
                "note": {"name": "Note", "template": ["L1", "L2", "L3"]},
            },
        }
        is_valid, errors = validate_manifest(data)
        assert is_valid, errors

    def test_new_format_invalid_key(self):
        """New keyed format with an unknown device type key fails validation."""
        data = {
            "id": "test_plugin",
            "name": "Test",
            "version": "1.0.0",
            "demo": {
                "jumbo": {"name": "Demo", "template": ["L1"]},
            },
        }
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("jumbo" in e for e in errors)

    def test_new_format_missing_name(self):
        """New keyed format with a missing 'name' in an entry fails validation."""
        data = {
            "id": "test_plugin",
            "name": "Test",
            "version": "1.0.0",
            "demo": {
                "flagship": {"template": ["L1"]},
            },
        }
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("flagship" in e and "name" in e for e in errors)

    def test_new_format_missing_template(self):
        """New keyed format with a missing 'template' in an entry fails validation."""
        data = {
            "id": "test_plugin",
            "name": "Test",
            "version": "1.0.0",
            "demo": {
                "note": {"name": "Demo"},
            },
        }
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("note" in e and "template" in e for e in errors)


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
        assert CURRENT_SCHEMA_VERSION == 4


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

    def test_get_demo_page_filters_by_device_type(self, service):
        """get_demo_page with device_type only returns matching pages."""
        flagship_schema = self._demo_schema("Flagship Demo")
        note_schema = DemoPageSchema(
            name="Note Demo",
            template=["L1", "L2", "L3"],
            device_type="note",
        )
        service.create_demo_page("test_plugin", flagship_schema)
        service.create_demo_page("test_plugin", note_schema)

        flagship_page = service.get_demo_page("test_plugin", device_type="flagship")
        note_page = service.get_demo_page("test_plugin", device_type="note")

        assert flagship_page is not None
        assert flagship_page.device_type == "flagship"
        assert note_page is not None
        assert note_page.device_type == "note"

    def test_singleton_per_device_type(self, service):
        """Recreating a flagship demo does not delete the note demo, and vice versa."""
        flagship_schema = self._demo_schema("Flagship Demo")
        note_schema = DemoPageSchema(
            name="Note Demo",
            template=["L1", "L2", "L3"],
            device_type="note",
        )
        service.create_demo_page("test_plugin", flagship_schema)
        service.create_demo_page("test_plugin", note_schema)

        # Recreate flagship — note should survive
        _, recreated = service.create_demo_page("test_plugin", self._demo_schema("Flagship Refreshed"))
        assert recreated

        assert service.get_demo_page("test_plugin", device_type="flagship").name == "Flagship Refreshed"
        assert service.get_demo_page("test_plugin", device_type="note") is not None
        assert service.get_demo_page("test_plugin", device_type="note").name == "Note Demo"

    def test_get_demo_page_no_filter_returns_any(self, service):
        """get_demo_page without device_type returns any demo page for the plugin."""
        note_schema = DemoPageSchema(
            name="Note Demo",
            template=["L1", "L2", "L3"],
            device_type="note",
        )
        service.create_demo_page("test_plugin", note_schema)
        found = service.get_demo_page("test_plugin")
        assert found is not None
        assert found.demo_plugin_id == "test_plugin"

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


# ---------------------------------------------------------------------------
# POST /plugins/{plugin_id}/demo-page – endpoint behaviour
#
# Regression coverage for issue #942: when no device_type query param is
# supplied, the endpoint must honour the configured board's device_type
# instead of defaulting to "flagship".
# ---------------------------------------------------------------------------


class TestCreateDemoPageEndpoint:
    @pytest.fixture
    def client(self):
        from src.api_server import app

        return TestClient(app)

    @pytest.fixture
    def flagship_demo_schema(self):
        return DemoPageSchema(
            name="Flagship Demo",
            template=["F1", "F2", "F3", "F4", "F5", "F6"],
            device_type="flagship",
        )

    @pytest.fixture
    def note_demo_schema(self):
        return DemoPageSchema(
            name="Note Demo",
            template=["N1", "N2", "N3"],
            device_type="note",
        )

    @pytest.fixture
    def manifest_with_both_demos(self, flagship_demo_schema, note_demo_schema):
        manifest = Mock()
        manifest.demo = {"flagship": flagship_demo_schema, "note": note_demo_schema}
        manifest.settings_schema = {"required": []}
        return manifest

    @pytest.fixture
    def board_settings_with_device(self):
        def _make(device_type: str):
            bs = Mock()
            bs.boards = [{"id": "b1", "device_type": device_type}]
            bs.devices = [device_type]
            return bs

        return _make

    def _patch_dependencies(self, manifest, board_settings):
        """Patch the registry, settings service, and page service."""
        registry = Mock()
        registry.get_manifest.return_value = manifest

        settings_service = Mock()
        settings_service.get_board_settings.return_value = board_settings

        created_page = Mock()
        created_page.model_dump.return_value = {"id": "p1", "name": "demo"}
        page_service = Mock()
        page_service.create_demo_page.return_value = (created_page, False)

        return (
            patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True),
            patch("src.api_server.get_plugin_registry", return_value=registry),
            patch("src.api_server.get_settings_service", return_value=settings_service),
            patch("src.api_server.get_page_service", return_value=page_service),
            patch("src.api_server.get_config_manager", return_value=Mock(get_plugin_config=Mock(return_value={}))),
            page_service,
        )

    def test_defaults_to_configured_board_device_type_note(
        self, client, manifest_with_both_demos, board_settings_with_device
    ):
        """When the only configured board is a Note, the demo must use the note schema."""
        bs = board_settings_with_device("note")
        p_avail, p_reg, p_ss, p_ps, p_cm, page_service = self._patch_dependencies(manifest_with_both_demos, bs)

        with p_avail, p_reg, p_ss, p_ps, p_cm:
            response = client.post("/plugins/test_plugin/demo-page")

        assert response.status_code == 200, response.text
        page_service.create_demo_page.assert_called_once()
        passed_schema = page_service.create_demo_page.call_args[0][1]
        assert passed_schema.device_type == "note", (
            "Endpoint should resolve device_type from configured board settings, not hard-code 'flagship'."
        )

    def test_defaults_to_configured_board_device_type_flagship(
        self, client, manifest_with_both_demos, board_settings_with_device
    ):
        """When the only configured board is a Flagship, the demo uses the flagship schema."""
        bs = board_settings_with_device("flagship")
        p_avail, p_reg, p_ss, p_ps, p_cm, page_service = self._patch_dependencies(manifest_with_both_demos, bs)

        with p_avail, p_reg, p_ss, p_ps, p_cm:
            response = client.post("/plugins/test_plugin/demo-page")

        assert response.status_code == 200, response.text
        passed_schema = page_service.create_demo_page.call_args[0][1]
        assert passed_schema.device_type == "flagship"

    def test_explicit_device_type_query_overrides_settings(
        self, client, manifest_with_both_demos, board_settings_with_device
    ):
        """An explicit ?device_type=flagship still wins over a Note-only configuration."""
        bs = board_settings_with_device("note")
        p_avail, p_reg, p_ss, p_ps, p_cm, page_service = self._patch_dependencies(manifest_with_both_demos, bs)

        with p_avail, p_reg, p_ss, p_ps, p_cm:
            response = client.post("/plugins/test_plugin/demo-page?device_type=flagship")

        assert response.status_code == 200, response.text
        passed_schema = page_service.create_demo_page.call_args[0][1]
        assert passed_schema.device_type == "flagship"

    def test_falls_back_to_flagship_when_note_template_missing(
        self, client, flagship_demo_schema, board_settings_with_device
    ):
        """If the plugin only ships a flagship demo, a Note board still gets *something*."""
        manifest = Mock()
        manifest.demo = {"flagship": flagship_demo_schema}
        manifest.settings_schema = {"required": []}
        bs = board_settings_with_device("note")
        p_avail, p_reg, p_ss, p_ps, p_cm, page_service = self._patch_dependencies(manifest, bs)

        with p_avail, p_reg, p_ss, p_ps, p_cm:
            response = client.post("/plugins/test_plugin/demo-page")

        assert response.status_code == 200, response.text
        passed_schema = page_service.create_demo_page.call_args[0][1]
        assert passed_schema.device_type == "flagship"
