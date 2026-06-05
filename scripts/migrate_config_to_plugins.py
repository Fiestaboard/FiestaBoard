#!/usr/bin/env python3
"""
Migration script: Convert legacy config.json features to plugin-based structure.

This script reads the existing config.json file and migrates feature configurations
to the new plugin format. It can be run multiple times safely (idempotent).

Usage:
    python scripts/migrate_config_to_plugins.py [--dry-run] [--backup]

Options:
    --dry-run   Show what would be migrated without making changes
    --backup    Create a backup of config.json before migration
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Add src to path for imports
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Default config path
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "data" / "config.json"

# Mapping from legacy feature names to plugin IDs
FEATURE_TO_PLUGIN_MAP = {
    "weather": "weather",
    "date_time": "date_time",
    "home_assistant": "home_assistant",
    "guest_wifi": "guest_wifi",
    "star_trek_quotes": "star_trek_quotes",
    "air_fog": "air_fog",
    "muni": "muni",
    "surf": "surf",
    "baywheels": "baywheels",
    "traffic": "traffic",
    "stocks": "stocks",
    # Note: silence_schedule is a system feature, not a plugin
}

# Fields that should be renamed during migration
FIELD_RENAMES = {
    "star_trek_quotes": {
        # No renames needed currently
    },
    "weather": {
        # No renames needed currently
    },
}

# Fields that should be excluded from plugin config (handled elsewhere)
EXCLUDED_FIELDS = {
    "color_rules",  # Color rules are stored separately or in manifest
}


def load_config(config_path: Path) -> dict:
    """Load the config.json file."""
    if not config_path.exists():
        print(f"Error: Config file not found at {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        return json.load(f)


def save_config(config_path: Path, config: dict) -> None:
    """Save the config.json file."""
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    print(f"Saved config to {config_path}")


def backup_config(config_path: Path) -> Path:
    """Create a backup of the config file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = config_path.parent / f"config.json.backup_{timestamp}"
    shutil.copy2(config_path, backup_path)
    print(f"Created backup at {backup_path}")
    return backup_path


def migrate_feature_to_plugin(feature_name: str, feature_config: dict) -> dict:
    """
    Migrate a feature configuration to plugin format.

    Args:
        feature_name: The legacy feature name
        feature_config: The feature configuration dict

    Returns:
        The migrated plugin configuration
    """
    plugin_config = {}

    # Get field renames for this feature
    renames = FIELD_RENAMES.get(feature_name, {})

    for key, value in feature_config.items():
        # Skip excluded fields
        if key in EXCLUDED_FIELDS:
            continue

        # Apply any field renames
        new_key = renames.get(key, key)
        plugin_config[new_key] = value

    return plugin_config


def migrate_config(config: dict, dry_run: bool = False) -> dict:
    """
    Migrate legacy features to plugins section.

    Args:
        config: The full config dict
        dry_run: If True, don't modify config, just report

    Returns:
        The migrated config (or original if dry_run)
    """
    features = config.get("features", {})
    plugins = config.get("plugins", {})

    migrated_count = 0
    skipped_count = 0

    print("\n=== Migration Report ===\n")

    for feature_name, plugin_id in FEATURE_TO_PLUGIN_MAP.items():
        if feature_name not in features:
            print(f"  [SKIP] {feature_name}: Not configured")
            skipped_count += 1
            continue

        if plugin_id in plugins:
            print(f"  [SKIP] {feature_name} -> {plugin_id}: Already migrated")
            skipped_count += 1
            continue

        feature_config = features[feature_name]
        plugin_config = migrate_feature_to_plugin(feature_name, feature_config)

        # Show what will be migrated
        enabled = plugin_config.get("enabled", False)
        status = "ENABLED" if enabled else "disabled"
        print(f"  [MIGRATE] {feature_name} -> {plugin_id} ({status})")

        if not dry_run:
            plugins[plugin_id] = plugin_config

        migrated_count += 1

    print("\n=== Summary ===")
    print(f"  Migrated: {migrated_count}")
    print(f"  Skipped:  {skipped_count}")

    if dry_run:
        print("\n  [DRY RUN] No changes were made")
    else:
        config["plugins"] = plugins
        print("\n  Changes applied to config")

    return config


def main():
    parser = argparse.ArgumentParser(description="Migrate FiestaBoard config.json features to plugin format")
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG_PATH, help=f"Path to config.json (default: {DEFAULT_CONFIG_PATH})"
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without making changes")
    parser.add_argument("--backup", action="store_true", help="Create a backup before migration")

    args = parser.parse_args()

    print("FiestaBoard Config Migration Script")
    print("=" * 40)
    print(f"Config: {args.config}")
    print(f"Dry run: {args.dry_run}")
    print(f"Backup: {args.backup}")

    # Load config
    config = load_config(args.config)

    # Create backup if requested
    if args.backup and not args.dry_run:
        backup_config(args.config)

    # Run migration
    migrated_config = migrate_config(config, dry_run=args.dry_run)

    # Save if not dry run
    if not args.dry_run:
        save_config(args.config, migrated_config)
        print("\n✓ Migration complete!")
        print("\nRestart the FiestaBoard service to apply the changes.")
    else:
        print("\nTo apply these changes, run without --dry-run")


if __name__ == "__main__":
    main()
