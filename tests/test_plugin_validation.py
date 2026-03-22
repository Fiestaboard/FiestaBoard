"""Tests for plugin validation - ensures plugin integrity in CI.

These tests run as part of the platform test suite and verify:
1. All plugin IDs are unique
2. Plugin IDs match their directory names
3. All manifest.json files are valid
4. Required files exist
"""

import json
import pytest
from pathlib import Path
from typing import Dict, List, Set

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
PLUGINS_DIR = PROJECT_ROOT / "plugins"

# Directories to skip
SKIP_DIRECTORIES = {"_template", "__pycache__"}


def get_plugin_directories() -> List[Path]:
    """Get all plugin directories (excluding template and pycache)."""
    if not PLUGINS_DIR.exists():
        return []
    
    plugins = []
    for item in PLUGINS_DIR.iterdir():
        if item.is_dir() and item.name not in SKIP_DIRECTORIES and not item.name.startswith("."):
            plugins.append(item)
    
    return sorted(plugins, key=lambda p: p.name)


def load_manifest(plugin_dir: Path) -> Dict:
    """Load a plugin's manifest.json."""
    manifest_path = plugin_dir / "manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


class TestPluginUniqueness:
    """Tests to ensure all plugin IDs are unique."""
    
    def test_all_plugin_ids_are_unique(self):
        """CI Test: Ensure no duplicate plugin IDs exist.
        
        This test fails if two or more plugins share the same ID,
        which would cause conflicts in the plugin registry.
        """
        plugins = get_plugin_directories()
        
        if not plugins:
            pytest.skip("No plugins found")
        
        ids_seen: Dict[str, str] = {}  # id -> directory name
        duplicates: List[str] = []
        
        for plugin_dir in plugins:
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            
            manifest = load_manifest(plugin_dir)
            plugin_id = manifest.get("id", "")
            
            if plugin_id in ids_seen:
                duplicates.append(
                    f"Plugin ID '{plugin_id}' is used by both "
                    f"'{ids_seen[plugin_id]}' and '{plugin_dir.name}'"
                )
            else:
                ids_seen[plugin_id] = plugin_dir.name
        
        assert not duplicates, (
            "Duplicate plugin IDs found:\n" + "\n".join(f"  - {d}" for d in duplicates)
        )
    
    def test_plugin_id_matches_directory_name(self):
        """CI Test: Ensure plugin ID matches its directory name.
        
        This convention makes it easier to locate plugins and prevents confusion.
        """
        plugins = get_plugin_directories()
        
        if not plugins:
            pytest.skip("No plugins found")
        
        mismatches: List[str] = []
        
        for plugin_dir in plugins:
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            
            manifest = load_manifest(plugin_dir)
            plugin_id = manifest.get("id", "")
            dir_name = plugin_dir.name
            
            if plugin_id != dir_name:
                mismatches.append(
                    f"Plugin in '{dir_name}/' has ID '{plugin_id}' "
                    f"(expected '{dir_name}')"
                )
        
        assert not mismatches, (
            "Plugin ID/directory mismatches found:\n" + 
            "\n".join(f"  - {m}" for m in mismatches)
        )


