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
from typing import Dict, List

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
        from src.plugins.manifest import PluginManifest

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


# ---------------------------------------------------------------------------
# Unit tests for manifest.py internals (not CI plugin-directory scans)
# ---------------------------------------------------------------------------

class TestVariableNamesSubArrays:
    """Tests for VariablesSchema.get_all_variable_names with sub-arrays."""

    def test_get_all_variable_names_with_sub_arrays(self):
        """get_all_variable_names includes sub-array field patterns."""
        from src.plugins.manifest import VariablesSchema, VariableArraySchema

        sub = VariableArraySchema(
            name="legs",
            label_field="carrier",
            item_fields=["carrier", "duration"],
        )
        array_schema = VariableArraySchema(
            name="routes",
            label_field="name",
            item_fields=["name", "eta"],
            sub_arrays={"legs": sub},
        )
        schema = VariablesSchema(
            simple=["status"],
            arrays={"routes": array_schema},
        )
        names = schema.get_all_variable_names("test")
        assert "status" in names
        assert "routes" in names
        assert "routes.*.name" in names
        assert "routes.*.eta" in names
        assert "routes.*.legs" in names
        assert "routes.*.legs.*.carrier" in names
        assert "routes.*.legs.*.duration" in names

    def test_get_all_variable_names_empty(self):
        """get_all_variable_names returns empty list when no variables defined."""
        from src.plugins.manifest import VariablesSchema

        schema = VariablesSchema()
        assert schema.get_all_variable_names("test") == []


class TestFromDictEdgeCases:
    """Tests for PluginManifest.from_dict edge cases and branch coverage."""

    def test_dict_simple_with_non_dict_meta(self):
        """from_dict handles dict simple where a value is not a dict (skips metadata)."""
        from src.plugins.manifest import PluginManifest

        data = {
            "id": "test", "name": "Test", "version": "1.0.0",
            "variables": {
                "simple": {
                    "alpha": "just_a_string",
                    "beta": {"description": "Beta var"},
                },
            },
        }
        manifest = PluginManifest.from_dict(data)
        assert "alpha" in manifest.variables.simple
        assert "beta" in manifest.variables.simple
        assert "alpha" not in manifest.variables.metadata
        assert "beta" in manifest.variables.metadata

    def test_simple_neither_list_nor_dict(self):
        """from_dict treats non-list/non-dict simple as empty."""
        from src.plugins.manifest import PluginManifest

        data = {
            "id": "test", "name": "Test", "version": "1.0.0",
            "variables": {"simple": 42},
        }
        manifest = PluginManifest.from_dict(data)
        assert manifest.variables.simple == []

    def test_groups_with_non_dict_group_data(self):
        """from_dict handles a group value that is not a dict (uses str fallback)."""
        from src.plugins.manifest import PluginManifest

        data = {
            "id": "test", "name": "Test", "version": "1.0.0",
            "variables": {
                "groups": {
                    "misc": "Miscellaneous",
                },
                "simple": ["a"],
            },
        }
        manifest = PluginManifest.from_dict(data)
        assert manifest.variables.groups["misc"].label == "Miscellaneous"

    def test_groups_non_dict_raw_skipped(self):
        """from_dict skips groups parsing when groups_raw is not a dict."""
        from src.plugins.manifest import PluginManifest

        data = {
            "id": "test", "name": "Test", "version": "1.0.0",
            "variables": {"groups": "invalid", "simple": ["a"]},
        }
        manifest = PluginManifest.from_dict(data)
        assert manifest.variables.groups == {}

    def test_screenshots_parsed_from_dict(self):
        """from_dict parses valid screenshot entries."""
        from src.plugins.manifest import PluginManifest

        data = {
            "id": "test", "name": "Test", "version": "1.0.0",
            "screenshots": [
                {"src": "docs/board.png", "alt": "Board", "caption": "Main", "primary": True},
                {"src": "docs/config.png", "alt": "Config"},
            ],
        }
        manifest = PluginManifest.from_dict(data)
        assert len(manifest.screenshots) == 2
        assert manifest.screenshots[0].src == "docs/board.png"
        assert manifest.screenshots[0].primary is True
        assert manifest.screenshots[0].caption == "Main"
        assert manifest.screenshots[1].caption == ""
        assert manifest.screenshots[1].primary is False

    def test_screenshots_skips_invalid_entries(self):
        """from_dict skips screenshot entries missing required fields."""
        from src.plugins.manifest import PluginManifest

        data = {
            "id": "test", "name": "Test", "version": "1.0.0",
            "screenshots": [
                {"src": "docs/board.png"},
                "not_a_dict",
                {"alt": "Missing src"},
                {"src": "docs/ok.png", "alt": "Valid"},
            ],
        }
        manifest = PluginManifest.from_dict(data)
        assert len(manifest.screenshots) == 1
        assert manifest.screenshots[0].alt == "Valid"

    def test_from_dict_parses_arrays_with_sub_arrays(self):
        """from_dict parses array schemas including sub_arrays."""
        from src.plugins.manifest import PluginManifest

        data = {
            "id": "test", "name": "Test", "version": "1.0.0",
            "variables": {
                "arrays": {
                    "routes": {
                        "label_field": "name",
                        "item_fields": ["name", "eta"],
                        "sub_arrays": {
                            "stops": {
                                "key_type": "dynamic",
                                "key_field": "stop_id",
                                "item_fields": ["stop_name", "arrival"],
                                "label_field": "stop_name",
                            }
                        }
                    }
                }
            },
        }
        manifest = PluginManifest.from_dict(data)
        assert "routes" in manifest.variables.arrays
        routes = manifest.variables.arrays["routes"]
        assert routes.item_fields == ["name", "eta"]
        assert routes.label_field == "name"
        assert "stops" in routes.sub_arrays
        stops = routes.sub_arrays["stops"]
        assert stops.key_type == "dynamic"
        assert stops.key_field == "stop_id"
        assert stops.item_fields == ["stop_name", "arrival"]


