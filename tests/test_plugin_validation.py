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