class TestManifestValidity:
    """Tests to ensure all manifests are valid."""
    
    def test_all_manifests_are_valid_json(self):
        """CI Test: All manifest.json files must be valid JSON."""
        plugins = get_plugin_directories()
        
        if not plugins:
            pytest.skip("No plugins found")
        
        invalid: List[str] = []
        
        for plugin_dir in plugins:
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                invalid.append(f"{plugin_dir.name}: manifest.json not found")
                continue
            
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    json.load(f)
            except json.JSONDecodeError as e:
                invalid.append(f"{plugin_dir.name}: Invalid JSON - {e}")
        
        assert not invalid, (
            "Invalid manifest files found:\n" + "\n".join(f"  - {i}" for i in invalid)
        )
    
    def test_all_manifests_have_required_fields(self):
        """CI Test: All manifests must have required fields (id, name, version)."""
        plugins = get_plugin_directories()
        
        if not plugins:
            pytest.skip("No plugins found")
        
        required_fields = ["id", "name", "version"]
        missing: List[str] = []
        
        for plugin_dir in plugins:
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            
            manifest = load_manifest(plugin_dir)
            
            for field in required_fields:
                if field not in manifest:
                    missing.append(f"{plugin_dir.name}: missing '{field}'")
        
        assert not missing, (
            "Manifests missing required fields:\n" + "\n".join(f"  - {m}" for m in missing)
        )
    
    def test_plugin_id_format(self):
        """CI Test: Plugin IDs must be valid identifiers (lowercase, underscores)."""
        plugins = get_plugin_directories()
        
        if not plugins:
            pytest.skip("No plugins found")
        
        invalid_ids: List[str] = []
        
        for plugin_dir in plugins:
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            
            manifest = load_manifest(plugin_dir)
            plugin_id = manifest.get("id", "")
            
            if not plugin_id:
                invalid_ids.append(f"{plugin_dir.name}: empty ID")
            elif not plugin_id[0].isalpha() or not plugin_id[0].islower():
                invalid_ids.append(f"{plugin_dir.name}: ID '{plugin_id}' must start with lowercase letter")
            elif not all(c.islower() or c.isdigit() or c == '_' for c in plugin_id):
                invalid_ids.append(f"{plugin_dir.name}: ID '{plugin_id}' contains invalid characters")
        
        assert not invalid_ids, (
            "Invalid plugin IDs found:\n" + "\n".join(f"  - {i}" for i in invalid_ids)
        )
    
    def test_version_format(self):
        """CI Test: Version must be semantic versioning format (X.Y.Z)."""
        plugins = get_plugin_directories()
        
        if not plugins:
            pytest.skip("No plugins found")
        
        invalid_versions: List[str] = []
        
        for plugin_dir in plugins:
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            
            manifest = load_manifest(plugin_dir)
            version = manifest.get("version", "")
            
            if not version:
                invalid_versions.append(f"{plugin_dir.name}: missing version")
                continue
            
            parts = version.split(".")
            if len(parts) != 3:
                invalid_versions.append(f"{plugin_dir.name}: version '{version}' must be X.Y.Z format")
            elif not all(part.isdigit() for part in parts):
                invalid_versions.append(f"{plugin_dir.name}: version '{version}' parts must be integers")
        
        assert not invalid_versions, (
            "Invalid version formats found:\n" + "\n".join(f"  - {v}" for v in invalid_versions)
        )

    def test_repository_url_capitalization(self):
        """CI Test: If manifest has repository URL, it must use canonical capitalization.

        Expected: https://github.com/FiestaBoard/FiestaBoard
        (Org 'FiestaBoard' and repo 'FiestaBoard' with capital B.)
        """
        canonical_repo_url = "https://github.com/FiestaBoard/FiestaBoard"
        plugins = get_plugin_directories()

        if not plugins:
            pytest.skip("No plugins found")

        wrong_urls: List[str] = []

        for plugin_dir in plugins:
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                continue

            manifest = load_manifest(plugin_dir)
            repo = manifest.get("repository")
            if repo is None:
                continue

            if repo != canonical_repo_url:
                wrong_urls.append(
                    f"{plugin_dir.name}: repository is '{repo}' "
                    f"(expected '{canonical_repo_url}')"
                )

        assert not wrong_urls, (
            "Manifests with incorrect repository URL (check capitalization):\n"
            + "\n".join(f"  - {w}" for w in wrong_urls)
        )


class TestPluginStructure:
    """Tests for plugin directory structure."""
    
    def test_all_plugins_have_init_file(self):
        """CI Test: All plugins must have __init__.py."""
        plugins = get_plugin_directories()
        
        if not plugins:
            pytest.skip("No plugins found")
        
        missing: List[str] = []
        
        for plugin_dir in plugins:
            init_file = plugin_dir / "__init__.py"
            if not init_file.exists():
                missing.append(plugin_dir.name)
        
        assert not missing, (
            "Plugins missing __init__.py:\n" + "\n".join(f"  - {m}" for m in missing)
        )
    
    def test_all_plugins_have_manifest(self):
        """CI Test: All plugins must have manifest.json."""
        plugins = get_plugin_directories()
        
        if not plugins:
            pytest.skip("No plugins found")
        
        missing: List[str] = []
        
        for plugin_dir in plugins:
            manifest_file = plugin_dir / "manifest.json"
            if not manifest_file.exists():
                missing.append(plugin_dir.name)
        
        assert not missing, (
            "Plugins missing manifest.json:\n" + "\n".join(f"  - {m}" for m in missing)
        )
    
    def test_all_plugins_have_tests_directory(self):
        """CI Test: All plugins should have a tests/ directory.
        
        Note: This is a warning-level test. New plugins must have tests,
        but this test ensures visibility of plugins without tests.
        """
        plugins = get_plugin_directories()
        
        if not plugins:
            pytest.skip("No plugins found")
        
        missing_tests: List[str] = []
        
        for plugin_dir in plugins:
            tests_dir = plugin_dir / "tests"
            if not tests_dir.exists() or not tests_dir.is_dir():
                missing_tests.append(plugin_dir.name)
        
        # This test passes but logs warnings
        # In strict mode (via validate_plugins.py --strict), this would fail
        if missing_tests:
            pytest.warns(
                UserWarning,
                match="Plugins without tests directory",
            ) if hasattr(pytest, 'warns') else None
            # Log for visibility even if test passes
            print(f"\nWarning: Plugins without tests/: {', '.join(missing_tests)}")