class TestToDictSerialization:
    """Tests for PluginManifest.to_dict serialization."""

    def test_to_dict_basic_fields(self):
        """to_dict includes all basic manifest fields."""
        from src.plugins.manifest import PluginManifest

        data = {
            "id": "test_plugin", "name": "Test Plugin", "version": "2.0.0",
            "description": "A test", "author": "Tester",
            "repository": "https://example.com", "documentation": "DOCS.md",
            "settings_schema": {"type": "object"},
            "env_vars": [{"name": "API_KEY"}],
            "variables": {"simple": ["temp"]},
            "max_lengths": {"temp": 5},
            "color_rules_schema": {"rules": []},
            "icon": "thermometer", "category": "weather",
            "fiestaboard_version": ">=2.0.0",
            "supports_triggers": True,
            "screenshots": [
                {"src": "docs/board.png", "alt": "Board", "primary": True},
            ],
        }
        manifest = PluginManifest.from_dict(data)
        result = manifest.to_dict()

        assert result["id"] == "test_plugin"
        assert result["name"] == "Test Plugin"
        assert result["version"] == "2.0.0"
        assert result["description"] == "A test"
        assert result["author"] == "Tester"
        assert result["repository"] == "https://example.com"
        assert result["documentation"] == "DOCS.md"
        # When supports_triggers is True the loader auto-injects a
        # canonical `trigger_page_id` field — verify it's present and that
        # the original `type: object` marker is preserved.
        assert result["settings_schema"]["type"] == "object"
        assert "trigger_page_id" in result["settings_schema"].get(
            "properties", {}
        )
        assert (
            result["settings_schema"]["properties"]["trigger_page_id"][
                "ui:widget"
            ]
            == "page-picker"
        )
        assert result["env_vars"] == [{"name": "API_KEY"}]
        assert result["max_lengths"] == {"temp": 5}
        assert result["icon"] == "thermometer"
        assert result["category"] == "weather"
        assert result["fiestaboard_version"] == ">=2.0.0"
        assert result["supports_triggers"] is True
        assert len(result["screenshots"]) == 1
        assert result["screenshots"][0]["src"] == "docs/board.png"
        assert result["screenshots"][0]["primary"] is True

    def test_to_dict_includes_variable_metadata(self):
        """to_dict includes variable_metadata when metadata is present."""
        from src.plugins.manifest import PluginManifest

        data = {
            "id": "test", "name": "Test", "version": "1.0.0",
            "variables": {
                "simple": {
                    "temp": {"description": "Temperature", "type": "number",
                             "max_length": 5, "group": "current", "example": "72"},
                },
            },
        }
        manifest = PluginManifest.from_dict(data)
        result = manifest.to_dict()

        assert "variable_metadata" in result
        meta = result["variable_metadata"]["temp"]
        assert meta["description"] == "Temperature"
        assert meta["type"] == "number"
        assert meta["max_length"] == 5
        assert meta["group"] == "current"
        assert meta["example"] == "72"

    def test_to_dict_includes_variable_groups(self):
        """to_dict includes variable_groups when groups are present."""
        from src.plugins.manifest import PluginManifest

        data = {
            "id": "test", "name": "Test", "version": "1.0.0",
            "variables": {
                "groups": {"time": {"label": "Time Info"}},
                "simple": ["hour"],
            },
        }
        manifest = PluginManifest.from_dict(data)
        result = manifest.to_dict()

        assert "variable_groups" in result
        assert result["variable_groups"]["time"]["label"] == "Time Info"

    def test_to_dict_omits_metadata_and_groups_when_empty(self):
        """to_dict omits variable_metadata and variable_groups when not present."""
        from src.plugins.manifest import PluginManifest

        data = {
            "id": "test", "name": "Test", "version": "1.0.0",
            "variables": {"simple": ["a"]},
        }
        manifest = PluginManifest.from_dict(data)
        result = manifest.to_dict()

        assert "variable_metadata" not in result
        assert "variable_groups" not in result


