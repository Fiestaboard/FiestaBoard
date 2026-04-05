#!/usr/bin/env python3
"""Extract FiestaBoard plugins into standalone public GitHub repositories.

Creates a public repo under the Fiestaboard organisation following the
``fiestaboard-plugin--{name}`` naming convention, copies the plugin source,
updates its manifest, and registers it in ``plugin-registry.json``.

Usage:
    python scripts/extract_plugin.py --plugin-id weather
    python scripts/extract_plugin.py --all
    python scripts/extract_plugin.py --all --dry-run

Requirements:
    - gh CLI authenticated with write access to the Fiestaboard org
    - git available on PATH
    - Run from the FiestaBoard repo root, or from anywhere (script detects root)

Exit codes:
    0  All extractions succeeded
    1  One or more extractions failed
    2  Bad arguments / configuration error
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent

PLUGINS_DIR = PROJECT_ROOT / "plugins"
REGISTRY_FILE = PROJECT_ROOT / "plugin-registry.json"
LICENSE_FILE = PROJECT_ROOT / "LICENSE"

# Parent directory where extracted repos are cloned (sibling of FiestaBoard)
WORKSPACE_DIR = PROJECT_ROOT.parent

ORG = "Fiestaboard"
REPO_PREFIX = "fiestaboard-plugin--"
FIESTABOARD_VERSION_CONSTRAINT = ">=2.10.0"

# Plugins that stay built-in and should NOT be extracted
BUILTIN_ONLY = {"date_time", "countdown", "_template"}

# All extractable plugins (ordered for predictable output)
ALL_PLUGINS = [
    "air_fog",
    "baywheels",
    "dad_jokes",
    "disney_parks_times",
    "generic_data",
    "guest_wifi",
    "health",
    "home_assistant",
    "last_fm",
    "muni",
    "nearby_aircraft",
    "santa_tracker",
    "spacecraft_launches",
    "sports_scores",
    "star_trek_quotes",
    "stardate",
    "stocks",
    "sun_art",
    "surf",
    "traffic",
    "visual_clock",
    "weather",
    "white_noise",
    "wsdot",
]

GITIGNORE_CONTENT = """\
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
.env
.env.local
*.egg-info/
dist/
build/
.coverage
.coverage.*
htmlcov/
.pytest_cache/
.mypy_cache/

# Editor
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    print(msg, flush=True)