class TestPluginRateLimits:
    """Tests for plugin refresh rate-limit configuration."""

    def test_min_refresh_seconds_is_valid_when_present(self):
        """CI Test: min_refresh_seconds must be a positive integer."""
        plugins = get_plugin_directories()
        if not plugins:
            pytest.skip("No plugins found")

        invalid: List[str] = []
        for plugin_dir in plugins:
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            manifest = load_manifest(plugin_dir)
            floor = manifest.get("min_refresh_seconds")
            if floor is None:
                continue
            if not isinstance(floor, int) or floor <= 0:
                invalid.append(
                    f"{plugin_dir.name}: min_refresh_seconds must be a positive integer, "
                    f"got {floor!r}"
                )
        assert not invalid, (
            "Invalid min_refresh_seconds:\n" + "\n".join(f"  - {i}" for i in invalid)
        )

    def test_min_refresh_seconds_lte_schema_minimum(self):
        """CI Test: min_refresh_seconds must be <= settings_schema minimum.
        
        The schema minimum is the user-facing lower bound shown in the UI.
        The hard floor must not exceed it, otherwise users would see a
        minimum in the UI that is lower than what the runtime enforces.
        """
        plugins = get_plugin_directories()
        if not plugins:
            pytest.skip("No plugins found")

        inconsistent: List[str] = []
        for plugin_dir in plugins:
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            manifest = load_manifest(plugin_dir)
            floor = manifest.get("min_refresh_seconds")
            if floor is None:
                continue
            schema = manifest.get("settings_schema", {})
            props = schema.get("properties", {})
            refresh = props.get("refresh_seconds", {})
            schema_min = refresh.get("minimum")
            if schema_min is not None and floor > schema_min:
                inconsistent.append(
                    f"{plugin_dir.name}: min_refresh_seconds ({floor}) > "
                    f"settings_schema minimum ({schema_min})"
                )
        assert not inconsistent, (
            "Inconsistent rate-limit floors:\n"
            + "\n".join(f"  - {i}" for i in inconsistent)
        )

    def test_plugins_with_refresh_seconds_have_floor(self):
        """CI Test: Plugins declaring refresh_seconds should have a rate-limit floor.

        A floor is satisfied by either an explicit top-level
        ``min_refresh_seconds`` field or a ``minimum`` inside the
        settings_schema ``refresh_seconds`` property (PluginBase falls
        back to the schema minimum at runtime).
        """
        plugins = get_plugin_directories()
        if not plugins:
            pytest.skip("No plugins found")

        missing: List[str] = []
        for plugin_dir in plugins:
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            manifest = load_manifest(plugin_dir)
            schema = manifest.get("settings_schema", {})
            props = schema.get("properties", {})
            refresh_prop = props.get("refresh_seconds")
            if refresh_prop is None:
                continue
            has_explicit = "min_refresh_seconds" in manifest
            has_schema_min = "minimum" in refresh_prop
            if not has_explicit and not has_schema_min:
                missing.append(plugin_dir.name)
        assert not missing, (
            "Plugins with refresh_seconds but no rate-limit floor "
            "(add min_refresh_seconds or a schema minimum):\n"
            + "\n".join(f"  - {m}" for m in missing)
        )