class TestValidateManifestEdgeCases:
    """Tests for validate_manifest covering remaining branches."""

    def test_missing_required_fields(self):
        """validate_manifest returns early when required fields are missing."""
        from src.plugins.manifest import validate_manifest

        data = {"description": "no required fields"}
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("Missing required field: id" in e for e in errors)
        assert any("Missing required field: name" in e for e in errors)
        assert any("Missing required field: version" in e for e in errors)

    def test_empty_plugin_id(self):
        """validate_manifest rejects empty plugin id."""
        from src.plugins.manifest import validate_manifest

        data = {"id": "", "name": "Test", "version": "1.0.0"}
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("cannot be empty" in e for e in errors)

    def test_id_invalid_characters(self):
        """validate_manifest rejects id with uppercase or special chars."""
        from src.plugins.manifest import validate_manifest

        data = {"id": "my-Plugin", "name": "Test", "version": "1.0.0"}
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("lowercase letters" in e for e in errors)

    def test_version_wrong_part_count(self):
        """validate_manifest rejects version with wrong number of parts."""
        from src.plugins.manifest import validate_manifest

        data = {"id": "test", "name": "Test", "version": "1.0"}
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("X.Y.Z" in e for e in errors)

    def test_version_non_digit_parts(self):
        """validate_manifest rejects version with non-digit parts."""
        from src.plugins.manifest import validate_manifest

        data = {"id": "test", "name": "Test", "version": "1.0.beta"}
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("integers" in e for e in errors)

    def test_settings_schema_not_dict(self):
        """validate_manifest rejects non-dict settings_schema."""
        from src.plugins.manifest import validate_manifest

        data = {"id": "test", "name": "Test", "version": "1.0.0",
                "settings_schema": "invalid"}
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("settings_schema must be an object" in e for e in errors)

    def test_env_vars_not_list(self):
        """validate_manifest rejects non-list env_vars."""
        from src.plugins.manifest import validate_manifest

        data = {"id": "test", "name": "Test", "version": "1.0.0",
                "env_vars": "invalid"}
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("env_vars must be an array" in e for e in errors)

    def test_env_vars_item_not_dict(self):
        """validate_manifest rejects env_vars item that is not a dict."""
        from src.plugins.manifest import validate_manifest

        data = {"id": "test", "name": "Test", "version": "1.0.0",
                "env_vars": ["not_a_dict"]}
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("must be an object" in e for e in errors)

    def test_env_vars_item_missing_name(self):
        """validate_manifest rejects env_vars item missing name field."""
        from src.plugins.manifest import validate_manifest

        data = {"id": "test", "name": "Test", "version": "1.0.0",
                "env_vars": [{"description": "no name"}]}
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("missing required field: name" in e for e in errors)

    def test_variables_not_dict(self):
        """validate_manifest rejects non-dict variables."""
        from src.plugins.manifest import validate_manifest

        data = {"id": "test", "name": "Test", "version": "1.0.0",
                "variables": "invalid"}
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("variables must be an object" in e for e in errors)

    def test_variables_groups_not_dict(self):
        """validate_manifest rejects non-dict variables.groups."""
        from src.plugins.manifest import validate_manifest

        data = {"id": "test", "name": "Test", "version": "1.0.0",
                "variables": {"groups": "invalid"}}
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("variables.groups must be an object" in e for e in errors)

    def test_variables_arrays_not_dict(self):
        """validate_manifest rejects non-dict variables.arrays."""
        from src.plugins.manifest import validate_manifest

        data = {"id": "test", "name": "Test", "version": "1.0.0",
                "variables": {"arrays": "invalid"}}
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("variables.arrays must be an object" in e for e in errors)

    def test_variables_array_item_not_dict(self):
        """validate_manifest rejects array schema that is not a dict."""
        from src.plugins.manifest import validate_manifest

        data = {"id": "test", "name": "Test", "version": "1.0.0",
                "variables": {"arrays": {"routes": "invalid"}}}
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("routes must be an object" in e for e in errors)

    def test_variables_array_missing_item_fields(self):
        """validate_manifest rejects array schema missing item_fields."""
        from src.plugins.manifest import validate_manifest

        data = {"id": "test", "name": "Test", "version": "1.0.0",
                "variables": {"arrays": {"routes": {"label_field": "name"}}}}
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("missing item_fields" in e for e in errors)

    def test_max_lengths_not_dict(self):
        """validate_manifest rejects non-dict max_lengths."""
        from src.plugins.manifest import validate_manifest

        data = {"id": "test", "name": "Test", "version": "1.0.0",
                "max_lengths": "invalid"}
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("max_lengths must be an object" in e for e in errors)

    def test_max_lengths_non_positive_integer(self):
        """validate_manifest rejects max_lengths with non-positive integer values."""
        from src.plugins.manifest import validate_manifest

        data = {"id": "test", "name": "Test", "version": "1.0.0",
                "max_lengths": {"temp": 0}}
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("positive integer" in e for e in errors)

    def test_max_lengths_non_int_value(self):
        """validate_manifest rejects max_lengths with non-integer values."""
        from src.plugins.manifest import validate_manifest

        data = {"id": "test", "name": "Test", "version": "1.0.0",
                "max_lengths": {"temp": "five"}}
        is_valid, errors = validate_manifest(data)
        assert not is_valid
        assert any("positive integer" in e for e in errors)


