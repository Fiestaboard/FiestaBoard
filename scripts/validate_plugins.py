#!/usr/bin/env python3
"""Validate plugin integrity - unique IDs, valid manifests, directory structure.

This script is run during CI to ensure:
1. All plugin IDs are unique
2. Plugin IDs match their directory names
3. All manifest.json files are valid
4. Required files exist (__init__.py, manifest.json)
5. Tests directory exists (warning if missing)
6. (--registry) All plugin-registry.json repos are reachable and well-formed

Usage:
    python scripts/validate_plugins.py [OPTIONS]

Options:
    --strict        Fail on warnings (missing tests, etc.)
    --verbose       Show detailed output
    --plugin=ID     Validate specific plugin only
    --registry      Validate plugin-registry.json repo URLs and structure

Exit codes:
    0 - All validations passed
    1 - Validation errors found
    2 - Configuration/setup error
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Project paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
PLUGINS_DIR = PROJECT_ROOT / "plugins"

# Directories to skip
SKIP_DIRECTORIES = {"_template", "__pycache__"}


class ValidationResult:
    """Result of validating a single plugin."""
    
    def __init__(self, plugin_id: str):
        self.plugin_id = plugin_id
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0
    
    def add_error(self, message: str):
        self.errors.append(message)
    
    def add_warning(self, message: str):
        self.warnings.append(message)
    
    def __str__(self):
        status = "PASS" if self.is_valid else "FAIL"
        return f"{self.plugin_id}: {status}"


def discover_plugin_directories() -> List[Path]:
    """Discover all plugin directories.
    
    Returns:
        List of paths to plugin directories
    """
    plugins = []
    
    if not PLUGINS_DIR.exists():
        return plugins
    
    for item in PLUGINS_DIR.iterdir():
        if not item.is_dir():
            continue
        if item.name in SKIP_DIRECTORIES:
            continue
        if item.name.startswith("."):
            continue
        plugins.append(item)
    
    return sorted(plugins, key=lambda p: p.name)


def load_manifest(plugin_dir: Path) -> Tuple[Optional[Dict], Optional[str]]:
    """Load a plugin's manifest.json.
    
    Returns:
        Tuple of (manifest_dict, error_message)
    """
    manifest_path = plugin_dir / "manifest.json"
    
    if not manifest_path.exists():
        return None, f"manifest.json not found in {plugin_dir.name}"
    
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON in manifest.json: {e}"
    except Exception as e:
        return None, f"Failed to read manifest.json: {e}"


def validate_manifest_schema(manifest: Dict, plugin_dir_name: str) -> List[str]:
    """Validate manifest against required schema.
    
    Returns:
        List of error messages
    """
    errors = []
    
    # Required fields
    required_fields = ["id", "name", "version"]
    for field in required_fields:
        if field not in manifest:
            errors.append(f"Missing required field: {field}")
    
    if errors:
        return errors
    
    # Validate ID format
    plugin_id = manifest.get("id", "")
    if not plugin_id:
        errors.append("Plugin id cannot be empty")
    elif not plugin_id[0].islower() or not plugin_id[0].isalpha():
        errors.append("Plugin id must start with a lowercase letter")
    elif not all(c.islower() or c.isdigit() or c == '_' for c in plugin_id):
        errors.append("Plugin id must contain only lowercase letters, numbers, and underscores")
    
    # Validate ID matches directory name
    if plugin_id != plugin_dir_name:
        errors.append(f"Plugin id '{plugin_id}' does not match directory name '{plugin_dir_name}'")
    
    # Validate version format (semantic versioning)
    version = manifest.get("version", "")
    if version:
        parts = version.split(".")
        if len(parts) != 3:
            errors.append("Version must be in format X.Y.Z (semantic versioning)")
        else:
            for part in parts:
                if not part.isdigit():
                    errors.append("Version parts must be integers")
                    break
    
    # Validate settings_schema if present
    settings = manifest.get("settings_schema", {})
    if settings and not isinstance(settings, dict):
        errors.append("settings_schema must be an object")
    
    # Validate env_vars if present
    env_vars = manifest.get("env_vars", [])
    if not isinstance(env_vars, list):
        errors.append("env_vars must be an array")
    else:
        for i, env_var in enumerate(env_vars):
            if not isinstance(env_var, dict):
                errors.append(f"env_vars[{i}] must be an object")
            elif "name" not in env_var:
                errors.append(f"env_vars[{i}] missing required field: name")
    
    # Validate variables if present
    variables = manifest.get("variables", {})
    if variables and not isinstance(variables, dict):
        errors.append("variables must be an object")
    
    # Validate max_lengths if present
    max_lengths = manifest.get("max_lengths", {})
    if max_lengths:
        if not isinstance(max_lengths, dict):
            errors.append("max_lengths must be an object")
        else:
            for key, value in max_lengths.items():
                if not isinstance(value, int) or value < 1:
                    errors.append(f"max_lengths.{key} must be a positive integer")
    
    # Validate icon if present
    icon = manifest.get("icon", "")
    if icon and not isinstance(icon, str):
        errors.append("icon must be a string")
    
    # Validate category if present
    valid_categories = ["art", "data", "transit", "weather", "entertainment", "utility", "home"]
    category = manifest.get("category", "")
    if category and category not in valid_categories:
        errors.append(f"category must be one of: {', '.join(valid_categories)}")
    
    return errors


def validate_plugin_structure(plugin_dir: Path) -> Tuple[List[str], List[str]]:
    """Validate plugin directory structure.
    
    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []
    
    # Required files
    required_files = ["__init__.py", "manifest.json"]
    for filename in required_files:
        if not (plugin_dir / filename).exists():
            errors.append(f"Missing required file: {filename}")
    
    # Recommended files
    if not (plugin_dir / "README.md").exists():
        warnings.append("Missing recommended file: README.md")
    
    # Tests directory
    tests_dir = plugin_dir / "tests"
    if not tests_dir.exists():
        warnings.append("Missing tests/ directory - tests are required for new plugins")
    else:
        # Check for test files
        test_files = list(tests_dir.glob("test_*.py"))
        if not test_files:
            warnings.append("No test files (test_*.py) found in tests/ directory")
    
    return errors, warnings