def run(cmd: list[str], cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command, streaming output to stdout."""
    return subprocess.run(cmd, cwd=cwd, check=check, text=True)


def plugin_id_to_repo_name(plugin_id: str) -> str:
    """Convert plugin_id (underscores) to repo name (hyphens)."""
    return REPO_PREFIX + plugin_id.replace("_", "-")


def repo_name_to_url(repo_name: str) -> str:
    return f"https://github.com/{ORG}/{repo_name}"


def load_registry() -> dict:
    if not REGISTRY_FILE.exists():
        return {"version": "1.0.0", "plugins": []}
    with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_registry(data: dict) -> None:
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def registry_has_plugin(data: dict, plugin_id: str) -> bool:
    return any(e.get("id") == plugin_id for e in data.get("plugins", []))


def load_plugin_manifest(plugin_dir: Path) -> dict:
    manifest_path = plugin_dir / "manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def gh_repo_exists(repo_name: str) -> bool:
    """Return True if the GitHub repo already exists."""
    result = subprocess.run(
        ["gh", "repo", "view", f"{ORG}/{repo_name}"],
        capture_output=True, text=True,
    )
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Core extraction logic
# ---------------------------------------------------------------------------

def extract_plugin(plugin_id: str, dry_run: bool = False) -> bool:
    """
    Extract a single plugin into its own GitHub repository.

    Returns True on success, False on failure.
    """
    log(f"\n{'='*60}")
    log(f"Extracting: {plugin_id}")
    log(f"{'='*60}")

    plugin_dir = PLUGINS_DIR / plugin_id
    if not plugin_dir.exists():
        log(f"  ERROR: Plugin directory not found: {plugin_dir}")
        return False

    if plugin_id in BUILTIN_ONLY:
        log(f"  SKIP: {plugin_id} is designated as built-in only")
        return True

    # Load manifest
    try:
        manifest = load_plugin_manifest(plugin_dir)
    except Exception as e:
        log(f"  ERROR: Failed to load manifest: {e}")
        return False

    repo_name = plugin_id_to_repo_name(plugin_id)
    repo_url = repo_name_to_url(repo_name)
    clone_dir = WORKSPACE_DIR / repo_name

    log(f"  Repo:      {ORG}/{repo_name}")
    log(f"  URL:       {repo_url}")
    log(f"  Clone dir: {clone_dir}")

    if dry_run:
        log("  [DRY RUN] Would create repo, copy files, and register.")
        return True

    # 1. Create GitHub repo (skip if already exists)
    if gh_repo_exists(repo_name):
        log(f"  Repo already exists, skipping creation.")
    else:
        log(f"  Creating GitHub repo {ORG}/{repo_name}...")
        try:
            run([
                "gh", "repo", "create", f"{ORG}/{repo_name}",
                "--public",
                "--description", f"FiestaBoard plugin: {manifest.get('name', plugin_id)}",
            ])
        except subprocess.CalledProcessError as e:
            log(f"  ERROR: Failed to create repo: {e}")
            return False

    # 2. Clone repo locally
    if clone_dir.exists():
        log(f"  Clone dir already exists, pulling latest...")
        try:
            run(["git", "pull", "--ff-only"], cwd=clone_dir)
        except subprocess.CalledProcessError as e:
            log(f"  ERROR: git pull failed: {e}")
            return False
    else:
        log(f"  Cloning {ORG}/{repo_name}...")
        try:
            run(["gh", "repo", "clone", f"{ORG}/{repo_name}", str(clone_dir)])
        except subprocess.CalledProcessError as e:
            log(f"  ERROR: Failed to clone repo: {e}")
            return False

    # 3. Copy plugin files into cloned repo
    log(f"  Copying plugin files...")
    for item in plugin_dir.iterdir():
        dest = clone_dir / item.name
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    # 4. Update manifest.json: set repository URL + fiestaboard_version
    manifest["repository"] = repo_url
    manifest["fiestaboard_version"] = FIESTABOARD_VERSION_CONSTRAINT
    manifest_dest = clone_dir / "manifest.json"
    with open(manifest_dest, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    log(f"  Updated manifest.json")

    # 5. Add .gitignore
    gitignore_path = clone_dir / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(GITIGNORE_CONTENT)
        log(f"  Added .gitignore")

    # 6. Add LICENSE (copy from main repo)
    license_dest = clone_dir / "LICENSE"
    if LICENSE_FILE.exists() and not license_dest.exists():
        shutil.copy2(LICENSE_FILE, license_dest)
        log(f"  Added LICENSE")

    # 7. Commit and push
    log(f"  Committing and pushing...")
    try:
        run(["git", "add", "-A"], cwd=clone_dir)

        # Check if there's anything to commit
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=clone_dir, capture_output=True, text=True, check=True,
        )
        if not status.stdout.strip():
            log(f"  Nothing to commit, already up to date.")
        else:
            run(
                ["git", "commit", "-m", f"feat: initial extraction of {plugin_id} plugin from FiestaBoard"],
                cwd=clone_dir,
            )
            run(["git", "push", "origin", "HEAD"], cwd=clone_dir)
            log(f"  Pushed to {ORG}/{repo_name}")

    except subprocess.CalledProcessError as e:
        log(f"  ERROR: git commit/push failed: {e}")
        return False

    # 8. Register in plugin-registry.json
    registry = load_registry()
    if registry_has_plugin(registry, plugin_id):
        log(f"  Registry entry already exists for {plugin_id}, updating...")
        registry["plugins"] = [e for e in registry["plugins"] if e.get("id") != plugin_id]

    registry["plugins"].append({
        "id": plugin_id,
        "name": manifest.get("name", plugin_id),
        "description": manifest.get("description", ""),
        "repository": repo_url,
        "author": manifest.get("author", "FiestaBoard Team"),
        "fiestaboard_version": FIESTABOARD_VERSION_CONSTRAINT,
        "icon": manifest.get("icon", "puzzle"),
        "category": manifest.get("category", "utility"),
    })

    # Keep registry sorted by id for clean diffs
    registry["plugins"].sort(key=lambda e: e["id"])
    save_registry(registry)
    log(f"  Registered in plugin-registry.json")

    log(f"  Done: {plugin_id} -> {repo_url}")
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract FiestaBoard plugins into standalone GitHub repositories."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--plugin-id",
        metavar="ID",
        help="Extract a single plugin by ID (e.g. weather)",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help=f"Extract all {len(ALL_PLUGINS)} plugins",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would happen without making any changes",
    )

    args = parser.parse_args()

    if args.dry_run:
        log("[DRY RUN MODE] No repos will be created or modified.\n")

    if args.all:
        plugins = ALL_PLUGINS
    else:
        if args.plugin_id in BUILTIN_ONLY:
            log(f"Error: '{args.plugin_id}' is a built-in only plugin and cannot be extracted.")
            return 2
        plugins = [args.plugin_id]

    log(f"Extracting {len(plugins)} plugin(s): {', '.join(plugins)}")

    failed = []
    for plugin_id in plugins:
        ok = extract_plugin(plugin_id, dry_run=args.dry_run)
        if not ok:
            failed.append(plugin_id)

    log(f"\n{'='*60}")
    log(f"SUMMARY")
    log(f"{'='*60}")
    log(f"  Succeeded: {len(plugins) - len(failed)}/{len(plugins)}")
    if failed:
        log(f"  Failed:    {', '.join(failed)}")
        return 1

    if not args.dry_run:
        log(f"\nplugin-registry.json now has {len(load_registry().get('plugins', []))} entries.")
        log(f"Remember to commit plugin-registry.json to the branch.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
