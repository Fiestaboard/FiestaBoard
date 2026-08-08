#!/usr/bin/env python3
"""
Fetch GitHub traffic and metadata for all FiestaBoard plugin repos and write
docs-site/static/plugin-stats.json.

Requires: GH_TOKEN env var (or gh CLI already authenticated) with traffic read
access to all plugin repos. Run from the repo root:

  python3 scripts/fetch_plugin_stats.py
"""

import base64
import datetime
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REGISTRY_PATH = Path(__file__).parent.parent / "plugin-registry.json"
OUTPUT_PATH = Path(__file__).parent.parent / "docs-site/static/plugin-stats.json"
MAX_WORKERS = 10


def gh_api(path: str):
    result = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  warning: gh api {path} failed: {result.stderr.strip()}", file=sys.stderr)
        return None
    return json.loads(result.stdout)


def fetch_plugin(plugin: dict) -> dict:
    # Registry plugins are not all org-hosted (community plugins live under
    # their author's account), so derive owner/repo from the registry URL
    # instead of assuming the Fiestaboard org.
    owner, repo_name = plugin["repository"].rstrip("/").split("/")[-2:]
    print(f"  {owner}/{repo_name}", file=sys.stderr)

    # The traffic API needs push access, which we only have for org repos.
    # For community repos it 403s — keep None so the output distinguishes
    # "no data" (null) from a genuine zero.
    traffic = gh_api(f"repos/{owner}/{repo_name}/traffic/clones")
    meta = gh_api(f"repos/{owner}/{repo_name}") or {}

    version = None
    manifest_raw = gh_api(f"repos/{owner}/{repo_name}/contents/manifest.json")
    if manifest_raw and manifest_raw.get("content"):
        try:
            manifest_data = json.loads(base64.b64decode(manifest_raw["content"]).decode())
            version = manifest_data.get("version")
        except (ValueError, KeyError, TypeError) as e:
            print(f"  warning: could not parse manifest for {repo_name}: {e}", file=sys.stderr)

    return {
        "id": plugin["id"],
        "repo": repo_name,
        "name": plugin["name"],
        "category": plugin["category"],
        "description": plugin["description"],
        "version": version,
        "created_at": meta.get("created_at"),
        "updated_at": meta.get("updated_at"),
        "clones_14d_count": traffic.get("count", 0) if traffic is not None else None,
        "clones_14d_uniques": traffic.get("uniques", 0) if traffic is not None else None,
    }


def main() -> None:
    with open(REGISTRY_PATH) as f:
        registry = json.load(f)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        plugins_out = list(executor.map(fetch_plugin, registry["plugins"]))

    output = {
        "generated_at": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": 14,
        "plugins": plugins_out,
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)
        f.write("\n")
    print(f"Wrote {OUTPUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
