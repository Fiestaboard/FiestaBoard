#!/usr/bin/env python3
"""
Sync plugin-previews.json from registry plugin manifests.

For each plugin in plugin-registry.json, fetch its manifest.json from GitHub.
A manifest that declares valid ``teaser``/``previews`` fields overwrites the
plugin's seed entry; otherwise the existing hand-authored entry is preserved.
Entries are removed only when a plugin leaves the registry. That preservation
rule is what makes "seed now, backfill later" safe - adopting the fields
silently upgrades an entry, and doing nothing never regresses one.

Requires: GH_TOKEN env var (or gh CLI already authenticated). Run from the
repo root:

  python3 scripts/sync_plugin_previews.py
"""

import base64
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
REGISTRY_PATH = REPO_ROOT / "plugin-registry.json"
PREVIEWS_PATH = REPO_ROOT / "plugin-previews.json"
MAX_WORKERS = 10

sys.path.insert(0, str(REPO_ROOT))

from src.plugins.previews import validate_previews, validate_teaser  # noqa: E402


def fetch_manifest(plugin: dict) -> dict | None:
    """Fetch a registry plugin's manifest.json via the GitHub contents API."""
    repository = plugin.get("repository", "")
    if "github.com/" not in repository:
        return None
    repo_path = repository.replace(".git", "").rstrip("/").split("github.com/")[1]
    ref = (plugin.get("branch") or "").strip()
    api_path = f"repos/{repo_path}/contents/manifest.json" + (f"?ref={ref}" if ref else "")
    result = subprocess.run(["gh", "api", api_path], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  warning: gh api {api_path} failed: {result.stderr.strip()}", file=sys.stderr)
        return None
    try:
        payload = json.loads(result.stdout)
        return json.loads(base64.b64decode(payload["content"]).decode())
    except (ValueError, KeyError, TypeError) as exc:
        print(f"  warning: could not parse manifest for {plugin['id']}: {exc}", file=sys.stderr)
        return None


def manifest_entry(plugin_id: str, manifest: dict | None) -> dict | None:
    """Return the {teaser, previews} entry a manifest declares, if valid.

    Both fields must be present and valid to take over the seed entry -
    a half-adopted or invalid declaration keeps the existing entry so the
    docs site never regresses.
    """
    if not manifest:
        return None
    teaser = manifest.get("teaser")
    previews = manifest.get("previews")
    if teaser is None and previews is None:
        return None

    errors = []
    if teaser is None:
        errors.append("previews declared without teaser")
    else:
        errors.extend(validate_teaser(teaser))
    if previews is None:
        errors.append("teaser declared without previews")
    else:
        errors.extend(validate_previews(previews))
    if errors:
        for error in errors:
            print(f"  warning: {plugin_id}: {error} - keeping existing entry", file=sys.stderr)
        return None

    return {
        "teaser": teaser,
        "previews": [
            {
                key: value
                for key, value in entry.items()
                if key in ("label", "device_type", "notes_wide", "notes_tall", "rows")
            }
            for entry in previews
        ],
    }


def sync(registry: dict, existing: dict, manifests: dict[str, dict | None]) -> dict:
    """Merge manifest-declared entries over the existing seed. Pure - no I/O."""
    merged: dict = {}
    for plugin in registry["plugins"]:
        plugin_id = plugin["id"]
        from_manifest = manifest_entry(plugin_id, manifests.get(plugin_id))
        if from_manifest is not None:
            merged[plugin_id] = from_manifest
        elif plugin_id in existing["plugins"]:
            merged[plugin_id] = existing["plugins"][plugin_id]
        else:
            print(
                f"  warning: {plugin_id} has no manifest previews and no seed entry",
                file=sys.stderr,
            )
    return {**existing, "plugins": {pid: merged[pid] for pid in sorted(merged)}}


def main() -> int:
    registry = json.loads(REGISTRY_PATH.read_text())
    existing = json.loads(PREVIEWS_PATH.read_text())

    print(f"Fetching manifests for {len(registry['plugins'])} plugins...", file=sys.stderr)
    with ThreadPoolExecutor(MAX_WORKERS) as executor:
        fetched = list(executor.map(fetch_manifest, registry["plugins"]))
    manifests = {plugin["id"]: manifest for plugin, manifest in zip(registry["plugins"], fetched, strict=True)}

    result = sync(registry, existing, manifests)
    adopted = sum(1 for pid in result["plugins"] if manifest_entry(pid, manifests.get(pid)))
    print(f"{len(result['plugins'])} entries ({adopted} from manifests)", file=sys.stderr)

    PREVIEWS_PATH.write_text(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
