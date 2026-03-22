#!/usr/bin/env python3
"""Retrofit a plugin's manifest.json from list-based to dict-based simple variables.

Reads manifest.json, converts variables.simple from a list to a dict skeleton
with max_lengths migrated into per-variable max_length fields. The top-level
max_lengths section is removed for simple variables (array max_lengths are kept).

Descriptions, groups, and examples must be filled in manually afterward.

Usage:
    python scripts/retrofit_plugin_manifest.py /path/to/plugin/dir
    python scripts/retrofit_plugin_manifest.py /path/to/plugin/dir --dry-run
"""

import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path


def retrofit_manifest(manifest_path: Path, dry_run: bool = False) -> dict:
    with open(manifest_path) as f:
        manifest = json.load(f, object_pairs_hook=OrderedDict)

    variables = manifest.get("variables", {})
    simple = variables.get("simple", [])
    max_lengths = manifest.get("max_lengths", {})

    if isinstance(simple, dict):
        print(f"  Already in dict format, skipping: {manifest_path}")
        return manifest

    if not isinstance(simple, list):
        print(f"  Unexpected simple type {type(simple).__name__}, skipping: {manifest_path}")
        return manifest

    new_simple = OrderedDict()
    array_max_lengths = OrderedDict()

    for var_name in simple:
        entry = OrderedDict()
        entry["description"] = ""
        entry["type"] = "string"
        ml = max_lengths.get(var_name)
        if ml is not None:
            entry["max_length"] = ml
        entry["group"] = "main"
        entry["example"] = ""
        new_simple[var_name] = entry

    # Separate array max_lengths (contain dots) from simple ones
    for key, val in max_lengths.items():
        if "." in key:
            array_max_lengths[key] = val

    # Build new variables section preserving key order
    new_variables = OrderedDict()
    new_variables["groups"] = OrderedDict([("main", OrderedDict([("label", "Main")]))])
    new_variables["simple"] = new_simple

    # Preserve arrays if they exist
    if "arrays" in variables:
        new_variables["arrays"] = variables["arrays"]

    # Preserve other variable keys (dynamic, nested, etc.)
    for key in variables:
        if key not in ("simple", "arrays", "groups"):
            new_variables[key] = variables[key]

    manifest["variables"] = new_variables

    # Replace max_lengths: keep only array max_lengths, or remove entirely
    if array_max_lengths:
        manifest["max_lengths"] = array_max_lengths
    elif "max_lengths" in manifest:
        del manifest["max_lengths"]

    if dry_run:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
    else:
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"  Converted: {manifest_path}")

    return manifest


def main():
    parser = argparse.ArgumentParser(description="Retrofit plugin manifest to rich metadata format")
    parser.add_argument("plugin_dir", type=Path, help="Path to the plugin directory")
    parser.add_argument("--dry-run", action="store_true", help="Print result without writing")
    args = parser.parse_args()

    manifest_path = args.plugin_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"Error: {manifest_path} not found", file=sys.stderr)
        sys.exit(1)

    retrofit_manifest(manifest_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