def validate_plugin(plugin_dir: Path) -> ValidationResult:
    """Validate a single plugin.
    
    Returns:
        ValidationResult with errors and warnings
    """
    result = ValidationResult(plugin_dir.name)
    
    # Validate structure
    structure_errors, structure_warnings = validate_plugin_structure(plugin_dir)
    for error in structure_errors:
        result.add_error(error)
    for warning in structure_warnings:
        result.add_warning(warning)
    
    # Load and validate manifest
    manifest, load_error = load_manifest(plugin_dir)
    if load_error:
        result.add_error(load_error)
        return result
    
    # Validate manifest schema
    schema_errors = validate_manifest_schema(manifest, plugin_dir.name)
    for error in schema_errors:
        result.add_error(error)
    
    return result


def validate_unique_ids(plugins: List[Path]) -> List[str]:
    """Check that all plugin IDs are unique.
    
    Returns:
        List of error messages for duplicate IDs
    """
    errors = []
    id_to_dirs: Dict[str, List[str]] = {}
    
    for plugin_dir in plugins:
        manifest, _ = load_manifest(plugin_dir)
        if manifest:
            plugin_id = manifest.get("id", "")
            if plugin_id:
                if plugin_id not in id_to_dirs:
                    id_to_dirs[plugin_id] = []
                id_to_dirs[plugin_id].append(plugin_dir.name)
    
    # Check for duplicates
    for plugin_id, dirs in id_to_dirs.items():
        if len(dirs) > 1:
            errors.append(
                f"Duplicate plugin ID '{plugin_id}' found in directories: {', '.join(dirs)}"
            )
    
    return errors


# ---------------------------------------------------------------------------
# Registry validation
# ---------------------------------------------------------------------------

REGISTRY_FILE = PROJECT_ROOT / "plugin-registry.json"
REGISTRY_PREFIX = "fiestaboard-plugin--"
REGISTRY_NAME_RE = re.compile(r"^fiestaboard-plugin--[a-z][a-z0-9-]*$")
SEMVER_CONSTRAINT_RE = re.compile(r"^(>=|>|<=|<|==|!=)\s*\d+\.\d+\.\d+$")