class TestManifestVariablesParsing:
    """Tests for the enhanced variables schema parsing (list/dict, groups, auto_discover)."""

    def test_manifest_parses_simple_list_format(self):
        """PluginManifest.from_dict handles the legacy list format for simple variables."""
        from src.plugins.manifest import PluginManifest

        data = {"id": "test", "name": "Test", "version": "1.0.0",
                "variables": {"simple": ["a", "b", "c"]}}
        manifest = PluginManifest.from_dict(data)
        assert manifest.variables.simple == ["a", "b", "c"]
        assert manifest.variables.metadata == {}

    def test_manifest_parses_simple_dict_format(self):
        """PluginManifest.from_dict handles the rich dict format for simple variables."""
        from src.plugins.manifest import PluginManifest, VariableMetadata

        data = {
            "id": "test", "name": "Test", "version": "1.0.0",
            "variables": {
                "simple": {
                    "temperature": {
                        "description": "Current temp",
                        "type": "number",
                        "max_length": 3,
                        "group": "current",
                        "example": "72",
                    },
                    "status": {"description": "Status text"},
                },
            },
        }
        manifest = PluginManifest.from_dict(data)
        assert manifest.variables.simple == ["temperature", "status"]
        assert "temperature" in manifest.variables.metadata
        meta = manifest.variables.metadata["temperature"]
        assert meta.description == "Current temp"
        assert meta.type == "number"
        assert meta.max_length == 3
        assert meta.group == "current"
        assert meta.example == "72"

    def test_manifest_parses_groups(self):
        """PluginManifest.from_dict parses the groups section."""
        from src.plugins.manifest import PluginManifest

        data = {
            "id": "test", "name": "Test", "version": "1.0.0",
            "variables": {
                "groups": {
                    "time": {"label": "Time"},
                    "date": {"label": "Date"},
                },
                "simple": ["hour", "minute"],
            },
        }
        manifest = PluginManifest.from_dict(data)
        assert "time" in manifest.variables.groups
        assert manifest.variables.groups["time"].label == "Time"
        assert "date" in manifest.variables.groups

    def test_manifest_auto_discover_default_true_when_no_vars(self):
        """auto_discover defaults to True when no variables section exists."""
        from src.plugins.manifest import PluginManifest

        data = {"id": "test", "name": "Test", "version": "1.0.0"}
        manifest = PluginManifest.from_dict(data)
        assert manifest.variables.auto_discover is True

    def test_manifest_auto_discover_default_false_when_vars_present(self):
        """auto_discover defaults to False when variables.simple is declared."""
        from src.plugins.manifest import PluginManifest

        data = {"id": "test", "name": "Test", "version": "1.0.0",
                "variables": {"simple": ["a"]}}
        manifest = PluginManifest.from_dict(data)
        assert manifest.variables.auto_discover is False

    def test_manifest_auto_discover_explicit_override(self):
        """Explicit auto_discover flag overrides the smart default."""
        from src.plugins.manifest import PluginManifest

        data = {"id": "test", "name": "Test", "version": "1.0.0",
                "variables": {"auto_discover": True, "simple": ["a"]}}
        manifest = PluginManifest.from_dict(data)
        assert manifest.variables.auto_discover is True

    def test_variable_metadata_defaults(self):
        """VariableMetadata has sensible defaults."""
        from src.plugins.manifest import VariableMetadata

        meta = VariableMetadata()
        assert meta.description == ""
        assert meta.type == "string"
        assert meta.max_length is None
        assert meta.group == ""
        assert meta.example == ""

    def test_variable_metadata_from_dict_format(self):
        """get_variable_metadata returns metadata for declared vars, defaults for unknown."""
        from src.plugins.manifest import PluginManifest

        data = {
            "id": "test", "name": "Test", "version": "1.0.0",
            "variables": {
                "simple": {
                    "temp": {"description": "Temperature", "type": "number"},
                },
            },
        }
        manifest = PluginManifest.from_dict(data)
        meta = manifest.variables.get_variable_metadata("temp")
        assert meta.description == "Temperature"
        assert meta.type == "number"

        unknown = manifest.variables.get_variable_metadata("unknown_field")
        assert unknown.description == ""
        assert unknown.type == "string"

    def test_dict_format_max_length_merges_into_top_level(self):
        """max_length in variable metadata is merged into the top-level max_lengths dict."""
        from src.plugins.manifest import PluginManifest

        data = {
            "id": "test", "name": "Test", "version": "1.0.0",
            "variables": {
                "simple": {
                    "temp": {"max_length": 3},
                    "status": {"max_length": 10},
                },
            },
        }
        manifest = PluginManifest.from_dict(data)
        assert manifest.max_lengths["temp"] == 3
        assert manifest.max_lengths["status"] == 10

    def test_top_level_max_lengths_take_precedence(self):
        """Explicit top-level max_lengths override per-variable metadata max_length."""
        from src.plugins.manifest import PluginManifest

        data = {
            "id": "test", "name": "Test", "version": "1.0.0",
            "max_lengths": {"temp": 5},
            "variables": {
                "simple": {"temp": {"max_length": 3}},
            },
        }
        manifest = PluginManifest.from_dict(data)
        assert manifest.max_lengths["temp"] == 5

    def test_validate_manifest_accepts_dict_simple(self):
        """validate_manifest accepts dict format for variables.simple."""
        from src.plugins.manifest import validate_manifest

        data = {
            "id": "test", "name": "Test", "version": "1.0.0",
            "variables": {"simple": {"a": {"description": "A var"}}},
        }
        is_valid, errors = validate_manifest(data)
        assert is_valid, errors

    def test_validate_manifest_rejects_invalid_simple_type(self):
        """validate_manifest rejects non-list/non-dict simple."""
        from src.plugins.manifest import validate_manifest

        data = {
            "id": "test", "name": "Test", "version": "1.0.0",
            "variables": {"simple": "not_valid"},
        }
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("simple" in e for e in errors)