class TestLoadManifestFunction:
    """Tests for the load_manifest function."""

    def test_load_manifest_file_not_found(self):
        """load_manifest returns error when file doesn't exist."""
        from src.plugins.manifest import load_manifest as _load_manifest

        result, errors = _load_manifest(Path("/nonexistent/path/manifest.json"))
        assert result is None
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_load_manifest_invalid_json(self):
        """load_manifest returns error for invalid JSON."""
        from src.plugins.manifest import load_manifest as _load_manifest
        from unittest.mock import patch, mock_open

        bad_json = "{invalid json content"
        with patch("pathlib.Path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=bad_json)):
            result, errors = _load_manifest(Path("fake/manifest.json"))

        assert result is None
        assert len(errors) == 1
        assert "Invalid JSON" in errors[0]

    def test_load_manifest_generic_read_exception(self):
        """load_manifest returns error when file read fails."""
        from src.plugins.manifest import load_manifest as _load_manifest
        from unittest.mock import patch

        with patch("pathlib.Path.exists", return_value=True), \
             patch("builtins.open", side_effect=PermissionError("denied")):
            result, errors = _load_manifest(Path("fake/manifest.json"))

        assert result is None
        assert len(errors) == 1
        assert "Failed to read manifest" in errors[0]

    def test_load_manifest_parse_exception(self):
        """load_manifest returns error when from_dict raises."""
        from src.plugins.manifest import load_manifest as _load_manifest
        from unittest.mock import patch, mock_open

        valid_json = '{"id": "test", "name": "Test", "version": "1.0.0"}'
        with patch("pathlib.Path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=valid_json)), \
             patch("src.plugins.manifest.PluginManifest.from_dict",
                   side_effect=KeyError("boom")):
            result, errors = _load_manifest(Path("fake/manifest.json"))

        assert result is None
        assert len(errors) == 1
        assert "Failed to parse manifest" in errors[0]