def _repo_name_from_url(url: str) -> str:
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    return url.rsplit("/", 1)[-1] if "/" in url else ""


def _plugin_id_from_repo_name(repo_name: str) -> str:
    if repo_name.startswith(REGISTRY_PREFIX):
        return repo_name[len(REGISTRY_PREFIX):].replace("-", "_")
    return repo_name.replace("-", "_")


def validate_registry_entry(entry: Dict, verbose: bool) -> List[str]:
    """Validate a single registry entry dict. Returns list of error strings."""
    errors = []
    plugin_id = entry.get("id", "")
    repo_url = entry.get("repository", "")

    if not plugin_id:
        errors.append("Entry missing 'id' field")
        return errors
    if not repo_url:
        errors.append(f"[{plugin_id}] Missing 'repository' field")
        return errors

    # 1. Naming convention
    repo_name = _repo_name_from_url(repo_url)
    if not REGISTRY_NAME_RE.match(repo_name):
        errors.append(
            f"[{plugin_id}] Repository name '{repo_name}' does not follow "
            f"'{REGISTRY_PREFIX}{{name}}' convention"
        )

    # 2. ID consistency with repo name
    derived_id = _plugin_id_from_repo_name(repo_name)
    if derived_id != plugin_id:
        errors.append(
            f"[{plugin_id}] Registry id '{plugin_id}' does not match id "
            f"derived from repo name '{repo_name}' (expected '{derived_id}')"
        )

    # 3. fiestaboard_version is a valid semver constraint if present
    fv = entry.get("fiestaboard_version", "")
    if fv and not SEMVER_CONSTRAINT_RE.match(fv.strip()):
        errors.append(
            f"[{plugin_id}] fiestaboard_version '{fv}' is not a valid semver "
            f"constraint (expected e.g. '>=2.10.0')"
        )

    # 4. Repo reachability via git ls-remote
    if verbose:
        print(f"  Checking {repo_url} ...", end=" ", flush=True)
    # Validate the URL from the registry JSON before passing to subprocess
    # (py/command-line-injection). Only HTTPS URLs are permitted; re-derive
    # from a regex match so CodeQL does not track the value as tainted.
    if not repo_url.startswith("https://"):
        errors.append(f"[{plugin_id}] Only HTTPS repository URLs are supported")
        if verbose:
            print("REJECTED")
        return errors
    _url_m = re.fullmatch(r"https://[^\x00-\x1f\s\"'<>\\]+", repo_url)
    if not _url_m:
        errors.append(f"[{plugin_id}] Repository URL contains invalid characters: {repo_url!r}")
        if verbose:
            print("REJECTED")
        return errors
    _safe_repo_url = _url_m.group(0)
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", _safe_repo_url],
            capture_output=True,
            text=True,
            timeout=30,
            env={**__import__("os").environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        if result.returncode != 0:
            errors.append(f"[{plugin_id}] Repository unreachable: {repo_url}")
            if verbose:
                print("UNREACHABLE")
        else:
            if verbose:
                print("OK")
    except subprocess.TimeoutExpired:
        errors.append(f"[{plugin_id}] Repository check timed out: {repo_url}")
        if verbose:
            print("TIMEOUT")
    except Exception as exc:
        errors.append(f"[{plugin_id}] Repository check failed: {exc}")
        if verbose:
            print(f"ERROR: {exc}")

    return errors


def validate_registry(verbose: bool) -> List[str]:
    """Validate plugin-registry.json. Returns list of error strings."""
    errors: List[str] = []

    if not REGISTRY_FILE.exists():
        return [f"Registry file not found: {REGISTRY_FILE}"]

    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        return [f"Registry file is invalid JSON: {exc}"]

    plugins = data.get("plugins", [])
    if not isinstance(plugins, list):
        return ["Registry 'plugins' field must be an array"]

    if verbose:
        print(f"Validating {len(plugins)} registry entries...")
        print()

    seen_ids: Dict[str, int] = {}
    for i, entry in enumerate(plugins):
        entry_errors = validate_registry_entry(entry, verbose)
        errors.extend(entry_errors)

        pid = entry.get("id", f"<entry {i}>")
        if pid in seen_ids:
            errors.append(f"Duplicate registry id '{pid}'")
        seen_ids[pid] = i

    return errors


def main():
    parser = argparse.ArgumentParser(
        description="Validate FiestaBoard plugin integrity"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on warnings (missing tests, etc.)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output"
    )
    parser.add_argument(
        "--plugin",
        type=str,
        help="Validate specific plugin only"
    )
    parser.add_argument(
        "--registry",
        action="store_true",
        help="Validate plugin-registry.json repository URLs and structure",
    )

    args = parser.parse_args()
    
    print("FiestaBoard Plugin Validator")
    print("=" * 50)
    print()

    # Registry validation mode
    if args.registry:
        print("Validating plugin registry...")
        print(f"Registry: {REGISTRY_FILE}")
        print()
        registry_errors = validate_registry(args.verbose)
        print()
        print("=" * 50)
        print("REGISTRY VALIDATION SUMMARY")
        print("=" * 50)
        if registry_errors:
            print(f"Errors: {len(registry_errors)}")
            for err in registry_errors:
                print(f"  ERROR: {err}")
            print()
            print("REGISTRY VALIDATION FAILED")
            sys.exit(1)
        else:
            print("Errors: 0")
            print()
            print("REGISTRY VALIDATION PASSED")
            sys.exit(0)

    # Discover plugins
    plugins = discover_plugin_directories()
    
    if args.plugin:
        plugins = [p for p in plugins if p.name == args.plugin]
        if not plugins:
            print(f"Error: Plugin '{args.plugin}' not found")
            sys.exit(2)
    
    if not plugins:
        print("No plugins found to validate.")
        print(f"Plugins directory: {PLUGINS_DIR}")
        sys.exit(0)
    
    print(f"Found {len(plugins)} plugin(s) to validate:")
    for p in plugins:
        print(f"  - {p.name}")
    print()
    
    # Validate each plugin
    results: List[ValidationResult] = []
    for plugin_dir in plugins:
        if args.verbose:
            print(f"Validating: {plugin_dir.name}")
        
        result = validate_plugin(plugin_dir)
        results.append(result)
        
        if args.verbose:
            if result.errors:
                for error in result.errors:
                    print(f"  ERROR: {error}")
            if result.warnings:
                for warning in result.warnings:
                    print(f"  WARNING: {warning}")
            print()
    
    # Check for duplicate IDs across all plugins
    print("Checking for duplicate plugin IDs...")
    duplicate_errors = validate_unique_ids(plugins)
    for error in duplicate_errors:
        print(f"  ERROR: {error}")
    print()
    
    # Summary
    print("=" * 50)
    print("VALIDATION SUMMARY")
    print("=" * 50)
    
    total_errors = sum(len(r.errors) for r in results) + len(duplicate_errors)
    total_warnings = sum(len(r.warnings) for r in results)
    
    passed = [r for r in results if r.is_valid]
    failed = [r for r in results if not r.is_valid]
    
    print(f"Plugins validated: {len(results)}")
    print(f"  Passed: {len(passed)}")
    print(f"  Failed: {len(failed)}")
    print(f"Total errors: {total_errors}")
    print(f"Total warnings: {total_warnings}")
    print()
    
    # List failures
    if failed:
        print("Failed plugins:")
        for result in failed:
            print(f"  - {result.plugin_id}")
            for error in result.errors:
                print(f"      ERROR: {error}")
    
    if duplicate_errors:
        print("\nDuplicate ID errors:")
        for error in duplicate_errors:
            print(f"  {error}")
    
    # List warnings
    if total_warnings > 0 and args.verbose:
        print("\nWarnings:")
        for result in results:
            for warning in result.warnings:
                print(f"  [{result.plugin_id}] {warning}")
    
    print()
    
    # Determine exit code
    if total_errors > 0:
        print("VALIDATION FAILED")
        sys.exit(1)
    elif args.strict and total_warnings > 0:
        print("VALIDATION FAILED (strict mode - warnings treated as errors)")
        sys.exit(1)
    else:
        print("VALIDATION PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()

