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
from pathlib import Path

REGISTRY_PATH = Path(__file__).parent.parent / "plugin-registry.json"
OUTPUT_PATH = Path(__file__).parent.parent / "docs-site/static/plugin-stats.json"


def gh_api(path: str):
    result = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  warning: gh api {path} failed: {result.stderr.strip()}", file=sys.stderr)
        return None
    return json.loads(result.stdout)


def main() -> None:
    with open(REGISTRY_PATH) as f:
        registry = json.load(f)

    plugins_out = []
    for plugin in registry["plugins"]:
        repo_name = plugin["repository"].rstrip("/").split("/")[-1]
        print(f"  {repo_name}", file=sys.stderr)

        traffic = gh_api(f"repos/Fiestaboard/{repo_name}/traffic/clones") or {}
        meta = gh_api(f"repos/Fiestaboard/{repo_name}") or {}

        version = None
        manifest_raw = gh_api(f"repos/Fiestaboard/{repo_name}/contents/manifest.json")
        if manifest_raw and manifest_raw.get("content"):
            try:
                manifest_data = json.loads(base64.b64decode(manifest_raw["content"]).decode())
                version = manifest_data.get("version")
            except (ValueError, KeyError, TypeError) as e:
                print(f"  warning: could not parse manifest for {repo_name}: {e}", file=sys.stderr)

        plugins_out.append({
            "id": plugin["id"],
            "repo": repo_name,
            "name": plugin["name"],
            "category": plugin["category"],
            "description": plugin["description"],
            "version": version,
            "created_at": meta.get("created_at"),
            "updated_at": meta.get("updated_at"),
            "clones_14d_count": traffic.get("count", 0),
            "clones_14d_uniques": traffic.get("uniques", 0),
        })

    output = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": 14,
        "plugins": plugins_out,
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)
        f.write("\n")
    print(f"Wrote {OUTPUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