class TestManifestScreenshots:
    """Tests for plugin screenshot configuration."""

    def test_screenshots_entries_reference_existing_files(self):
        """CI Test: All screenshot src paths in manifest must exist on disk."""
        plugins = get_plugin_directories()

        if not plugins:
            pytest.skip("No plugins found")

        missing_files: List[str] = []

        for plugin_dir in plugins:
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                continue

            manifest = load_manifest(plugin_dir)
            screenshots = manifest.get("screenshots", [])

            for screenshot in screenshots:
                src = screenshot.get("src", "")
                if not src:
                    continue
                normalised = src.lstrip("./")
                full_path = plugin_dir / normalised
                if not full_path.exists():
                    missing_files.append(
                        f"{plugin_dir.name}: screenshots entry '{src}' "
                        f"not found at {full_path}"
                    )

        assert not missing_files, (
            "Screenshot files referenced in manifests do not exist:\n"
            + "\n".join(f"  - {f}" for f in missing_files)
        )

    def test_screenshots_array_is_list_when_present(self):
        """CI Test: screenshots field must be an array if provided."""
        plugins = get_plugin_directories()

        if not plugins:
            pytest.skip("No plugins found")

        invalid: List[str] = []

        for plugin_dir in plugins:
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                continue

            manifest = load_manifest(plugin_dir)
            screenshots = manifest.get("screenshots")
            if screenshots is not None and not isinstance(screenshots, list):
                invalid.append(
                    f"{plugin_dir.name}: 'screenshots' must be an array, "
                    f"got {type(screenshots).__name__}"
                )

        assert not invalid, (
            "Invalid screenshots field types:\n" + "\n".join(f"  - {i}" for i in invalid)
        )

    def test_each_screenshot_entry_has_src(self):
        """CI Test: Each screenshot entry must have a 'src' field."""
        plugins = get_plugin_directories()

        if not plugins:
            pytest.skip("No plugins found")

        missing_src: List[str] = []

        for plugin_dir in plugins:
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                continue

            manifest = load_manifest(plugin_dir)
            screenshots = manifest.get("screenshots", [])

            for idx, screenshot in enumerate(screenshots):
                if not isinstance(screenshot, dict) or "src" not in screenshot:
                    missing_src.append(
                        f"{plugin_dir.name}: screenshots[{idx}] missing 'src' field"
                    )

        assert not missing_src, (
            "Screenshot entries missing 'src':\n" + "\n".join(f"  - {s}" for s in missing_src)
        )

    def test_at_most_one_primary_screenshot(self):
        """CI Test: At most one screenshot should have primary=true."""
        plugins = get_plugin_directories()

        if not plugins:
            pytest.skip("No plugins found")

        multiple_primary: List[str] = []

        for plugin_dir in plugins:
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                continue

            manifest = load_manifest(plugin_dir)
            screenshots = manifest.get("screenshots", [])
            primary_count = sum(
                1 for s in screenshots if isinstance(s, dict) and s.get("primary") is True
            )
            if primary_count > 1:
                multiple_primary.append(
                    f"{plugin_dir.name}: {primary_count} screenshots marked as primary "
                    f"(only one allowed)"
                )

        assert not multiple_primary, (
            "Plugins with multiple primary screenshots:\n"
            + "\n".join(f"  - {m}" for m in multiple_primary)
        )


class TestManifestCompleteness:
    """Tests that manifests include recommended fields for full functionality."""

    def test_all_manifests_have_settings_schema(self):
        """CI Test: All plugin manifests should define a settings_schema."""
        plugins = get_plugin_directories()

        if not plugins:
            pytest.skip("No plugins found")

        missing: List[str] = []

        for plugin_dir in plugins:
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                continue

            manifest = load_manifest(plugin_dir)
            if "settings_schema" not in manifest:
                missing.append(plugin_dir.name)

        assert not missing, (
            "Plugins missing 'settings_schema':\n"
            + "\n".join(f"  - {m}" for m in missing)
        )

    def test_all_manifests_have_variables(self):
        """CI Test: All plugin manifests should define a variables section."""
        plugins = get_plugin_directories()

        if not plugins:
            pytest.skip("No plugins found")

        missing: List[str] = []

        for plugin_dir in plugins:
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                continue

            manifest = load_manifest(plugin_dir)
            if "variables" not in manifest:
                missing.append(plugin_dir.name)

        assert not missing, (
            "Plugins missing 'variables':\n"
            + "\n".join(f"  - {m}" for m in missing)
        )

    def test_settings_schema_is_object_type(self):
        """CI Test: settings_schema must be a JSON object with 'type': 'object'."""
        plugins = get_plugin_directories()

        if not plugins:
            pytest.skip("No plugins found")

        invalid: List[str] = []

        for plugin_dir in plugins:
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                continue

            manifest = load_manifest(plugin_dir)
            schema = manifest.get("settings_schema")
            if schema is None:
                continue
            if not isinstance(schema, dict):
                invalid.append(f"{plugin_dir.name}: settings_schema must be a dict")
            elif schema.get("type") != "object":
                invalid.append(
                    f"{plugin_dir.name}: settings_schema['type'] must be 'object', "
                    f"got {schema.get('type')!r}"
                )

        assert not invalid, (
            "Manifests with invalid settings_schema:\n"
            + "\n".join(f"  - {i}" for i in invalid)
        )


class TestPluginIconsAndCategories:
    """Tests for plugin display configuration."""
    
    def test_icon_values_are_valid_strings(self):
        """CI Test: Icon field should be a valid string if present."""
        plugins = get_plugin_directories()
        
        if not plugins:
            pytest.skip("No plugins found")
        
        invalid: List[str] = []
        
        for plugin_dir in plugins:
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            
            manifest = load_manifest(plugin_dir)
            icon = manifest.get("icon")
            
            if icon is not None and not isinstance(icon, str):
                invalid.append(f"{plugin_dir.name}: icon must be a string, got {type(icon).__name__}")
            elif icon is not None and len(icon) == 0:
                invalid.append(f"{plugin_dir.name}: icon cannot be empty string")
        
        assert not invalid, (
            "Invalid icon values:\n" + "\n".join(f"  - {i}" for i in invalid)
        )
    
    def test_category_values_are_valid(self):
        """CI Test: Category field should be a valid category if present."""
        plugins = get_plugin_directories()
        
        if not plugins:
            pytest.skip("No plugins found")
        
        valid_categories = {"art", "data", "transit", "weather", "entertainment", "utility", "home"}
        invalid: List[str] = []
        
        for plugin_dir in plugins:
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            
            manifest = load_manifest(plugin_dir)
            category = manifest.get("category")
            
            if category is not None and category not in valid_categories:
                invalid.append(
                    f"{plugin_dir.name}: category '{category}' not in {valid_categories}"
                )
        
        assert not invalid, (
            "Invalid category values:\n" + "\n".join(f"  - {i}" for i in invalid)
        )

